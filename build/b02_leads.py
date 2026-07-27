"""Build 02 — fetch the lead section of every article in the corpus.

The long pole of the whole project: ~166k articles across ~300 wikis. Two things
this stage does that the probe's s05 did not, both learned the hard way there:

* **Bounded concurrency.** The fetch is latency-bound (~3.3 s per request against
  a 0.15 s throttle floor), so a handful of workers converts ~10 hours into ~3
  while staying well inside polite WMF rates. Work is queued per (wiki, 20-title
  chunk), not per wiki, because the article distribution is skewed enough that
  per-wiki workers would leave enwiki running alone for an hour at the end.

* **Per-wiki shards.** Every fetched response was already cached, so the *network*
  cost always survived a crash — but the final assembly did not, and replaying
  ~9k cached responses to rebuild it is pure waste. Each wiki's rows are written
  the moment its last chunk lands, and a completed shard is skipped entirely on
  re-run. A wiki that had a permanently failing chunk is written as `.partial`
  and retried next time.

Run it detached and watch the log file. Do not pipe it through `tail` — the
progress output buffers and you go blind for hours.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build.common import FULL_INTERIM, LEAD_SHARDS, fmt_eta, select_leads  # noqa: E402
from probe.common import RAW, write_parquet  # noqa: E402
from probe.textproc import normalize_ws  # noqa: E402
from probe.wiki import EXTRACT_BATCH, fetch_leads_many  # noqa: E402


def shard_paths(dbname: str) -> tuple[Path, Path]:
    return LEAD_SHARDS / f"{dbname}.parquet", LEAD_SHARDS / f"{dbname}.partial.parquet"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--wikis", type=int, default=0, help="largest N wikis only (smoke test)")
    ap.add_argument("--assemble-only", action="store_true")
    args = ap.parse_args()

    sl = pd.read_parquet(FULL_INTERIM / "sitelinks.parquet")
    api2db = dict(zip(sl.api, sl.dbname))
    by_api = {api: sorted(set(g.title)) for api, g in sl.groupby("api")}
    order = sorted(by_api, key=lambda a: (-len(by_api[a]), a))
    if args.wikis:
        order = order[: args.wikis]

    # Rows for a wiki are assembled from the sitelink frame, not from the response:
    # several museums can point at the same article via redirects, and each of them
    # needs its own row.
    rows_by_api = {api: g[["qid", "title", "lang"]] for api, g in sl.groupby("api")}

    if not args.assemble_only:
        todo, skipped = [], 0
        for api in order:
            done, _ = shard_paths(api2db[api])
            if done.exists():
                skipped += 1
            else:
                todo.append(api)

        n_titles = sum(len(by_api[a]) for a in todo)
        n_chunks = sum(-(-len(by_api[a]) // EXTRACT_BATCH) for a in todo)
        print(f"{len(order)} wikis in corpus; {skipped} already complete, {len(todo)} to fetch")
        print(f"{n_titles:,} articles -> {n_chunks:,} requests, workers={args.workers}")
        if todo:
            print("largest: " + ", ".join(
                f"{api2db[a]}={len(by_api[a]):,}" for a in todo[:8]))

        t0 = time.monotonic()

        def on_wiki_done(api: str, got: dict[str, str], n_failed: int) -> None:
            rows = []
            for q, title, lang in rows_by_api[api].itertuples(index=False):
                text = got.get(title)
                if not text:
                    continue
                text = normalize_ws(text)
                if text:
                    rows.append({"qid": q, "lang": lang, "dbname": api2db[api],
                                 "title": title, "text": text, "chars": len(text)})
            df = pd.DataFrame(rows, columns=["qid", "lang", "dbname", "title", "text", "chars"])
            done, partial = shard_paths(api2db[api])
            df.to_parquet(done if not n_failed else partial, index=False)
            if n_failed:
                print(f"  ! {api2db[api]}: {n_failed} chunk(s) failed -> .partial, "
                      f"will retry on re-run", flush=True)

        # A cumulative rate is useless here: a resumed run replays thousands of
        # cached responses in the first second, and the resulting average makes
        # every later ETA wildly optimistic for the rest of the run. Measure over
        # a trailing window instead, so the number reflects the network.
        window: list[tuple[int, float]] = []

        def on_progress(n: int, total: int, wikis_left: int) -> None:
            if n % 100 and n != total:
                return
            now = time.monotonic()
            window.append((n, now))
            del window[:-10]
            dn, dt = n - window[0][0], now - window[0][1]
            rate = dn / dt if dt > 0 and dn else 0.0
            eta = (total - n) / rate if rate else float("inf")
            print(f"  {n:,}/{total:,} req  {rate:.2f} req/s  {wikis_left} wikis open  "
                  f"eta {fmt_eta(eta)}  elapsed {fmt_eta(now - t0)}", flush=True)

        fetch_leads_many({a: by_api[a] for a in todo}, workers=args.workers,
                         on_wiki_done=on_wiki_done, on_progress=on_progress)
        print(f"\nfetch elapsed: {fmt_eta(time.monotonic() - t0)}")

    # ---- assemble ----------------------------------------------------------
    complete = {p.stem: p for p in LEAD_SHARDS.glob("*.parquet")
                if not p.name.endswith(".partial.parquet")}
    partial = {p.name[: -len(".partial.parquet")]: p
               for p in LEAD_SHARDS.glob("*.partial.parquet")}
    use = {**partial, **complete}  # a complete shard always wins over a stale partial
    print(f"\nassembling {len(use)} shards ({len(partial)} partial)")

    frames = [pd.read_parquet(p) for p in use.values()]
    allleads = pd.concat([f for f in frames if len(f)], ignore_index=True)
    write_parquet(allleads, FULL_INTERIM / "leads_all.parquet",
                  expect_cols=["qid", "lang", "text", "chars"])

    museums = pd.read_parquet(RAW / "museums.parquet")
    best = select_leads(allleads, dict(zip(museums.qid, museums.country_qid)))
    best = museums.merge(best, on="qid", how="inner")
    write_parquet(best, FULL_INTERIM / "leads.parquet",
                  expect_cols=["qid", "lang", "text", "chars", "lat", "lon", "country_qid"])

    print(f"\nmuseums with a usable lead: {len(best):,} / {len(museums):,} "
          f"({len(museums) - len(best):,} lost)")
    print(f"articles per museum: mean {len(allleads) / allleads.qid.nunique():.2f}")
    print(f"lead is in an official language of its country: {best.is_local.mean():.1%}")
    print(f"english share: {(best.lang == 'en').mean():.1%}")
    print(f"languages represented: {best.lang.nunique()}")
    print("\nselected-lead language (top 15):")
    for k, v in best.lang.value_counts().head(15).items():
        print(f"  {k:<8} {v:>6}  {v / len(best) * 100:4.1f}%")
    print("\nlead length (characters):")
    print(best.chars.describe(percentiles=[0.05, 0.1, 0.25, 0.5, 0.75, 0.9]).round(0).to_string())
    for thresh in (100, 150, 200, 300):
        print(f"  under {thresh} chars: {(best.chars < thresh).mean():6.1%}")


if __name__ == "__main__":
    main()
