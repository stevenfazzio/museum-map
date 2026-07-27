"""Stage 02 — pick candidate museums per country.

The raw distribution is badly skewed (Italy 8.9k, Germany 8.5k, US 7.0k), so a
uniform random draw would be exactly the "60% US/DE/JP" map the experiment is
trying to avoid. Allocation is proportional to sqrt(n_country): it flattens the
long head without collapsing to a uniform draw that would give Vatican City the
same weight as Germany.

This stage only picks *candidates* (an oversample). Some museums have a sitelink
but no Wikipedia sitelink, so the final 2,000 is settled in s04 after s03 has
resolved which candidates really have articles.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from museum_map.common import INTERIM, N_SAMPLE, RAW, SEED, write_parquet  # noqa: E402

OVERSAMPLE = 3
FLOOR = 10


def sqrt_allocate(counts: dict[str, int], total: int) -> dict[str, int]:
    """Largest-remainder allocation on sqrt weights, capped by what each stratum has.

    Iterates because capping a small stratum frees quota that must be redistributed.
    """
    keys = sorted(counts)
    alloc = {k: 0 for k in keys}
    for _ in range(1000):
        need = total - sum(alloc.values())
        if need <= 0:
            break
        room = [k for k in keys if alloc[k] < counts[k]]
        if not room:
            break
        w = {k: math.sqrt(counts[k]) for k in room}
        wsum = sum(w.values())
        target = {k: need * w[k] / wsum for k in room}
        placed = 0
        for k in room:
            take = min(int(target[k]), counts[k] - alloc[k])
            alloc[k] += take
            placed += take
        if placed == 0:
            # Remainders are all < 1; hand out the last few units one at a time.
            for k in sorted(room, key=lambda k: (-target[k], k)):
                if sum(alloc.values()) >= total:
                    break
                if alloc[k] < counts[k]:
                    alloc[k] += 1
    return alloc


def main() -> None:
    df = pd.read_parquet(RAW / "museums.parquet")
    print(f"loaded {len(df):,} museums across {df.country_qid.nunique()} countries")

    counts = df.country_qid.value_counts().to_dict()
    alloc = sqrt_allocate(counts, N_SAMPLE)
    assert sum(alloc.values()) == N_SAMPLE, sum(alloc.values())

    rng = np.random.default_rng(SEED)
    picks = []
    for cq in sorted(counts):
        want = alloc[cq]
        if want == 0:
            continue
        pool = df[df.country_qid == cq].sort_values("qid")
        n_cand = min(len(pool), want * OVERSAMPLE + FLOOR)
        idx = rng.permutation(len(pool))[:n_cand]
        sub = pool.iloc[np.sort(idx)].copy()
        sub["alloc"] = want
        # Deterministic priority order within the country; s04 takes a prefix of this.
        sub["priority"] = rng.permutation(len(sub))
        picks.append(sub)

    cand = pd.concat(picks, ignore_index=True).sort_values(["country_qid", "priority"])
    write_parquet(cand, INTERIM / "candidates.parquet", expect_cols=["qid", "alloc", "priority"])

    a = pd.Series(alloc)
    a = a[a > 0].sort_values(ascending=False)
    print(f"\nallocation: {len(a)} countries receive >=1 slot; {N_SAMPLE} total")
    print(f"candidates fetched for sitelink resolution: {len(cand):,}")
    qid2label = dict(zip(df.country_qid, df.country_label))
    show = (
        pd.DataFrame({
            "population": df.country_label.value_counts(),
            "allocated": a.rename(index=qid2label),
        })
        .dropna()
        .sort_values("population", ascending=False)
        .head(12)
    )
    show["pop_%"] = (show.population / len(df) * 100).round(1)
    show["alloc_%"] = (show.allocated / N_SAMPLE * 100).round(1)
    print("\nstratification effect (top 12 by population):")
    print(show.astype({"population": int, "allocated": int}).to_string())


if __name__ == "__main__":
    main()
