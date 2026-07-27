"""Stage 04 — settle the final 2,000 and assign one type label per museum.

Candidates that turned out to have no Wikipedia article are dropped, then the
sqrt allocation is re-run over what survived so the total lands exactly on 2,000.

Type labels are derived from the data rather than a hand-curated taxonomy: a
museum's label is the *least common* of its P31 values among the K most common
museum types globally. Least-common = most specific, so a museum tagged both
{museum, art museum} is labelled "art museum"; one tagged only {museum} stays
generic. Anything with no top-K type falls to "other".
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from museum_map.common import INTERIM, N_SAMPLE, SUBCLASSES, qid, sparql, write_parquet  # noqa: E402
from museum_map.wiki import fetch_en_labels  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s02_sample import sqrt_allocate  # noqa: E402

TOP_K_TYPES = 15


def main() -> None:
    cand = pd.read_parquet(INTERIM / "candidates.parquet")
    sl = pd.read_parquet(INTERIM / "sitelinks.parquet")

    have = set(sl.qid.unique())
    ok = cand[cand.qid.isin(have)].copy()
    print(f"candidates {len(cand):,} -> {len(ok):,} with >=1 Wikipedia article "
          f"({len(cand) - len(ok):,} dropped)")

    counts = ok.country_qid.value_counts().to_dict()
    alloc = sqrt_allocate(counts, N_SAMPLE)
    assert sum(alloc.values()) == N_SAMPLE, sum(alloc.values())

    picks = []
    for cq, want in sorted(alloc.items()):
        if want:
            picks.append(ok[ok.country_qid == cq].nsmallest(want, "priority"))
    sample = pd.concat(picks, ignore_index=True)
    assert len(sample) == N_SAMPLE and sample.qid.is_unique

    # ---- type labels -------------------------------------------------------
    # P31 returns every type a museum has, including structural ones ("building")
    # and superclasses ("memory institution"). Only the Q33506 subclass closure
    # counts as a *museum type*.
    museum_types = {qid(r["t"]) for r in sparql(SUBCLASSES, namespace="wdqs_subclasses")}
    print(f"museum-type closure: {len(museum_types)} QIDs")

    exploded = (
        sample.assign(t=sample.types.str.split("|"))
        .explode("t")
        .dropna(subset=["t"])
        .query("t != ''")
    )
    exploded = exploded[exploded.t.isin(museum_types)]
    freq = exploded.t.value_counts()
    top = list(freq.head(TOP_K_TYPES).index)
    rank = {t: i for i, t in enumerate(top)}  # index 0 = most common = least specific

    def pick_type(types_str: str) -> str:
        ts = [t for t in types_str.split("|") if t in rank]
        if not ts:
            return "OTHER"
        return max(ts, key=lambda t: rank[t])  # highest rank = rarest = most specific

    n_museum_typed = sample.types.map(
        lambda s: any(t in museum_types for t in s.split("|"))
    ).mean()

    sample["type_qid"] = sample.types.map(pick_type)
    labels = fetch_en_labels(top)
    labels["OTHER"] = "other"
    sample["type_label"] = sample.type_qid.map(labels)

    sample = sample.drop(columns=["alloc", "priority"]).sort_values("qid").reset_index(drop=True)
    write_parquet(
        sample,
        INTERIM / "sample.parquet",
        expect_cols=["qid", "country_qid", "country_label", "type_qid", "type_label"],
    )

    print(f"\nfinal sample: {len(sample):,} museums, "
          f"{sample.country_qid.nunique()} countries, {sample.type_label.nunique()} types")
    print(f"museums carrying any museum-specific P31: {n_museum_typed:.1%}")
    generic = (sample.type_qid == freq.index[0]).mean()
    print(f"museums whose most specific type is still the generic top type: {generic:.1%}"
          "  <- type is a weak label")
    print(f"largest country share: {sample.country_label.value_counts(normalize=True).iloc[0]:.1%}")
    print("\ncountry distribution (top 15):")
    for k, v in sample.country_label.value_counts().head(15).items():
        print(f"  {k:<24} {v:>4}  {v / len(sample) * 100:4.1f}%")
    print("\ntype distribution:")
    for k, v in sample.type_label.value_counts().items():
        print(f"  {k:<32} {v:>4}  {v / len(sample) * 100:4.1f}%")


if __name__ == "__main__":
    main()
