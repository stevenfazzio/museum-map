"""Pipeline 06 — one-sentence English summary of each museum's lead.

80.9% of leads are not in English, because the corpus deliberately prefers the
local-language article (see `museum_map/common.py:select_leads`). That is right
for *placing* a museum and useless for *reading* about one: the map's tooltip was
showing Ukrainian, Japanese and Arabic text to an English-reading audience.

Summaries are generated from the embedded lead, not from the museum's English
Wikipedia article where one happens to exist (40.1% of them). The tooltip should
explain why a point sits where it does, and what put it there is the text we
embedded — an English article we did *not* embed would answer with a different
document.

Batched ~10 museums per call, because the per-call overhead dominates otherwise:
one call per museum is ~49k calls, batching cuts it to ~5k. Shards land every
`--checkpoint` batches so a crash costs minutes, not the whole run.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from museum_map.common import write_parquet  # noqa: E402
from pipeline.common import corpus_paths, fmt_eta  # noqa: E402

MODEL = "claude-haiku-4-5"
BATCH = 10
CONCURRENCY = 8
MAX_LEAD_CHARS = 1200  # the tail runs to 29,902; the first paragraph carries the gist

SYSTEM = """\
You summarise museum descriptions for the tooltip of an interactive map.

You will get a numbered list of Wikipedia lead sections, each about one museum, \
in any language. For each one, write a single English sentence naming what the \
museum is actually about — its subject, collection, or distinguishing feature.

GROUNDING IS THE HARD RULE. Every fact in your sentence must come from the \
provided text for that museum. You may recognise some of these museums — ignore \
what you know. If the text gives only a location and a founding date, your \
sentence gives only a location and a founding date. Never infer a museum's \
subject from its name: a text that says "the Ferenczy Museum was founded in \
1951 at Kossuth Lajos street 5" supports "founded in 1951 in Szentendre" and \
does NOT support "dedicated to the works of the Ferenczy family of artists", no \
matter how likely that is to be true. A thin sentence is correct when the source \
is thin; an invented one is a bug.

Other rules:
- One sentence per museum, at most 25 words.
- English, whatever the source language.
- Within what the text supports, keep what makes this museum specific: the \
collection, the subject, what makes it notable. "A museum in Poland" is weak if \
the text offers more; "a museum of antique weighing scales, the first of its \
kind in Ukraine" is what we want when the text says so.
- Do not begin with "This museum" or the museum's own name. Start with the \
substance.

