"""Build 04 — re-select the fixture's leads under the map's rule.

The probe's `data/interim/leads.parquet` picks the longest article in any
language. The map prefers the local-language article when it is at least half as
long (see `build/common.py:select_leads`). If the fixture kept the old rule it
would stop predicting the full pipeline, which is the only reason it exists.

The probe's own artefacts are left untouched — `run_all.sh` has to keep
reproducing `reports/report.md` exactly — so this writes a separate file that
only the map stages read.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build.common import select_leads  # noqa: E402
from probe.common import INTERIM, write_parquet  # noqa: E402


def main() -> None:
    sample = pd.read_parquet(INTERIM / "sample.parquet")
    allleads = pd.read_parquet(INTERIM / "leads_all.parquet")
    allleads = allleads[allleads.qid.isin(set(sample.qid))]
    print(f"{len(sample):,} museums, {len(allleads):,} articles")

    best = select_leads(allleads, dict(zip(sample.qid, sample.country_qid)))
    out = sample.merge(best, on="qid", how="inner")
    write_parquet(out, INTERIM / "fixture_map_leads.parquet",
                  expect_cols=["qid", "lang", "text", "chars", "type_label"])

    old = pd.read_parquet(INTERIM / "leads.parquet", columns=["qid", "lang", "chars"])
    merged = old.merge(out[["qid", "lang", "chars"]], on="qid", suffixes=("_old", "_new"))
    changed = (merged.lang_old != merged.lang_new).mean()
    print(f"\nlead is in an official language of its country: {out.is_local.mean():.1%}")
    print(f"selection changed for {changed:.1%} of museums")
    print(f"median lead: {old.chars.median():.0f} -> {out.chars.median():.0f} chars")
    print(f"under 200 chars: {(old.chars < 200).mean():.1%} -> {(out.chars < 200).mean():.1%}")


if __name__ == "__main__":
    main()
