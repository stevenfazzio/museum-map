"""Stage 08 — how much of the embedding structure is just metadata?

Labels tested: country, museum type, and — added after the first run made it
necessary — the language the lead is written in. Language turned out to be the
dominant axis by a wide margin (ARI ~0.77 vs ~0.08 for country), so without it
the country numbers are unattributable: language tracks country closely, and the
lead comes from whichever Wikipedia had the longest article.

For each variant, on each of three row subsets (see `subsets` below):

  * UMAP -> 10D for clustering, 2D for plotting (random_state fixed: UMAP is
    otherwise non-deterministic and the report would not reproduce)
  * HDBSCAN on the 10D projection
  * ARI / AMI of clusters against country and against type
  * silhouette using country (and type) as the label, in cosine space and in 2D

ARI alone is a weak instrument here: it compares two *partitions*, and ~40
clusters against ~150 countries is penalised for the cardinality mismatch even if
the space is strongly geographic. So two directly interpretable measures are
added, both reported against their chance baselines:

  * k-NN label purity - of a museum's 10 nearest neighbours, what share share its
    country? Chance = sum(p_i^2). This answers "is the neighbourhood geographic?"
    without any clustering step in between.
  * linear probe - cross-validated accuracy of logistic regression predicting
    country from the embedding. This is the ceiling on recoverable metadata.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    adjusted_mutual_info_score,
    adjusted_rand_score,
    silhouette_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.neighbors import NearestNeighbors

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from museum_map.common import INTERIM, PROCESSED, SEED  # noqa: E402
from museum_map.debias import centered  # noqa: E402

VARIANTS = ["a_full", "b_nofirst", "c_noloc"]
K_NN = 10
MIN_CLASS = 5


def knn_purity(X: np.ndarray, y: np.ndarray, k: int = K_NN) -> tuple[float, float]:
    """Mean share of a point's k nearest neighbours carrying the same label, and chance."""
    nn = NearestNeighbors(n_neighbors=k + 1, metric="cosine").fit(X)
    _, idx = nn.kneighbors(X)
    same = (y[idx[:, 1:]] == y[:, None]).mean()
    p = pd.Series(y).value_counts(normalize=True).to_numpy()
    return float(same), float((p**2).sum())


def linear_probe(X: np.ndarray, y: np.ndarray, seed: int = SEED) -> dict:
    """Cross-validated accuracy of predicting the label from the embedding."""
    s = pd.Series(y)
    keep = s.isin(s.value_counts()[lambda c: c >= MIN_CLASS].index).to_numpy()
    Xf, yf = X[keep], y[keep]
    if len(np.unique(yf)) < 2:
        return {"accuracy": None, "baseline": None, "n": int(keep.sum()), "n_classes": 0}
    Xp = PCA(n_components=min(128, Xf.shape[1], Xf.shape[0] - 1), random_state=seed).fit_transform(Xf)
    clf = LogisticRegression(max_iter=2000, C=1.0)
    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=seed)
    acc = cross_val_score(clf, Xp, yf, cv=cv, scoring="accuracy", n_jobs=-1).mean()
    base = pd.Series(yf).value_counts(normalize=True).iloc[0]
    return {
        "accuracy": float(acc),
        "baseline": float(base),
        "n": int(keep.sum()),
        "n_classes": int(len(np.unique(yf))),
    }


