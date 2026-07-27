"""Build 12 — name the regions of the map with Toponymy.

Toponymy is map labelling, not topic modelling: it names *regions of the space*
at several zoom levels, then propagates each region's name to the points inside
it. Two consequences that shape this stage:

* The 2D coordinates from b11 are an **input**, not a picture. The default
  clusterer finds its regions in that space, so b11's UMAP parameters decide what
  gets named.

* Points that land in low-density gaps come back `Unlabelled`, per layer and
  recomputed independently at each. That is the unnamed space between named
  places, not a failure to classify, and it is **kept** in the output. The probe's
  ~40% HDBSCAN noise fraction is not an argument against this approach — a point
  with no name of its own still sits inside the named region above it.

Layer order follows Toponymy's own convention: index 0 is the finest layer (most,
smallest regions), index -1 the coarsest.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Must be set before numba is imported, so it sits above every other import here.
# torch ships its own OpenMP runtime; once it is loaded, numba's default OpenMP
# threading layer segfaults inside fast_hdbscan's kdtree — reliably, on the very
# first clustering call. Numba's own workqueue pool avoids the second runtime
# entirely and stays multi-threaded (NUMBA_NUM_THREADS=1 also "fixes" it, by
# serialising; KMP_DUPLICATE_LIB_OK does not fix it at all).
os.environ.setdefault("NUMBA_THREADING_LAYER", "workqueue")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build.common import corpus_paths, fmt_eta  # noqa: E402
from probe.common import write_parquet  # noqa: E402

OBJECT_DESCRIPTION = "museum"
CORPUS_DESCRIPTION = (
    "museums from every country in the world, each described by the lead section "
    "of its Wikipedia article. Articles are in many languages."
)

# These names are rendered as labels on a map, where they compete for space with
# their neighbours — a name that reads well in a list ("Regional and Specialized
# Museums Across Kazakhstan, Russia, and International Locations") is unusable at
# 20 characters per line. Without this instruction the default names run to 12-15
# words. Every object in the corpus is a museum, so saying so carries no
# information and just costs width.
NAME_INSTRUCTIONS = (
    "These topic names will be rendered as labels on a map, so they must be SHORT: "
    "at most five words, and ideally two or three. Name the subject matter, not the "
    "container: write 'Narrow-Gauge Railways', not 'Heritage and Tourist Narrow Gauge "
    "Railway Museums Preserving Industrial Transport History'. Every object in this "
    "corpus is a museum, so do not use the word 'museum' unless it is genuinely "
    "distinguishing. Avoid filler adjectives such as 'Regional and Specialized', "
    "'Various', or 'Diverse'. Keep a geographic qualifier only when the region is "
    "what actually distinguishes the group."
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="fixture")
    ap.add_argument("--llm-model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--min-cluster-size", type=int, default=10)
    ap.add_argument("--tag", default="", help="suffix for the output files, e.g. a model name")
    ap.add_argument("--long-names", action="store_true",
                    help="drop the brevity instruction and take Toponymy's default naming")
    args = ap.parse_args()

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY is not set")

    import torch
    from sentence_transformers import SentenceTransformer
    from toponymy import Toponymy, ToponymyClusterer
    from toponymy.llm_wrappers import AsyncAnthropicNamer

    leads_path, out_dir = corpus_paths(args.corpus)
    leads = pd.read_parquet(leads_path).sort_values("qid").reset_index(drop=True)
    qids = np.load(out_dir / "qids.npy", allow_pickle=True)
    coords = pd.read_parquet(out_dir / "coords.parquet")

    centered_path = out_dir / "emb_centered.npy"
    emb = np.load(centered_path if centered_path.exists() else out_dir / "emb.npy")
    print(f"using {'centred' if centered_path.exists() else 'RAW'} embeddings {emb.shape}")

    assert (coords.qid.to_numpy() == qids).all(), "coords order drifted from embedding order"
    assert (leads.qid.to_numpy() == qids).all(), "leads order drifted from embedding order"
    # pandas hands back a Fortran-ordered block for a multi-column selection, and
    # fast_hdbscan's numba kdtree only has a definition for the C-ordered case.
    xy = np.ascontiguousarray(coords[["x", "y"]].to_numpy(), dtype=np.float32)

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    embedder = SentenceTransformer("BAAI/bge-m3", device=device)
    namer = AsyncAnthropicNamer(
        api_key=key,
        model=args.llm_model,
        max_concurrent_requests=args.concurrency,
        llm_specific_instructions=None if args.long_names else NAME_INSTRUCTIONS,
    )
    # Toponymy's verbose flag drives tqdm bars as well as its status lines, and a
    # bar redirected to a log file writes one line per update — at full-corpus
    # scale that is tens of thousands of lines burying every real message.
    verbose = sys.stdout.isatty()
    clusterer = ToponymyClusterer(base_min_cluster_size=args.min_cluster_size, verbose=verbose)

    model = Toponymy(
        llm_wrapper=namer,
        text_embedding_model=embedder,
        clusterer=clusterer,
        object_description=OBJECT_DESCRIPTION,
        corpus_description=CORPUS_DESCRIPTION,
        verbose=verbose,
    )

    print(f"corpus={args.corpus}  n={len(leads):,}  llm={args.llm_model}  "
          f"concurrency={args.concurrency}")
    t0 = time.monotonic()
    model.fit(
        objects=leads.text.fillna("").tolist(),
        embedding_vectors=emb,
        clusterable_vectors=xy,
    )
    elapsed = time.monotonic() - t0
    tag = f"_{args.tag}" if args.tag else ""

    # topic_names_[0] is the FINEST layer; [-1] the coarsest.
    names = [list(layer) for layer in model.topic_names_]
    # One naming call per cluster per layer, plus a disambiguation pass, so the
    # cluster total is the cost driver. AsyncAnthropicNamer does not support the
    # debug callback, so this is counted rather than observed.
    n_clusters = sum(len(layer) for layer in names)
    words = [len(n.split()) for layer in names for n in layer]
    print(f"\ntoponymy fit: {fmt_eta(elapsed)}, {n_clusters} clusters named")
    print(f"name length: median {int(np.median(words))} words, max {max(words)}")

    (out_dir / f"topic_names{tag}.json").write_text(
        json.dumps({"layers_fine_to_coarse": names,
                    "llm_model": args.llm_model,
                    "clusters_named": n_clusters,
                    "brevity_instruction": not args.long_names,
                    "seconds": round(elapsed, 1)}, ensure_ascii=False, indent=2)
    )

    out = pd.DataFrame({"qid": qids})
    for i, layer in enumerate(model.cluster_layers_):
        # Keep Unlabelled: it is the unnamed gap between named regions at this
        # scale, and dropping it would silently shrink the map.
        out[f"layer{i}_name"] = np.asarray(layer.topic_name_vector, dtype=object)
        out[f"layer{i}_cluster"] = np.asarray(layer.cluster_labels, dtype="int32")
    write_parquet(out, out_dir / f"topics{tag}.parquet", expect_cols=["qid", "layer0_name"])

    print(f"\n{len(names)} layers, fine -> coarse:")
    for i, layer in enumerate(names):
        unl = float((out[f"layer{i}_name"] == "Unlabelled").mean())
        print(f"  layer {i}: {len(layer):>4} named regions, {unl:6.1%} Unlabelled")
    assert len(names[0]) >= len(names[-1]), "layer order is not fine -> coarse"

    print("\ncoarsest layer:")
    for n in names[-1]:
        print(f"  - {n}")
    print(f"\nfinest layer, first 25 of {len(names[0])}:")
    for n in names[0][:25]:
        print(f"  - {n}")


if __name__ == "__main__":
    main()
