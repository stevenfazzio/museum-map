"""Build 14 — does the probe's verdict survive at full scale?

The probe answered its go/no-go question on 2,000 museums. This re-asks the same
questions of the built map, on whatever corpus it was built from, so the report
can say whether the conclusions replicated or were an artefact of the sample.

Every metric here is deliberately the same one the probe used, so the numbers are
comparable to `probe/reports/`:

* ARI of the discovered regions against country / type / language. ARI compares
  partitions and is punished when ~50 regions meet ~200 countries, so it is
  reported next to 10-NN label purity (against `sum p_i^2` chance) and a
  cross-validated linear probe (against the majority baseline), which answer
  "is the neighbourhood geographic?" without a clustering step in between.

* The type probe is run on *specifically-typed* museums only. Half the corpus
  carries just the generic `museum` P31, so an all-museums probe scores exactly
  the majority baseline and reads as "no signal" whatever the embedding holds.

* The local<->universal axis: median *great-circle* distance to a museum's 10
  nearest *embedding* neighbours, aggregated by type. Small means its peers are
  down the road, large means they are everywhere. The probe found local/
  ethnographic/archaeological at one end and military/railway/natural-history at
  the other.

It also measures something the probe could not: how the corpus's stub tail —
museums whose article is one sentence — lands on the map.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from pathlib import Path

os.environ.setdefault("NUMBA_THREADING_LAYER", "workqueue")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common import corpus_paths  # noqa: E402
from museum_map.common import SEED  # noqa: E402

PROBE_CAP = 25_000  # rows fed to the linear probe; full-corpus lbfgs is otherwise slow
NN_K = 10
EARTH_KM = 6371.0088


def haversine_pairs(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Great-circle km between paired coordinates (NaN propagates)."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dlat, dlon = p2 - p1, np.radians(lon2) - np.radians(lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def haversine_to_neighbours(lat, lon, nn_idx: np.ndarray) -> np.ndarray:
    """Median great-circle km from each point to its listed neighbours."""
    d = haversine_pairs(lat[:, None], lon[:, None], lat[nn_idx], lon[nn_idx])
    # A museum with no coordinates, or whose every neighbour lacks them, has no
    # radius. nanmedian warns once per all-NaN row and returns NaN, which is the
    # wanted answer — so the warning is silenced rather than the value filled in.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(d, axis=1)


def purity(idx: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    """Mean share of a point's K neighbours sharing its label, and the chance rate."""
    neigh = labels[idx[:, 1:]]  # column 0 is the point itself
    hit = (neigh == labels[:, None]).mean()
    p = pd.Series(labels).value_counts(normalize=True).to_numpy()
    return float(hit), float((p**2).sum())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="fixture")
    ap.add_argument("--tag", default="short")
    args = ap.parse_args()

    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import adjusted_rand_score
    from sklearn.model_selection import cross_val_score
    from sklearn.neighbors import NearestNeighbors

    leads_path, out_dir = corpus_paths(args.corpus)
    leads = pd.read_parquet(leads_path).sort_values("qid").reset_index(drop=True)
    topics = pd.read_parquet(out_dir / f"topics_{args.tag}.parquet")
    emb = np.load(out_dir / "emb_centered.npy")
    assert (topics.qid.to_numpy() == leads.qid.to_numpy()).all(), "topics/leads order drift"

    if "type_label" not in leads.columns:
        tp = leads_path.parent / "types.parquet"
        if tp.exists():
            leads = leads.merge(pd.read_parquet(tp)[["qid", "type_label"]], on="qid", how="left")
    leads["type_label"] = leads.get("type_label", pd.Series([""] * len(leads))).fillna("other")

    res: dict = {"corpus": args.corpus, "n": int(len(leads)), "tag": args.tag}
    print(f"corpus={args.corpus}  n={len(leads):,}")

    country = leads.country_label.fillna("unknown").to_numpy()
    lang = leads.lang.fillna("unknown").to_numpy()
    type_lab = leads.type_label.to_numpy()

    # ---- ARI of discovered regions against the three candidate explanations ----
    layer_cols = sorted([c for c in topics.columns if c.endswith("_cluster")],
                        key=lambda c: int(c.removeprefix("layer").removesuffix("_cluster")))
    res["ari"] = {}
    print("\nARI of discovered regions vs:")
    for c in layer_cols:
        lab = topics[c].to_numpy()
        row = {
            "country": float(adjusted_rand_score(country, lab)),
            "type": float(adjusted_rand_score(type_lab, lab)),
            "language": float(adjusted_rand_score(lang, lab)),
            "n_clusters": int(lab.max() + 1),
            "noise_frac": float((lab == -1).mean()),
        }
        res["ari"][c] = row
        print(f"  {c}: country {row['country']:+.3f}  type {row['type']:+.3f}  "
              f"language {row['language']:+.3f}   ({row['n_clusters']} clusters)")

    # ---- 10-NN label purity in the embedding space ----------------------------
    print(f"\n{NN_K}-NN purity (vs chance):")
    nn = NearestNeighbors(n_neighbors=NN_K + 1, metric="cosine").fit(emb)
    _, idx = nn.kneighbors(emb)
    res["purity"] = {}
    for nm, lab in (("country", country), ("type", type_lab), ("language", lang)):
        got, chance = purity(idx, lab)
        res["purity"][nm] = {"purity": got, "chance": chance}
        print(f"  {nm:<9} {got:.3f}  (chance {chance:.3f})")

    # ---- linear probe for type, on specifically-typed museums only -------------
    specific = leads.type_label.notna() & ~leads.type_label.isin(["museum", "other", ""])
    n_spec = int(specific.sum())
    print(f"\ntype probe on {n_spec:,} specifically-typed museums "
          f"({n_spec / len(leads):.1%} of corpus):")
    if n_spec > 200:
        rng = np.random.default_rng(SEED)
        sel = np.flatnonzero(specific.to_numpy())
        capped = len(sel) > PROBE_CAP
        if capped:
            sel = np.sort(rng.choice(sel, PROBE_CAP, replace=False))
        y = type_lab[sel]
        base = float(pd.Series(y).value_counts(normalize=True).iloc[0])
        scores = cross_val_score(
            LogisticRegression(max_iter=1000, n_jobs=-1), emb[sel], y, cv=3, n_jobs=1
        )
        res["type_probe"] = {"acc": float(scores.mean()), "baseline": base,
                             "n": int(len(sel)), "capped": bool(capped)}
        print(f"  accuracy {scores.mean():.3f} vs majority baseline {base:.3f}"
              + (f"  (subsampled to {PROBE_CAP:,})" if capped else ""))

    # ---- local <-> universal axis ---------------------------------------------
    # Median *great-circle* distance to the 10 nearest EMBEDDING neighbours, which
    # is the probe's definition. Small = its peers are down the road (a local-history
    # museum); large = its peers are worldwide (a railway museum). Note this is not
    # cosine distance to those neighbours, which measures embedding density instead
    # and answers a different question entirely.
    #
    # The probe materialised the full N x N haversine matrix; at 49k that is 9.7 GB.
    # Only the 10 neighbour distances per museum are needed, so they are computed
    # directly and the matrix never exists.
    lat, lon = leads.lat.to_numpy(), leads.lon.to_numpy()
    radius_km = haversine_to_neighbours(lat, lon, idx[:, 1:])
    leads["radius_km"] = radius_km
    have_geo = np.isfinite(radius_km)
    rng = np.random.default_rng(SEED)
    have = np.flatnonzero(np.isfinite(lat) & np.isfinite(lon))
    a, b = rng.choice(have, 200_000), rng.choice(have, 200_000)
    rand_med = float(np.nanmedian(haversine_pairs(lat[a], lon[a], lat[b], lon[b])))
    res["radius_km"] = {
        "median": float(np.nanmedian(radius_km)),
        "random_pair_median": rand_med,
        "coverage": float(have_geo.mean()),
    }
    print(f"\nlocal <-> universal: median neighbourhood radius "
          f"{np.nanmedian(radius_km):,.0f} km vs {rand_med:,.0f} km random-pair baseline "
          f"({np.nanmedian(radius_km) / rand_med:.2f}x); {have_geo.mean():.1%} have coordinates")

    by_type = (leads[specific.to_numpy() & have_geo]
               .groupby("type_label").radius_km.agg(["median", "size"])
               .query("size >= 30").sort_values("median"))
    res["radius_by_type"] = {k: float(v) for k, v in by_type["median"].items()}
    n_show = min(6, len(by_type) // 2)
    print("  most locally rooted:")
    for k, r in by_type.head(n_show).iterrows():
        print(f"    {k:<28} {r['median']:>7,.0f} km  (n={int(r['size'])})")
    print("  most internationally legible:")
    for k, r in by_type.tail(n_show).iloc[::-1].iterrows():
        print(f"    {k:<28} {r['median']:>7,.0f} km  (n={int(r['size'])})")

    # ---- the stub tail ---------------------------------------------------------
    fine = topics[layer_cols[0]].to_numpy()
    bins = pd.cut(leads.chars, [0, 150, 300, 600, 1200, 10**9],
                  labels=["<150", "150-300", "300-600", "600-1200", "1200+"])
    stub = pd.DataFrame({"bin": bins, "unlabelled": fine == -1, "radius_km": radius_km})
    tab = stub.groupby("bin", observed=True).agg(
        n=("unlabelled", "size"), unlabelled=("unlabelled", "mean"),
        median_radius_km=("radius_km", "median"))
    res["by_lead_length"] = tab.to_dict("index")
    print("\nlead length vs how the map treats it:")
    print(f"  {'chars':<10} {'n':>7} {'unlabelled':>11} {'radius km':>11}")
    for k, r in tab.iterrows():
        print(f"  {k:<10} {int(r['n']):>7} {r['unlabelled']:>10.1%} "
              f"{r['median_radius_km']:>11,.0f}")

    out = out_dir / f"analysis_{args.tag}.json"
    out.write_text(json.dumps(res, indent=2, default=str))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
