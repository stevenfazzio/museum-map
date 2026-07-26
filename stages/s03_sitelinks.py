"""Stage 03 — resolve real Wikipedia sitelinks for every candidate.

s01 only knows `wikibase:sitelinks > 0`, which counts Commons/Wikiquote/Wikisource
too. This resolves the actual per-language Wikipedia articles.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from probe.common import INTERIM, write_parquet  # noqa: E402
from probe.wiki import ENTITY_BATCH, fetch_sitelinks, wikipedia_sites  # noqa: E402


def main() -> None:
    cand = pd.read_parquet(INTERIM / "candidates.parquet")
    qids = sorted(cand.qid.unique())
    sites = wikipedia_sites()
    print(f"{len(qids):,} candidates; {len(sites)} open Wikipedias in the sitematrix")

    rows = []
    for i in range(0, len(qids), ENTITY_BATCH):
        chunk = qids[i : i + ENTITY_BATCH]
        got = fetch_sitelinks(chunk)
        for q, links in got.items():
            for db, title in links.items():
                rows.append(
                    {"qid": q, "dbname": db, "lang": sites[db]["lang"],
                     "api": sites[db]["url"] + "/w/api.php", "title": title}
                )
        done = i + len(chunk)
        if done % 1000 < ENTITY_BATCH or done == len(qids):
            print(f"  {done:,}/{len(qids):,} candidates resolved -> {len(rows):,} articles")

    sl = pd.DataFrame(rows)
    write_parquet(sl, INTERIM / "sitelinks.parquet", expect_cols=["qid", "lang", "title", "api"])

    per = sl.groupby("qid").size()
    missing = len(qids) - per.shape[0]
    print(f"\ncandidates with >=1 Wikipedia article: {per.shape[0]:,} ({missing:,} have none)")
    print(f"articles per museum: median {per.median():.0f}, mean {per.mean():.1f}, max {per.max()}")
    print("\nmost common article languages:")
    print(sl.lang.value_counts().head(12).to_string())


if __name__ == "__main__":
    main()