def analyse(X: np.ndarray, meta: pd.DataFrame, seed: int = SEED) -> tuple[dict, pd.DataFrame]:
    import umap

    country = meta.country_label.to_numpy()
    mtype = meta.type_label.to_numpy()
    # The lead is written in whichever Wikipedia had the longest article, and
    # language correlates hard with country. Without measuring it, any "country"
    # signal is unattributable: it could just be "which language this text is in".
    language = meta.lang.to_numpy()

    red10 = umap.UMAP(n_components=10, n_neighbors=15, min_dist=0.0,
                      metric="cosine", random_state=seed).fit_transform(X)
    red2 = umap.UMAP(n_components=2, n_neighbors=15, min_dist=0.1,
                     metric="cosine", random_state=seed).fit_transform(X)

    labels = HDBSCAN(min_cluster_size=15, min_samples=5).fit_predict(red10)
    clustered = labels >= 0
    n_clusters = int(len(set(labels[clustered])))

    def both(y):
        """ARI/AMI with noise kept as its own group, and over clustered points only."""
        out = {
            "ari_all": float(adjusted_rand_score(y, labels)),
            "ami_all": float(adjusted_mutual_info_score(y, labels)),
        }
        if clustered.sum() > 1 and len(set(labels[clustered])) > 1:
            out["ari_clustered"] = float(adjusted_rand_score(y[clustered], labels[clustered]))
            out["ami_clustered"] = float(adjusted_mutual_info_score(y[clustered], labels[clustered]))
        else:
            out["ari_clustered"] = out["ami_clustered"] = None
        return out

    def sil(y):
        if len(set(y)) < 2:
            return {"cosine": None, "umap2d": None}
        return {
            "cosine": float(silhouette_score(X, y, metric="cosine")),
            "umap2d": float(silhouette_score(red2, y, metric="euclidean")),
        }

    p_country, c_country = knn_purity(X, country)
    p_type, c_type = knn_purity(X, mtype)
    p_lang, c_lang = knn_purity(X, language)

    res = {
        "n": int(len(X)),
        "n_clusters": n_clusters,
        "noise_fraction": float((~clustered).mean()),
        "n_countries": int(len(set(country))),
        "n_types": int(len(set(mtype))),
        "n_languages": int(len(set(language))),
        "language": {
            **both(language),
            "silhouette": sil(language),
            "knn_purity": p_lang,
            "knn_chance": c_lang,
            "probe": linear_probe(X, language, seed),
        },
        "country": {
            **both(country),
            "silhouette": sil(country),
            "knn_purity": p_country,
            "knn_chance": c_country,
            "probe": linear_probe(X, country, seed),
        },
        "type": {
            **both(mtype),
            "silhouette": sil(mtype),
            "knn_purity": p_type,
            "knn_chance": c_type,
            "probe": linear_probe(X, mtype, seed),
        },
    }

    # The type label is degenerate: ~62% of museums carry only the generic
    # "museum" P31, so a classifier hits the majority baseline by predicting one
    # class and the whole type test reads as "no signal" regardless of the
    # embedding. Re-run type against only the specifically-typed museums, which
    # is the question actually being asked.
    generic = pd.Series(mtype).mode().iloc[0]
    specific = ~pd.Series(mtype).isin({generic, "other"}).to_numpy()
    if specific.sum() > 50 and len(set(mtype[specific])) > 1:
        p_sp, c_sp = knn_purity(X[specific], mtype[specific])
        res["type_specific"] = {
            "n": int(specific.sum()),
            "excluded_labels": [generic, "other"],
            "n_types": int(len(set(mtype[specific]))),
            "ari_all": float(adjusted_rand_score(mtype[specific], labels[specific])),
            "ami_all": float(adjusted_mutual_info_score(mtype[specific], labels[specific])),
            "silhouette": {
                "cosine": float(silhouette_score(X[specific], mtype[specific], metric="cosine")),
                "umap2d": float(
                    silhouette_score(red2[specific], mtype[specific], metric="euclidean")
                ),
            },
            "knn_purity": p_sp,
            "knn_chance": c_sp,
            "probe": linear_probe(X[specific], mtype[specific], seed),
        }
    else:
        res["type_specific"] = None

    coords = meta[["qid", "country_label", "type_label", "lang", "chars"]].copy()
    coords["x"], coords["y"] = red2[:, 0], red2[:, 1]
    coords["cluster"] = labels
    return res, coords


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="intfloat/multilingual-e5-large")
    ap.add_argument("--center", action="store_true",
                    help="per-language centre the embeddings before analysing")
    args = ap.parse_args()
    tag = args.model.split("/")[-1] + ("_centered" if args.center else "")

    v = pd.read_parquet(INTERIM / "variants.parquet")
    qids = np.load(PROCESSED / "qids.npy", allow_pickle=True)
    assert list(qids) == list(v.qid), "embedding row order does not match variants.parquet"

    common = v.usable_all.to_numpy()
    chars = v.chars.to_numpy()
    q1 = np.quantile(chars, 0.25)

    # Three subsets, because the obvious single choice is biased either way:
    #   own      - each variant on its own usable rows. Faithful per-variant read,
    #              but (b) loses every single-sentence lead so its n is smaller.
    #   common   - all three restricted to the same museums, so the three numbers
    #              are directly comparable; skews long, since dropping the
    #              single-sentence leads removes the shortest stubs.
    #   drop_q1  - common subset minus the shortest length quartile.
    # `None` means "use this variant's own usable mask".
    subsets: dict[str, np.ndarray | None] = {
        "own": None,
        "common": common,
        "drop_shortest_quartile": common & (chars > q1),
    }
    print(f"rows: {len(v):,} total | common subset {common.sum():,} | "
          f"shortest-quartile cut at {q1:.0f} chars -> "
          f"{subsets['drop_shortest_quartile'].sum():,}")

    results: dict = {
        "model": args.model,
        "centered": bool(args.center),
        "shortest_quartile_char_cutoff": float(q1),
        "length_distribution": {
            k: float(x) for k, x in v["chars"]
            .describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]).items()
        },
        "language_distribution": v["lang"].value_counts().head(20).to_dict(),
        # How many museums have an English article at all (not just where English
        # happened to be the longest) — the coverage cost of an English-only corpus.
        "english_available": int(
            pd.read_parquet(INTERIM / "leads_all.parquet")
            .query("lang == 'en'")
            .qid.nunique()
        ),
        "stripping": {
            "mean_frac_chars_removed": float(v["frac_removed_noloc"].mean()),
            "median_frac_chars_removed": float(v["frac_removed_noloc"].median()),
            "museum_name_removed_share": float(v["label_hit"].mean()),
        },
        "variants": {},
    }

    for variant in VARIANTS:
        X_all = np.load(PROCESSED / f"emb_{args.model.split(chr(47))[-1]}_{variant}.npy")
        if args.center:
            X_all = centered(X_all, v["lang"].to_numpy())
        own = v[f"usable_{variant[0]}"].to_numpy()
        results["variants"][variant] = {}
        for sname, spec in subsets.items():
            mask = own if spec is None else spec
            t0 = time.time()
            res, coords = analyse(X_all[mask], v[mask].reset_index(drop=True))
            results["variants"][variant][sname] = res
            if sname == "own":
                coords.to_parquet(PROCESSED / f"coords_{tag}_{variant}.parquet", index=False)
            c = res["country"]
            print(
                f"  {variant:<11} {sname:<24} n={res['n']:<5} clusters={res['n_clusters']:<4} "
                f"noise={res['noise_fraction']:.0%}  ARI_country={c['ari_all']:+.3f}  "
                f"knn={c['knn_purity']:.3f} (chance {c['knn_chance']:.3f})  [{time.time() - t0:.0f}s]"
            )

    out = PROCESSED / f"metrics_{tag}.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
