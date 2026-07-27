"""Stage 11 — how does embedding distance relate to distance on the ground?

Country ARI came out near zero, which reads as "geography is not in the
embedding". That was the wrong instrument, not the right answer: ARI compares
*partitions*, and geography is a continuous gradient. Embedding neighbours are in
fact several times closer on the ground than chance.

So this measures the continuous relationship directly:

  * decay curve - mean cosine similarity binned by great-circle distance, against
    a permutation null (coordinates shuffled, both marginals preserved). Flat
    means no geographic effect; a downward slope means near museums are more
    alike.
  * within-country curve - the same restricted to same-country pairs. If the
    decay survives there, distance matters beyond national borders rather than
    "country" doing all the work.
  * raw vs language-centred - geography and language are confounded (neighbours
    on the ground share a Wikipedia edition), so the honest question is how much
    geographic structure survives language removal.
  * neighbourhood radius per museum - median great-circle distance to a museum's
    10 nearest embedding neighbours. Small = locally rooted (its peers are down
    the road); large = internationally legible (its peers are everywhere). This
    is the local/universal axis, derived *from* geography rather than by erasing
    it.

Deliberately not done here: residualising geography out of the embeddings. Unlike
language — a corpus artefact introduced by the "longest article" sampling rule,
and checkable against parallel articles — location is constitutive of what a
museum is, and there is no "same museum, different place" oracle to verify that
removal took the confound rather than the content.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from museum_map.common import INTERIM, PROCESSED, SEED, write_parquet  # noqa: E402
from museum_map.debias import centered, l2  # noqa: E402

EARTH_KM = 6371.0088
K_NN = 10
N_PERM = 50
# Two bins per decade, plus a "same site" bucket below 1 km.
BIN_EDGES = np.array([0.0, 1.0, 3.16, 10.0, 31.6, 100.0, 316.0, 1000.0,
                      3162.0, 10000.0, 20100.0])


def haversine_matrix(lat_deg: np.ndarray, lon_deg: np.ndarray) -> np.ndarray:
    lat = np.radians(lat_deg)
    lon = np.radians(lon_deg)
    dlat = lat[:, None] - lat[None, :]
    dlon = lon[:, None] - lon[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(lat)[:, None] * np.cos(lat)[None, :] * np.sin(dlon / 2) ** 2
    return (2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))).astype(np.float32)


def binned_mean(values: np.ndarray, bin_idx: np.ndarray, n_bins: int) -> np.ndarray:
    total = np.bincount(bin_idx, weights=values, minlength=n_bins)
    count = np.bincount(bin_idx, minlength=n_bins)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(count > 0, total / np.maximum(count, 1), np.nan)[:n_bins]


def curve(
    S: np.ndarray, bin_idx: np.ndarray, iu: tuple, n_bins: int, rng, n_perm: int = N_PERM
) -> dict:
    """Decay curve plus a permutation null envelope.

    The null shuffles which museum sits at which coordinate, which destroys the
    geography/embedding association while preserving both marginal distributions
    exactly. A flat observed curve inside the envelope means no geographic effect.
    """
    s_flat = S[iu].astype(np.float64)
    obs = binned_mean(s_flat, bin_idx, n_bins)
    counts = np.bincount(bin_idx, minlength=n_bins)[:n_bins]

    n = S.shape[0]
    null = np.empty((n_perm, n_bins))
    for p in range(n_perm):
        perm = rng.permutation(n)
        null[p] = binned_mean(S[perm[iu[0]], perm[iu[1]]].astype(np.float64), bin_idx, n_bins)

    return {
        "mean_similarity": [None if np.isnan(x) else float(x) for x in obs],
        "n_pairs": [int(c) for c in counts],
        "null_lo": [None if np.isnan(x) else float(x) for x in np.nanpercentile(null, 2.5, axis=0)],
        "null_hi": [None if np.isnan(x) else float(x) for x in np.nanpercentile(null, 97.5, axis=0)],
        "global_mean": float(s_flat.mean()),
    }


def mantel(S: np.ndarray, D: np.ndarray, iu: tuple, rng, n_perm: int = N_PERM) -> dict:
    """Correlation between log great-circle distance and embedding similarity."""
    d = np.log10(np.maximum(D[iu], 0.1)).astype(np.float64)
    s = S[iu].astype(np.float64)
    r = float(np.corrcoef(d, s)[0, 1])
    n = S.shape[0]
    null = np.empty(n_perm)
    for p in range(n_perm):
        perm = rng.permutation(n)
        null[p] = np.corrcoef(d, S[perm[iu[0]], perm[iu[1]]].astype(np.float64))[0, 1]
    return {
        "r": r,
        "null_mean": float(null.mean()),
        "null_sd": float(null.std()),
        "z": float((r - null.mean()) / max(null.std(), 1e-12)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="intfloat/multilingual-e5-large")
    args = ap.parse_args()
    tag = args.model.split("/")[-1]
    rng = np.random.default_rng(SEED)

    v = pd.read_parquet(INTERIM / "variants.parquet")
    has = v.lat.notna().to_numpy() & v.lon.notna().to_numpy()
    X_all = l2(np.load(PROCESSED / f"emb_{tag}_a_full.npy").astype(np.float32))
    # Centre on the full sample, then subset — the language centroids should be
    # estimated from every museum, not only the ones carrying coordinates.
    Xc_all = centered(X_all, v["lang"].to_numpy())

    g = v[has].reset_index(drop=True)
    X, Xc = X_all[has], Xc_all[has]
    n = len(g)
    print(f"{n:,} of {len(v):,} museums have coordinates ({has.mean():.1%})")

    D = haversine_matrix(g.lat.to_numpy(), g.lon.to_numpy())
    iu = np.triu_indices(n, k=1)
    n_bins = len(BIN_EDGES) - 1
    bin_idx = np.clip(np.digitize(D[iu], BIN_EDGES) - 1, 0, n_bins - 1)

    same_country = (g.country_label.to_numpy()[:, None] == g.country_label.to_numpy()[None, :])
    sc_flat = same_country[iu]
    print(f"{len(iu[0]):,} pairs; {sc_flat.sum():,} same-country "
          f"({sc_flat.mean():.1%}); median distance {np.median(D[iu]):,.0f} km")

    results: dict = {
        "model": args.model,
        "n_museums": int(n),
        "coord_coverage": float(has.mean()),
        "bin_edges_km": BIN_EDGES.tolist(),
        "spaces": {},
    }

    for name, M in [("raw", X), ("centered", Xc)]:
        S = M @ M.T
        results["spaces"][name] = {
            "all_pairs": curve(S, bin_idx, iu, n_bins, rng),
            "mantel": mantel(S, D, iu, rng),
        }
        # Same-country subset: does distance still matter inside one country?
        sub_idx = np.flatnonzero(sc_flat)
        sub_bins = bin_idx[sub_idx]
        s_sub = S[iu][sub_idx].astype(np.float64)
        results["spaces"][name]["same_country"] = {
            "mean_similarity": [
                None if np.isnan(x) else float(x)
                for x in binned_mean(s_sub, sub_bins, n_bins)
            ],
            "n_pairs": [int(c) for c in np.bincount(sub_bins, minlength=n_bins)[:n_bins]],
            "global_mean": float(s_sub.mean()),
        }
        m = results["spaces"][name]["mantel"]
        print(f"  {name:<9} mantel r={m['r']:+.4f} (null {m['null_mean']:+.4f}"
              f" +/- {m['null_sd']:.4f}, z={m['z']:+.1f})")

    # ---- neighbourhood radius: the local/universal axis ---------------------
    for name, M in [("raw", X), ("centered", Xc)]:
        S = M @ M.T
        np.fill_diagonal(S, -np.inf)
        nn = np.argpartition(-S, K_NN, axis=1)[:, :K_NN]
        g[f"radius_km_{name}"] = np.median(np.take_along_axis(D, nn, axis=1), axis=1)

    rand_med = float(np.median(D[iu]))
    results["random_pair_median_km"] = rand_med
    results["radius"] = {
        name: {
            "median": float(g[f"radius_km_{name}"].median()),
            "p10": float(g[f"radius_km_{name}"].quantile(0.10)),
            "p90": float(g[f"radius_km_{name}"].quantile(0.90)),
            "vs_random": float(g[f"radius_km_{name}"].median() / rand_med),
        }
        for name in ("raw", "centered")
    }

    by_type = (
        g.groupby("type_label")["radius_km_centered"]
        .agg(["median", "count"])
        .query("count >= 15")
        .sort_values("median")
    )
    results["radius_by_type"] = {
        k: {"median_km": float(r["median"]), "n": int(r["count"])}
        for k, r in by_type.iterrows()
    }

    out_cols = ["qid", "label", "country_label", "type_label", "lang", "lat", "lon",
                "radius_km_raw", "radius_km_centered"]
    write_parquet(g[out_cols], PROCESSED / f"geo_scores_{tag}.parquet", expect_cols=out_cols)

    path = PROCESSED / f"geo_{tag}.json"
    path.write_text(json.dumps(results, indent=2))
    print(f"\nrandom-pair median distance: {rand_med:,.0f} km")
    for name in ("raw", "centered"):
        r = results["radius"][name]
        print(f"  {name:<9} neighbourhood radius: median {r['median']:,.0f} km "
              f"({r['vs_random']:.2f}x random), p10 {r['p10']:,.0f} - p90 {r['p90']:,.0f}")
    print("\nneighbourhood radius by type (centered, n>=15) — local first:")
    for k, r in by_type.iterrows():
        print(f"  {k:<28}{r['median']:>9,.0f} km   (n={int(r['count'])})")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