Reply with a JSON object mapping each number to its sentence, and nothing else:
{"1": "...", "2": "..."}"""


def build_prompt(rows: list[tuple[int, str, str]]) -> str:
    parts = []
    for n, name, text in rows:
        parts.append(f"{n}. [{name}] {text[:MAX_LEAD_CHARS]}")
    return "\n\n".join(parts)


def parse_reply(text: str, n: int) -> dict[int, str]:
    """Pull the JSON object out of the reply, tolerating stray prose around it."""
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    out = {}
    for k, v in raw.items():
        try:
            i = int(str(k).strip())
        except ValueError:
            continue
        if 1 <= i <= n and isinstance(v, str) and v.strip():
            out[i] = " ".join(v.split())
    return out


async def summarise_all(client, model: str, batches: list[list[tuple]], concurrency: int,
                        on_done) -> None:
    sem = asyncio.Semaphore(concurrency)

    async def one(idx: int, rows: list[tuple]) -> None:
        async with sem:
            try:
                resp = await client.messages.create(
                    model=model,
                    max_tokens=2048,
                    system=SYSTEM,
                    messages=[{"role": "user", "content": build_prompt(rows)}],
                )
                text = next((b.text for b in resp.content if b.type == "text"), "")
                got = parse_reply(text, len(rows))
                usage = (resp.usage.input_tokens, resp.usage.output_tokens)
            except Exception as exc:  # one bad batch must not kill the run
                print(f"    ! batch {idx}: {type(exc).__name__}: {exc}", flush=True)
                got, usage = {}, (0, 0)
            on_done(idx, rows, got, usage)

    await asyncio.gather(*(one(i, rows) for i, rows in enumerate(batches)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="fixture")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--concurrency", type=int, default=CONCURRENCY)
    ap.add_argument("--limit", type=int, default=0, help="first N museums only (smoke test)")
    args = ap.parse_args()

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY is not set")

    from anthropic import AsyncAnthropic

    leads_path, out_dir = corpus_paths(args.corpus)
    out_path = out_dir / "summaries.parquet"
    leads = pd.read_parquet(leads_path).sort_values("qid").reset_index(drop=True)
    if args.limit:
        leads = leads.head(args.limit)

    # A summary describes a specific lead, so keying it on qid alone makes a
    # changed lead invisible: the row is still there, and its summary now
    # describes text that is no longer in the corpus. (Changing the lead-selection
    # rule moved 13.5% of leads once already.) The source hash makes that
    # detectable, the same way p10 fingerprints the embedding inputs.
    src_hash = {q: hashlib.sha1(t.encode()).hexdigest()[:16]
                for q, t in zip(leads.qid, leads.text.fillna(""))}

    # The lead is only half of what produced a summary; the prompt and the model
    # are the other half. Hashing the text alone means editing SYSTEM — or asking
    # for extra fields — leaves all 54,778 rows looking fresh, and the stage
    # cheerfully reports "nothing to do" while the file describes the old prompt.
    # Kept in its own column rather than mixed into `source_sha1` so that adding
    # the check does not itself invalidate summaries that are perfectly good.
    prompt_hash = hashlib.sha1(f"{SYSTEM}\x00{args.model}".encode()).hexdigest()[:16]

    have: dict[str, str] = {}
    if out_path.exists():
        prev = pd.read_parquet(out_path)
        if "source_sha1" in prev.columns:
            if "prompt_sha1" not in prev.columns:
                # Written before this column existed. Its rows were generated by
                # whatever SYSTEM/model was current then, which cannot be
                # recovered from the file — so they are grandfathered rather than
                # silently rebilled. Delete the file to force a clean regeneration.
                print(f"{out_path.name}: predates prompt fingerprinting — assuming its "
                      f"{len(prev):,} summaries came from the current prompt and model")
                prev = prev.assign(prompt_sha1=prompt_hash)
            ok = [
                src_hash.get(q) == h and p == prompt_hash
                for q, h, p in zip(prev.qid, prev.source_sha1, prev.prompt_sha1)
            ]
            fresh = prev[ok]
            stale_lead = sum(
                src_hash.get(q) != h for q, h in zip(prev.qid, prev.source_sha1)
            )
            stale_prompt = len(prev) - len(fresh) - stale_lead
            have = dict(zip(fresh.qid, fresh.summary))
            print(f"resuming: {len(have):,} summaries still match their lead and prompt"
                  + (f", {stale_lead:,} stale (lead changed)" if stale_lead else "")
                  + (f", {stale_prompt:,} stale (prompt or model changed)"
                     if stale_prompt else ""))
        else:
            print(f"{out_path.name}: no source hashes — cannot verify {len(prev):,} "
                  "summaries against their leads, regenerating all")

    todo = leads[~leads.qid.isin(have)]
    name_col = leads.label.where(leads.has_label, leads.title) if "has_label" in leads else leads.label
    names = dict(zip(leads.qid, name_col.fillna(leads.qid)))
    rows = [(q, names.get(q, q), t) for q, t in zip(todo.qid, todo.text.fillna(""))]
    batches = [
        [(i + 1, nm, tx) for i, (_, nm, tx) in enumerate(rows[s : s + args.batch])]
        for s in range(0, len(rows), args.batch)
    ]
    qid_batches = [
        [q for q, _, _ in rows[s : s + args.batch]] for s in range(0, len(rows), args.batch)
    ]

    print(f"corpus={args.corpus}  {len(leads):,} museums, {len(rows):,} to summarise")
    print(f"model={args.model}  batch={args.batch}  concurrency={args.concurrency}  "
          f"{len(batches):,} calls")
    if not batches:
        print("nothing to do")
        return

    t0 = time.monotonic()
    state = {"done": 0, "in": 0, "out": 0, "missing": 0}

    def flush() -> None:
        df = pd.DataFrame({"qid": list(have), "summary": list(have.values())})
        df["source_sha1"] = df.qid.map(src_hash)
        df["prompt_sha1"] = prompt_hash
        write_parquet(df.sort_values("qid").reset_index(drop=True), out_path,
                      expect_cols=["qid", "summary", "source_sha1", "prompt_sha1"])

    def on_done(idx: int, batch_rows: list[tuple], got: dict[int, str], usage) -> None:
        qids = qid_batches[idx]
        for i, q in enumerate(qids, start=1):
            if i in got:
                have[q] = got[i]
            else:
                state["missing"] += 1
        state["done"] += 1
        state["in"] += usage[0]
        state["out"] += usage[1]
        n = state["done"]
        if n % 50 == 0 or n == len(batches):
            rate = n / max(time.monotonic() - t0, 1e-9)
            cost = state["in"] / 1e6 * 1.0 + state["out"] / 1e6 * 5.0
            print(f"  {n:,}/{len(batches):,} calls  {rate:.1f}/s  "
                  f"eta {fmt_eta((len(batches) - n) / rate)}  ${cost:.2f} so far", flush=True)
        if n % 200 == 0:
            flush()

    client = AsyncAnthropic(api_key=key)
    asyncio.run(summarise_all(client, args.model, batches, args.concurrency, on_done))
    flush()

    cost = state["in"] / 1e6 * 1.0 + state["out"] / 1e6 * 5.0
    print(f"\nelapsed {fmt_eta(time.monotonic() - t0)}  "
          f"tokens in {state['in']:,} out {state['out']:,}  cost ${cost:.2f}")
    print(f"summaries: {len(have):,}/{len(leads):,}  ({state['missing']:,} not returned)")
    lens = pd.Series([len(s.split()) for s in have.values()])
    print(f"length: median {lens.median():.0f} words, p95 {lens.quantile(0.95):.0f}, "
          f"max {lens.max()}")


if __name__ == "__main__":
    main()
