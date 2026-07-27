"""Stage 10 — can language actually be removed? Ground-truth test.

The problem with judging a de-biasing transform by "did language ARI drop" is
that language ARI drops by construction — you subtracted the language means, so
of course the language clusters loosen. It proves nothing about whether the
*museum* survived.

This stage uses a ground truth that does not depend on any clustering metric.
1,113 museums in the sample have articles in two or more languages. Those are the
same institution described twice. If a representation is language-neutral, the
German and the Japanese article about one museum should retrieve each other.

  query   = one article
  pool    = every other article (all 6,885, including same-language distractors,
            because their crowding is precisely the effect being measured)
  correct = any other article about the same museum, necessarily in another language

Reported per transform:
  * P@1 / MRR / Recall@10 for that retrieval
  * crowding - of the articles that outrank the true match, what share are in the
    query's own language? This is the direct read on "language is in the way"
  * what happens to language and to country k-NN purity as collateral

Transforms compared:
  raw       L2-normalised embeddings
  centered  per-language centroid subtraction, leave-one-out and shrunk toward
            the global mean. LOO matters: 28 languages here have exactly one
            museum, and subtracting a singleton's own centroid maps it precisely
            onto the origin, manufacturing a cluster out of nothing.
  inlp      iterative nullspace projection: fit a linear language classifier,
            project onto its nullspace, repeat. Removes linear language
            information far more thoroughly than a rank-1-per-group mean shift.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from museum_map.common import INTERIM, PROCESSED, SEED  # noqa: E402
from museum_map.debias import centered, inlp, l2  # noqa: E402

INLP_ITERS = 3
K_NN = 10


# ------------------------------------------------------------------ evaluation


def knn_purity(X: np.ndarray, y: np.ndarray, k: int = K_NN) -> tuple[float, float]:
    S = X @ X.T
    np.fill_diagonal(S, -np.inf)
    idx = np.argpartition(-S, kth=k, axis=1)[:, :k]
    same = float((y[idx] == y[:, None]).mean())
    p = pd.Series(y).value_counts(normalize=True).to_numpy()
    return same, float((p**2).sum())


def retrieval(
    X: np.ndarray, qid: np.ndarray, lang: np.ndarray, name_shared: np.ndarray | None = None
) -> dict:
    """Rank of the best same-museum article, computed without a full sort."""
    S = X @ X.T
    np.fill_diagonal(S, -np.inf)

    by_museum: dict[str, np.ndarray] = {
        q: np.flatnonzero(qid == q) for q in np.unique(qid)
    }
    ranks, crowd, shared = [], [], []
    for i in range(len(X)):
        pos = by_museum[qid[i]]
        pos = pos[pos != i]
        if len(pos) == 0:
            continue  # museum has only one article: no ground truth available
        best = S[i, pos].max()
        above = S[i] > best
        ranks.append(1 + int(above.sum()))
        crowd.append(float((lang[above] == lang[i]).mean()) if above.any() else np.nan)
        shared.append(bool(name_shared[i]) if name_shared is not None else False)

    r = np.array(ranks, dtype=float)
    c = np.array(crowd, dtype=float)
    sh = np.array(shared, dtype=bool)
    out = {
        "n_queries": int(len(r)),
        "p_at_1": float((r == 1).mean()),
        "recall_at_10": float((r <= 10).mean()),
        "mrr": float((1.0 / r).mean()),
        "median_rank": float(np.median(r)),
        "crowding_same_language": float(np.nanmean(c)),
    }
    # Name-overlap control: the same museum's articles usually repeat its proper
    # name verbatim across languages, so retrieval could be string matching
    # dressed up as semantics. Split the queries and see.
    if name_shared is not None and sh.any() and (~sh).any():
        out["name_shared"] = {
            "n": int(sh.sum()),
            "p_at_1": float((r[sh] == 1).mean()),
            "mrr": float((1.0 / r[sh]).mean()),
        }
        out["name_absent"] = {
            "n": int((~sh).sum()),
            "p_at_1": float((r[~sh] == 1).mean()),
            "mrr": float((1.0 / r[~sh]).mean()),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="intfloat/multilingual-e5-large")
    ap.add_argument("--batch-size", type=int, default=32)
    args = ap.parse_args()
    tag = args.model.split("/")[-1]

    al = pd.read_parquet(INTERIM / "leads_all.parquet").sort_values(["qid", "lang"])
    al = al.reset_index(drop=True)
    sample = pd.read_parquet(INTERIM / "sample.parquet")[
        ["qid", "country_label", "type_label", "label", "has_label"]
    ]
    al = al.merge(sample, on="qid", how="left")

    per = al.groupby("qid").lang.nunique()
    multi = int((per >= 2).sum())
    print(f"{len(al):,} articles, {al.qid.nunique():,} museums, "
          f"{multi:,} with >=2 languages, {al.lang.nunique()} languages")

    # ---- embed every article (cached) --------------------------------------
    emb_path = PROCESSED / f"emb_{tag}_parallel.npy"
    if emb_path.exists():
        X = np.load(emb_path)
        print(f"loaded cached embeddings {X.shape}")
        assert len(X) == len(al), f"cache is stale: {len(X)} != {len(al)}"
    else:
        import torch
        from sentence_transformers import SentenceTransformer

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        model = SentenceTransformer(args.model, device=device)
        prefix = "query: " if "e5" in args.model.lower() else ""
        X = model.encode(
            [prefix + t for t in al.text],
            batch_size=args.batch_size,
            normalize_embeddings=True,
            show_progress_bar=True,
            convert_to_numpy=True,
        ).astype(np.float32)
        tmp = emb_path.with_name(emb_path.name + ".tmp")
        with open(tmp, "wb") as fh:
            np.save(fh, X)
        tmp.replace(emb_path)
        print(f"embedded {X.shape} -> {emb_path.name}")

    X = l2(X.astype(np.float32))
    qid = al.qid.to_numpy()
    lang = al.lang.to_numpy()
    country = al.country_label.fillna("(unknown)").to_numpy()

    # Does the museum's own name appear verbatim in this article AND in at least
    # one of its other-language articles? Only meaningful where Wikidata has a
    # real label (otherwise `label` is just the QID and never matches).
    lower = al.text.str.lower().to_numpy()
    lbl = al.label.fillna("").str.lower().to_numpy()
    ok = al.has_label.fillna(False).to_numpy()
    has_name = np.array([bool(o) and len(m) > 2 and m in t
                         for t, m, o in zip(lower, lbl, ok)])
    by_m = {q: np.flatnonzero(qid == q) for q in np.unique(qid)}
    name_shared = np.array([
        has_name[i] and bool(has_name[by_m[qid[i]][by_m[qid[i]] != i]].any())
        for i in range(len(al))
    ])
    print(f"queries whose museum name appears in both articles: {name_shared.mean():.1%}")

    # ---- transforms --------------------------------------------------------
    print("\nbuilding transforms...")
    t0 = time.time()
    Xc = centered(X, lang)
    print(f"  centered: {time.time() - t0:.0f}s")
    t0 = time.time()
    Xi, removed, accs = inlp(X, lang, INLP_ITERS)
    print(f"  inlp: {time.time() - t0:.0f}s, {removed} of {X.shape[1]} dims removed")

    spaces = {"raw": X, "centered": Xc, "inlp": Xi}

    # ---- evaluate ----------------------------------------------------------
    results: dict = {
        "model": args.model,
        "n_articles": int(len(al)),
        "n_museums": int(al.qid.nunique()),
        "n_museums_multilingual": multi,
        "n_languages": int(al.lang.nunique()),
        "inlp_dims_removed": int(removed),
        "inlp_dims_total": int(X.shape[1]),
        "inlp_train_acc_per_iter": accs,
        "spaces": {},
    }
    print(f"\n{'space':<10}{'P@1':>8}{'R@10':>8}{'MRR':>8}{'medRank':>9}"
          f"{'crowd':>8} | {'langKNN':>8}{'chance':>8} | {'ctryKNN':>8}{'chance':>8}")
    for name, M in spaces.items():
        ret = retrieval(M, qid, lang, name_shared)
        lp, lc = knn_purity(M, lang)
        cp, cc = knn_purity(M, country)
        results["spaces"][name] = {
            **ret,
            "language_knn_purity": lp,
            "language_knn_chance": lc,
            "country_knn_purity": cp,
            "country_knn_chance": cc,
        }
        print(f"{name:<10}{ret['p_at_1']:>8.3f}{ret['recall_at_10']:>8.3f}{ret['mrr']:>8.3f}"
              f"{ret['median_rank']:>9.0f}{ret['crowding_same_language']:>8.2f} | "
              f"{lp:>8.3f}{lc:>8.3f} | {cp:>8.3f}{cc:>8.3f}")

    out = PROCESSED / f"parallel_{tag}.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {out}")

    # 2D layouts so the report can show the language blobs dissolving.
    import umap

    frames = []
    for name, M in spaces.items():
        t0 = time.time()
        r2 = umap.UMAP(
            n_components=2, n_neighbors=15, min_dist=0.1, metric="cosine", random_state=SEED
        ).fit_transform(M)
        frames.append(pd.DataFrame({"space": name, "qid": qid, "lang": lang,
                                    "x": r2[:, 0], "y": r2[:, 1]}))
        print(f"  umap {name}: {time.time() - t0:.0f}s")
    cpath = PROCESSED / f"parallel_coords_{tag}.parquet"
    pd.concat(frames, ignore_index=True).to_parquet(cpath, index=False)
    print(f"wrote {cpath}")


if __name__ == "__main__":
    main()
