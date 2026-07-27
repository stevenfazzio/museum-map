"""Stage 05 — fetch the lead section of every article, keep the longest per museum.

"Longest" is measured in characters, which is not script-neutral: the same content
in Japanese or Chinese occupies far fewer characters than in German or Russian.
The selected language is stored alongside the text so the report can show how the
bias actually landed.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from museum_map.common import INTERIM, write_parquet  # noqa: E402
from museum_map.textproc import normalize_ws  # noqa: E402
from museum_map.wiki import fetch_leads  # noqa: E402

# XLM-R's 100 pretraining languages — multilingual-e5-large inherits this vocabulary.
XLMR_LANGS = set(
    "af am ar as az be bg bn br bs ca cs cy da de el en eo es et eu fa fi fr fy ga gd gl gu "
    "ha he hi hr hu hy id is it ja jv ka kk km kn ko ku ky la lo lt lv mg mk ml mn mr ms my "
    "ne nl no om or pa pl ps pt ro ru sa sd si sk sl so sq sr su sv sw ta te th tl tr ug uk "
    "ur uz vi xh yi zh".split()
)


def main() -> None:
    sample = pd.read_parquet(INTERIM / "sample.parquet")
    sl = pd.read_parquet(INTERIM / "sitelinks.parquet")
    sl = sl[sl.qid.isin(set(sample.qid))]
    print(f"{len(sample):,} museums -> {len(sl):,} candidate articles "
          f"across {sl.api.nunique()} wikis")

    by_api: dict[str, list[str]] = defaultdict(list)
    for api, title in zip(sl.api, sl.title):
        by_api[api].append(title)

    # Biggest wikis first so failures surface early rather than after an hour.
    order = sorted(by_api, key=lambda a: -len(by_api[a]))
    rows = []
    for n, api in enumerate(order, 1):
        titles = sorted(set(by_api[api]))
        got = fetch_leads(api, titles)
        lang_rows = sl[sl.api == api]
        for q, t, lg in zip(lang_rows.qid, lang_rows.title, lang_rows.lang):
            text = got.get(t)
            if text:
                text = normalize_ws(text)
                if text:
                    rows.append({"qid": q, "lang": lg, "title": t, "text": text,
                                 "chars": len(text)})
        if n % 25 == 0 or n == len(order):
            print(f"  [{n}/{len(order)}] {api.split('//')[1].split('.')[0]}: "
                  f"{len(rows):,} leads fetched")

    allleads = pd.DataFrame(rows)
    write_parquet(allleads, INTERIM / "leads_all.parquet", expect_cols=["qid", "lang", "chars"])

    # Longest wins; ties broken by language code so reruns are identical.
    best = (
        allleads.sort_values(["qid", "chars", "lang"], ascending=[True, False, True])
        .drop_duplicates("qid", keep="first")
        .reset_index(drop=True)
    )
    best = sample.merge(best, on="qid", how="inner")
    write_parquet(best, INTERIM / "leads.parquet", expect_cols=["qid", "lang", "text", "chars"])

    missing = len(sample) - len(best)
    print(f"\nmuseums with a usable lead: {len(best):,} ({missing} lost)")
    print(f"articles per museum: mean {len(allleads) / allleads.qid.nunique():.1f}")
    print("\nselected-lead language (top 15):")
    for k, v in best.lang.value_counts().head(15).items():
        mark = "" if k in XLMR_LANGS else "  <- outside XLM-R's 100 languages"
        print(f"  {k:<8} {v:>5}  {v / len(best) * 100:4.1f}%{mark}")
    off = (~best.lang.isin(XLMR_LANGS)).mean()
    print(f"\nselected leads in languages the encoder was not pretrained on: {off:.1%}")
    print(f"english share: {(best.lang == 'en').mean():.1%}")
    print("\nlead length (characters):")
    print(best.chars.describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]).round(0).to_string())


if __name__ == "__main__":
    main()
