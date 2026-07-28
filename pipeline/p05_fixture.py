"""Pipeline 05 — carve a small dev fixture out of the full corpus.

The map stages are slow enough at 49k that iterating on them directly is
painful, so every stage takes `--corpus fixture` and runs against 2,000 museums
instead. This builds that fixture.

It is a plain random sample of the finished corpus, deliberately *not* stratified.
An earlier fixture allocated museums per country in proportion to sqrt(n), which
flattens Italy/Germany/US — and in doing so pushed each museum's neighbours into
other countries by construction, understating the geographic signal by a factor
of 2.7 (0.38x vs 0.14x of the random-pair baseline). A fixture that misrepresents
the corpus that badly is worse than none, because it gets trusted.

**What the fixture can and cannot predict.** Distributional properties transfer
closely — median lead 470 vs 467 chars, 19.2% vs 19.4% under 200 chars, 69.5% vs
69.1% local-language, 87.9% vs 88.1% with coordinates. *Neighbourhood* properties
do not, and cannot: a 4% sample removes 96% of every museum's true nearest
neighbours, so the local<->universal radius reads 0.30x here against 0.14x on the
corpus, and the type probe scores 0.470 against 0.657. Use the fixture to check
that a stage runs and its output looks sane; never quote its neighbourhood or
classifier numbers as if they were the corpus's.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from museum_map.common import INTERIM, SEED, write_parquet  # noqa: E402
from pipeline.common import FULL_INTERIM  # noqa: E402

N_FIXTURE = 2000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_FIXTURE)
    args = ap.parse_args()

    full = pd.read_parquet(FULL_INTERIM / "leads.parquet")
    types_path = FULL_INTERIM / "types.parquet"
    if types_path.exists():
        n_before = len(full)
        full = full.merge(pd.read_parquet(types_path)[["qid", "type_label"]],
                          on="qid", how="left")
        assert len(full) == n_before, "type merge changed row count"

    fixture = (full.sample(n=min(args.n, len(full)), random_state=SEED)
               .sort_values("qid").reset_index(drop=True))
    write_parquet(fixture, INTERIM / "fixture_leads.parquet",
                  expect_cols=["qid", "lang", "text", "chars"])

    print(f"\nsampled {len(fixture):,} of {len(full):,} museums")
    print(f"countries {fixture.country_label.nunique()}, languages {fixture.lang.nunique()}")
    print(f"median lead {fixture.chars.median():.0f} chars (corpus {full.chars.median():.0f})")
    print(f"under 200 chars {(fixture.chars < 200).mean():.1%} "
          f"(corpus {(full.chars < 200).mean():.1%})")
    if "is_local" in fixture.columns:
        print(f"lead in an official language {fixture.is_local.mean():.1%} "
              f"(corpus {full.is_local.mean():.1%})")


if __name__ == "__main__":
    main()
