"""Build 11 — per-language centring, then UMAP to the 2D map plane.

Centring uses leave-one-out means shrunk toward the global mean (`probe/debias.py`).
Plain per-language centring is not usable here: at fixture scale 28 of 104
languages have exactly one museum, and subtracting a singleton group's mean from
its only member puts that point exactly on the origin — manufacturing a dense
fake cluster at the centre of the map. The full corpus has more languages and a
longer singleton tail, so this matters more, not less.

Geography is deliberately *not* removed. Language was a corpus artefact and
parallel articles gave an oracle to confirm the removal took the artefact rather
than the content; location is constitutive of what a museum is, and there is no
"same museum, different place" to validate a removal against.

The 2D coordinates are an input to the next stage, not just a picture: Toponymy's
default clusterer finds its regions in *this* space, so these parameters decide
what gets named.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common import corpus_paths, fmt_eta  # noqa: E402
from museum_map.common import SEED, write_parquet  # noqa: E402
from museum_map.debias import centered  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="fixture")
    ap.add_argument("--n-neighbors", type=int, default=15)
    ap.add_argument("--min-dist", type=float, default=0.0)
    ap.add_argument("--no-center", action="store_true", help="skip per-language centring")
    args = ap.parse_args()

    leads_path, out_dir = corpus_paths(args.corpus)
    leads = pd.read_parquet(leads_path).sort_values("qid").reset_index(drop=True)
    qids = np.load(out_dir / "qids.npy", allow_pickle=True)
    emb = np.load(out_dir / "emb.npy")
    assert len(emb) == len(leads) == len(qids), (len(emb), len(leads), len(qids))
    assert (leads.qid.to_numpy() == qids).all(), "qid order drifted from the embedding order"

    print(f"corpus={args.corpus}  {emb.shape}  {leads.lang.nunique()} languages")
    singleton = (leads.lang.value_counts() == 1).sum()
    print(f"languages with exactly one museum: {singleton}")

    if args.no_center:
        X = emb
        print("centring: SKIPPED")
    else:
        t0 = time.monotonic()
        X = centered(emb, leads.lang.to_numpy())
        print(f"centring: leave-one-out + shrinkage, {fmt_eta(time.monotonic() - t0)}")
        np.save(out_dir / "emb_centered.npy", X.astype(np.float32))

    import umap

    t0 = time.monotonic()
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=args.n_neighbors,
        min_dist=args.min_dist,
        metric="cosine",
        random_state=SEED,
        verbose=True,
    )
    xy = reducer.fit_transform(X)
    print(f"umap: {fmt_eta(time.monotonic() - t0)}")

    coords = pd.DataFrame({"qid": qids, "x": xy[:, 0].astype("float32"),
                           "y": xy[:, 1].astype("float32")})
    write_parquet(coords, out_dir / "coords.parquet", expect_cols=["qid", "x", "y"])
    print(f"\nx range [{xy[:, 0].min():.2f}, {xy[:, 0].max():.2f}]  "
          f"y range [{xy[:, 1].min():.2f}, {xy[:, 1].max():.2f}]")


if __name__ == "__main__":
    main()
