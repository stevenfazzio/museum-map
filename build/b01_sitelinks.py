"""Build 01 — resolve real Wikipedia sitelinks for every museum in the corpus.

The probe resolved sitelinks for 7,233 sampled candidates; this does the same for
all 55,280. `sitelink_count` from the harvest counts Commons/Wikiquote/Wikisource
too, so it cannot be used to plan the fetch — only this stage knows how many real
Wikipedia articles exist.

Resumption is free rather than incremental: all ~1,100 responses are cached by
request hash, so a re-run replays from disk in about a minute and continues.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build.common import FULL_INTERIM, fmt_eta  # noqa: E402
from probe.common import RAW, write_parquet  # noqa: E402
from probe.wiki import fetch_sitelinks, wikipedia_sites  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="first N museums only (smoke test)")
    args = ap.parse_args()

    df = pd.read_parquet(RAW / "museums.parquet")
    qids = sorted(df.qid.unique())
    if args.limit:
        qids = qids[: args.limit]
    sites = wikipedia_sites()
    print(f"{len(qids):,} museums; {len(sites)} open Wikipedias in the sitematrix")
    print(f"workers={args.workers}")

    t0 = time.monotonic()

    def progress(n: int, total: int) -> None:
        if n % 50 and n != total:
            return
        rate = n / max(time.monotonic() - t0, 1e-9)
        eta = (total - n) / rate if rate else float("inf")
        print(f"  {n:,}/{total:,} batches  {rate:.1f} req/s  eta {fmt_eta(eta)}", flush=True)

    got = fetch_sitelinks(qids, workers=args.workers, on_progress=progress)

    rows = [
        {"qid": q, "dbname": db, "lang": sites[db]["lang"],
         "api": sites[db]["url"] + "/w/api.php", "title": title}
        for q, links in got.items()
        for db, title in links.items()
    ]
    sl = pd.DataFrame(rows).sort_values(["qid", "dbname"]).reset_index(drop=True)
    if args.limit:
        # A truncated sitelinks.parquet looks exactly like a complete one to b02,
        # which would then silently fetch a fraction of the corpus. Never write it.
        print(f"\n--limit set: {len(sl):,} rows resolved, NOT written")
    else:
        write_parquet(sl, FULL_INTERIM / "sitelinks.parquet",
                      expect_cols=["qid", "lang", "title", "api"])

    per = sl.groupby("qid").size()
    print(f"\nelapsed: {fmt_eta(time.monotonic() - t0)}")
    print(f"museums with >=1 Wikipedia article: {per.shape[0]:,} "
          f"({len(qids) - per.shape[0]:,} have none)")
    print(f"articles: {len(sl):,} total, median {per.median():.0f} / mean {per.mean():.2f} "
          f"per museum, max {per.max()}")
    print(f"distinct wikis to fetch from: {sl.api.nunique()}")
    print("\nprojected extract requests (20 titles per request, per wiki):")
    est = int(sl.groupby("api").title.nunique().apply(lambda n: -(-n // 20)).sum())
    print(f"  {est:,} requests")
    print("\nmost common article languages:")
    print(sl.lang.value_counts().head(12).to_string())


if __name__ == "__main__":
    main()
