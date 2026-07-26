"""Stage 07 — embed all three variants with a multilingual encoder.

Default is intfloat/multilingual-e5-large (XLM-R based, 1024-dim). Pass
--model BAAI/bge-m3 to rerun with the other candidate; outputs are named after
the model so the two never overwrite each other.

e5's model card: use the "query: " prefix for non-retrieval tasks, which is what
clustering is. bge-m3 takes no prefix.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from probe.common import INTERIM, PROCESSED  # noqa: E402

VARIANTS = {"a_full": "text_full", "b_nofirst": "text_nofirst", "c_noloc": "text_noloc"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="intfloat/multilingual-e5-large")
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--device", default=None)
    args = ap.parse_args()

    import torch
    from sentence_transformers import SentenceTransformer

    device = args.device or ("mps" if torch.backends.mps.is_available() else "cpu")
    tag = args.model.split("/")[-1]
    print(f"model={args.model}  device={device}")

    v = pd.read_parquet(INTERIM / "variants.parquet")
    model = SentenceTransformer(args.model, device=device)
    max_len = model.max_seq_length
    prefix = "query: " if "e5" in args.model.lower() else ""
    print(f"max_seq_length={max_len}  prefix={prefix!r}  rows={len(v):,}")

    np.save(PROCESSED / "qids.npy", v.qid.to_numpy())

    tok = model.tokenizer
    stats = {}
    for name, col in VARIANTS.items():
        out = PROCESSED / f"emb_{tag}_{name}.npy"
        texts = [prefix + t for t in v[col].fillna("")]

        lens = [len(tok.encode(t, add_special_tokens=True)) for t in texts]
        trunc = float(np.mean([n > max_len for n in lens]))
        stats[name] = (float(np.median(lens)), trunc)

        if out.exists():
            print(f"  {name}: cached ({out.name})")
            continue
        emb = model.encode(
            texts,
            batch_size=args.batch_size,
            normalize_embeddings=True,
            show_progress_bar=True,
            convert_to_numpy=True,
        )
        # np.save appends ".npy" unless the path already ends in it, so write
        # through a handle to keep the temp name exactly as given.
        tmp = out.with_name(out.name + ".tmp")
        with open(tmp, "wb") as fh:
            np.save(fh, emb.astype(np.float32))
        tmp.replace(out)
        print(f"  {name}: {emb.shape} -> {out.name}")

    print("\ntoken lengths (median) and share truncated at the model limit:")
    for name, (med, trunc) in stats.items():
        flag = "  <- truncation is material" if trunc > 0.15 else ""
        print(f"  {name:<12} median {med:5.0f} tok   truncated {trunc:5.1%}{flag}")


if __name__ == "__main__":
    main()
