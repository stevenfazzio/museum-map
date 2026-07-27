"""Build 10 — embed every museum's lead with BGE-M3.

Only one text variant here. The probe's (b) nofirst and (c) noloc existed to
answer "is the space just geography?", and that question is settled: geography is
a gradient the map should keep, not a confound to strip. So the map is built on
the lead as fetched.

BGE-M3 rather than e5-large, because the probe's second encoder showed the
language dominance that drove the first round's conclusions was an e5 artefact:
language ARI +0.769 under e5 versus +0.017 under BGE-M3, with raw cross-lingual
P@1 of 0.941. No prefix — that is an e5 convention.
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

from build.common import corpus_paths, fmt_eta  # noqa: E402

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

    # Row count alone cannot decide whether a cached embedding is still valid:
    # changing which language's article represents each museum leaves the count
    # identical and every vector wrong. The fingerprint covers the actual texts
    # and the settings that change their vectors.
    meta_path = emb_path.with_name("emb.meta.json")
    fingerprint = {
        "n": len(leads),
        "model": args.model,
        "max_seq_len": args.max_seq_len,
        "texts_sha1": hashlib.sha1(
            "\x00".join(leads.text.fillna("")).encode()
        ).hexdigest(),
    }
    if emb_path.exists():
        emb = np.load(emb_path)
        prev = json.loads(meta_path.read_text()) if meta_path.exists() else None
        if prev == fingerprint and len(emb) == len(leads):
            print(f"{emb_path.name}: cached and fingerprint matches, nothing to do")
            return
        if prev is None:
            print(f"{emb_path.name}: no fingerprint on disk — cannot verify, re-embedding")
        else:
            differing = [k for k in fingerprint if prev.get(k) != fingerprint[k]]
            print(f"{emb_path.name}: stale ({', '.join(differing)} changed) — re-embedding")

    device = args.device or ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"corpus={args.corpus}  rows={len(leads):,}  model={args.model}  device={device}")

    model = SentenceTransformer(args.model, device=device)
    model.max_seq_length = min(model.max_seq_length, args.max_seq_len)
    prefix = "query: " if "e5" in args.model.lower() else ""
    texts = [prefix + t for t in leads.text.fillna("")]

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
    part_path = emb_path.with_name(emb_path.name + ".part.npy")
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

    emb = np.concatenate(done)
    assert len(emb) == len(leads), f"{len(emb)} vectors for {len(leads)} museums"
    tmp = emb_path.with_name(emb_path.name + ".tmp")
    with open(tmp, "wb") as fh:
        np.save(fh, emb)
    tmp.replace(emb_path)
    meta_path.write_text(json.dumps(fingerprint, indent=2))
    part_path.unlink(missing_ok=True)
    print(f"\n{emb.shape} -> {emb_path}  ({fmt_eta(time.monotonic() - t0)})")


if __name__ == "__main__":
    main()
