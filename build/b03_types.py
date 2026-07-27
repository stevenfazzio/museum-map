"""Build 03 — assign one museum type per museum, for the whole corpus.

Same rule as the probe's s04, applied to all 55,280 rather than the sample: a
museum's type is the *least common* of its P31 values among the K most common
museum types globally. Least common = most specific, so {museum, art museum}
labels as "art museum" while a museum tagged only {museum} stays generic.

P31 returns structural types too ("building") and superclasses ("memory
institution"), so only QIDs inside the Q33506 subclass closure count as a museum
type. That closure query is already cached from the harvest.

The map does not colour by this — regions come from Toponymy. It feeds the
tooltip, the search field, and the report's comparison of discovered regions
against declared type.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build.common import FULL_INTERIM  # noqa: E402
from probe.common import INTERIM, RAW, qid, sparql, write_parquet  # noqa: E402
from probe.wiki import fetch_en_labels  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "stages"))
from s01_harvest import SUBCLASSES  # noqa: E402

# The probe used 15 against a 2,000-row sample. The full corpus is 27x larger, so
# a longer tail of types clears a usable count; 25 keeps the rarest bucket in the
# hundreds rather than the single digits.
TOP_K_TYPES = 25


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="full")
    ap.add_argument("--top-k", type=int, default=TOP_K_TYPES)
    args = ap.parse_args()

    if args.corpus == "full":
        df = pd.read_parquet(RAW / "museums.parquet")
        out_path = FULL_INTERIM / "types.parquet"
    else:
        df = pd.read_parquet(INTERIM / "sample.parquet")
        out_path = INTERIM / "types_fixture.parquet"
    print(f"corpus={args.corpus}  {len(df):,} museums")

    museum_types = {qid(r["t"]) for r in sparql(SUBCLASSES, namespace="wdqs_subclasses")}
    print(f"museum-type closure: {len(museum_types)} QIDs")

    exploded = (
        df.assign(t=df.types.str.split("|"))
        .explode("t")
        .dropna(subset=["t"])
        .query("t != ''")
    )
    exploded = exploded[exploded.t.isin(museum_types)]
    freq = exploded.t.value_counts()
    top = list(freq.head(args.top_k).index)
    rank = {t: i for i, t in enumerate(top)}  # 0 = most common = least specific

    def pick_type(types_str: str) -> str:
        ts = [t for t in types_str.split("|") if t in rank]
        return max(ts, key=lambda t: rank[t]) if ts else "OTHER"

    out = df[["qid"]].copy()
    out["type_qid"] = df.types.map(pick_type)
    labels = fetch_en_labels(top)
    labels["OTHER"] = "other"
    out["type_label"] = out.type_qid.map(labels)
    write_parquet(out, out_path, expect_cols=["qid", "type_qid", "type_label"])

    n_typed = df.types.map(lambda s: any(t in museum_types for t in s.split("|"))).mean()
    generic = (out.type_qid == freq.index[0]).mean()
    print(f"\nmuseums carrying any museum-specific P31: {n_typed:.1%}")
    print(f"whose most specific type is still the generic top type: {generic:.1%}"
          "  <- type stays a weak label at full scale")
    print(f"\ntype distribution ({out.type_label.nunique()} labels):")
    for k, v in out.type_label.value_counts().items():
        print(f"  {k:<34} {v:>6}  {v / len(out) * 100:5.1f}%")


if __name__ == "__main__":
    main()
