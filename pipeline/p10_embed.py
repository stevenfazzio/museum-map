"""Build 10 — embed every museum's lead with BGE-M3.

Only one text variant: the lead as fetched. Variants that stripped the first
sentence or masked place names were tried to see whether the space was merely
geography; it is not, and geography is a gradient the map should keep rather than
a confound to strip.

BGE-M3 rather than multilingual-e5-large. Under e5, article language dominated
everything — language ARI +0.769, against +0.017 under BGE-M3, with raw
cross-lingual P@1 of 0.941. Encoder choice, not corpus, was doing that. No prefix
here — that is an e5 convention.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from museum_map.common import write_parquet  # noqa: E402
from pipeline.common import corpus_paths, fmt_eta  # noqa: E402

MODEL = "BAAI/bge-m3"

# BGE-M3 advertises max_seq_length 8192, and sentence-transformers sorts a batch
# descending by length, so the very first batch is the longest texts in the
# corpus padded to each other. At full scale that is 32 x ~4,100 tokens through a
# 568M-parameter model, and MPS dies with
# kIOGPUCommandBufferCallbackErrorOutOfMemory before a single vector is written.
# The 2,000-museum fixture never triggered it: its longest lead is half as long.
#
# Capping the sequence length bounds that worst-case batch. 2048 costs 0.13% of
# leads a truncation (p99 is 856 tokens, p99.9 is 2,091) — the cap is reported at
# run time so the number is never silently assumed.
MAX_SEQ_LEN = 2048


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="fixture")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--device", default=None)
    ap.add_argument("--max-seq-len", type=int, default=MAX_SEQ_LEN)
    ap.add_argument("--chunk", type=int, default=5000, help="rows per checkpoint")
    args = ap.parse_args()

    import torch
    from sentence_transformers import SentenceTransformer

    leads_path, out_dir = corpus_paths(args.corpus)
    emb_path = out_dir / "emb.npy"

    leads = pd.read_parquet(leads_path, columns=["qid", "lang", "text", "chars"])
    leads = leads.sort_values("qid").reset_index(drop=True)
    np.save(out_dir / "qids.npy", leads.qid.to_numpy())

    # Staleness is tracked PER ROW, not as one hash over the whole corpus.
    # A single corpus-wide fingerprint detects a change correctly and then cannot
    # say where it is, so one edited lead forces re-embedding all 49,218 — an hour
    # and a half of GPU time to redo work that is still valid. Each museum's
    # vector depends only on its own text (verified: re-encoding a text alone
    # reproduces its stored vector bit-identically, so batch composition does not
    # affect the result), which makes reuse safe row by row.
    #
    # `settings` are the things that invalidate *everything* — a different model
    # or sequence cap changes every vector, so those still force a full rebuild.
    meta_path = emb_path.with_name("emb.meta.json")
    index_path = emb_path.with_name("emb.index.parquet")
    settings = {"model": args.model, "max_seq_len": args.max_seq_len}
    row_hash = pd.Series(
        [hashlib.sha1(t.encode()).hexdigest()[:16] for t in leads.text.fillna("")],
        index=leads.index,
    )

    cached: dict[str, np.ndarray] = {}
    if emb_path.exists() and index_path.exists() and meta_path.exists():
        prev_settings = json.loads(meta_path.read_text())
        if {k: prev_settings.get(k) for k in settings} == settings:
            prev_emb = np.load(emb_path)
            prev_idx = pd.read_parquet(index_path)
            if len(prev_emb) == len(prev_idx):
                cached = {
                    q: prev_emb[i]
                    for i, (q, h) in enumerate(zip(prev_idx.qid, prev_idx.source_sha1))
                    if h is not None
                }
                cached_hash = dict(zip(prev_idx.qid, prev_idx.source_sha1))
                cached = {q: v for q, v in cached.items() if q in cached_hash}
                reusable = {
                    q for q, h in zip(leads.qid, row_hash) if cached_hash.get(q) == h
                }
                cached = {q: v for q, v in cached.items() if q in reusable}
        else:
            changed = [k for k in settings if prev_settings.get(k) != settings[k]]
            print(f"{', '.join(changed)} changed — every vector is invalid, full re-embed")

    todo_mask = ~leads.qid.isin(cached)
    n_reuse, n_todo = len(leads) - int(todo_mask.sum()), int(todo_mask.sum())
    if n_todo == 0:
        print(f"{emb_path.name}: all {len(leads):,} rows still match their lead, nothing to do")
        return
    if n_reuse:
        print(f"reusing {n_reuse:,} cached vectors, re-embedding {n_todo:,} changed rows "
              f"({n_todo / len(leads):.1%})")

    device = args.device or ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"corpus={args.corpus}  rows={len(leads):,}  model={args.model}  device={device}")

    model = SentenceTransformer(args.model, device=device)
    model.max_seq_length = min(model.max_seq_length, args.max_seq_len)
    prefix = "query: " if "e5" in args.model.lower() else ""
    todo = leads[todo_mask].reset_index(drop=True)
    texts = [prefix + t for t in todo.text.fillna("")]

    tok = model.tokenizer
    lens = [len(tok.encode(t, add_special_tokens=True)) for t in texts]
    trunc = float(np.mean([n > model.max_seq_length for n in lens]))
    print(f"tokens: median {np.median(lens):.0f}, p95 {np.percentile(lens, 95):.0f}, "
          f"max {max(lens)}, cap {model.max_seq_length}, truncated {trunc:.2%}")
    print(f"batch_size={args.batch_size}  worst-case batch "
          f"{args.batch_size * model.max_seq_length:,} tokens")

    # Encoded in chunks with a checkpoint after each, because this is an hour of
    # GPU time and the failure mode that actually happened was an OOM part-way
    # through, which lost the lot. Partial work now survives a crash and a re-run
    # picks up where it stopped.
    # The checkpoint is named after the exact set of rows being embedded. Without
    # that, a partial file left by a run over a *different* subset would look
    # resumable purely because it is shorter, and its vectors would be silently
    # assigned to the wrong museums.
    todo_sig = hashlib.sha1("\x00".join(todo.qid).encode()).hexdigest()[:12]
    for old in emb_path.parent.glob("emb.npy.part.*.npy"):
        if todo_sig not in old.name:
            old.unlink(missing_ok=True)
    part_path = emb_path.with_name(f"emb.npy.part.{todo_sig}.npy")
    done: list[np.ndarray] = []
    n_done = 0
    if part_path.exists():
        prev = np.load(part_path)
        if len(prev) <= len(texts):
            done, n_done = [prev], len(prev)
            print(f"resuming from checkpoint: {n_done:,}/{len(texts):,} rows already embedded")

    t0, started_at = time.monotonic(), n_done
    while n_done < len(texts):
        batch = texts[n_done : n_done + args.chunk]
        vecs = model.encode(
            batch,
            batch_size=args.batch_size,
            normalize_embeddings=True,
            show_progress_bar=sys.stdout.isatty(),
            convert_to_numpy=True,
        ).astype(np.float32)
        done.append(vecs)
        n_done += len(batch)
        tmp = part_path.with_suffix(".tmp")
        with open(tmp, "wb") as fh:
            np.save(fh, np.concatenate(done))
        tmp.replace(part_path)
        # Rate over rows done *this session* — counting resumed rows against
        # only this session's clock would report a fictitious speedup.
        rate = (n_done - started_at) / max(time.monotonic() - t0, 1e-9)
        print(f"  {n_done:,}/{len(texts):,} embedded  {rate:.0f} rows/s  "
              f"eta {fmt_eta((len(texts) - n_done) / rate)}", flush=True)

    fresh = np.concatenate(done)
    assert len(fresh) == len(todo), f"{len(fresh)} vectors for {len(todo)} changed rows"
    cached.update(dict(zip(todo.qid, fresh)))

    # Reassemble in the corpus's qid order, so row i always means qids[i] whether
    # the vector was reused or just computed.
    emb = np.vstack([cached[q] for q in leads.qid]).astype(np.float32)
    assert len(emb) == len(leads), f"{len(emb)} vectors for {len(leads)} museums"
    tmp = emb_path.with_name(emb_path.name + ".tmp")
    with open(tmp, "wb") as fh:
        np.save(fh, emb)
    tmp.replace(emb_path)
    meta_path.write_text(json.dumps({**settings, "n": len(leads)}, indent=2))
    write_parquet(pd.DataFrame({"qid": leads.qid, "source_sha1": row_hash.to_numpy()}),
                  index_path, expect_cols=["qid", "source_sha1"])
    part_path.unlink(missing_ok=True)
    print(f"\n{emb.shape} -> {emb_path}  "
          f"({n_todo:,} embedded in {fmt_eta(time.monotonic() - t0)}, {n_reuse:,} reused)")


if __name__ == "__main__":
    main()
