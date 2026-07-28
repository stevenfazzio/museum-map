"""Build 07 — find the museums p01's Wikidata query does not return.

EXPENSIVE. A full run crawls the museum category tree of the top 30 wikis
(~185,000 articles, several hours of network) and classifies ~48,000 candidates
with Haiku (~$27). It is not part of `run.sh` and does not need re-running to
build the map: its output, `data/interim/gap/in_scope_qids.json`, is consumed by
p08 and changes only as Wikidata's typing changes.

Why it exists: the corpus is defined by `wdt:P31/wdt:P279* wd:Q33506`, which is
a claim about Wikidata's typing rather than about the world. It misses 5,560
museums that have a Wikipedia article — 24% of US museums, against 2% for Italy
and Japan, because a US historic house museum gets an NRHP listing and
`instance of: house` and nobody adds the museum claim. See `COVERAGE.md`.

Scope is the top 30 wikis by corpus coverage, which reach 96.2% of the corpus.
The remaining 263 contribute under 4% combined — below this measurement's own
error bar.

Everything is cached by request hash, so a re-run after a crash is nearly free.
Stages checkpoint to data/interim/gap/ and are skipped when already present.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from museum_map.common import INTERIM, RAW  # noqa: E402
from museum_map.gap import (  # noqa: E402
    NOT_AN_INSTITUTION,
    OUT_OF_SCOPE,
    classify,
    crawl_all,
    derive_config,
    p31_of,
    pageprops,
)
from museum_map.wiki import fetch_leads  # noqa: E402

GAP = INTERIM / "gap"


def top_wikis(n: int) -> dict[str, int]:
    """dbname -> museums in the corpus reachable through it, largest first."""
    lead = pd.read_parquet(INTERIM / "full" / "leads.parquet")
    sl = pd.read_parquet(INTERIM / "full" / "sitelinks.parquet")
    sl = sl[sl.qid.isin(set(lead.qid))]
    return sl.groupby("dbname").qid.nunique().sort_values(ascending=False).head(n).to_dict()


def measure_wiki(dbname, cfg, articles, inraw):
    out_path = GAP / f"measured_{dbname}.json"
    if out_path.exists():
        return json.load(open(out_path))

    api = f"https://{cfg['lang']}.wikipedia.org/w/api.php"
    titles = sorted(articles)
    props = pageprops(api, titles)
    miss = {t: v for t, v in props.items() if v[0] not in inraw}
    p31 = p31_of(sorted({v[0] for v in miss.values()}))
    cand = {t: v for t, v in miss.items()
            if not set(p31.get(v[0], [])) & NOT_AN_INSTITUTION}
    leads = fetch_leads(api, sorted(cand))

    items = [(t, v[2], v[1], leads.get(t, "")) for t, v in sorted(cand.items())]
    labels, usage = asyncio.run(classify(items))
    res = {"dbname": dbname, "n_articles": len(titles), "n_have": len(props) - len(miss),
           "n_miss": len(miss), "labels": labels,
           "qid": {t: cand[t][0] for t in labels}, "usage": list(usage)}
    json.dump(res, open(out_path, "w"), ensure_ascii=False)
    c = Counter(labels.values())
    print(f"  {dbname}: have {res['n_have']:,} | miss {len(miss):,} -> "
          f"museum {c['museum']:,} partly {c['partly']:,} "
          f"adjacent {c['adjacent']:,} not {c['not']:,}", flush=True)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wikis", type=int, default=30, help="top N wikis by corpus coverage")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    GAP.mkdir(parents=True, exist_ok=True)

    sizes = top_wikis(args.wikis)
    cfg_path = GAP / "wiki_config.json"
    if cfg_path.exists():
        cfg = json.load(open(cfg_path))
    else:
        cfg = derive_config(list(sizes))
        json.dump(cfg, open(cfg_path, "w"), ensure_ascii=False, indent=1)
    print(f"{len(cfg)} wikis configured from Wikidata")
    for db, c in cfg.items():
        print(f"  {db:<10}{sizes.get(db, 0):>7,}  {c['root']:<28} {' '.join(c['stems'][:6])}")

    art_path = GAP / "articles.json"
    if art_path.exists():
        arts = json.load(open(art_path))
    else:
        arts = crawl_all(cfg, sizes, workers=args.workers)
        json.dump(arts, open(art_path, "w"), ensure_ascii=False)
    print(f"\ncrawled {sum(len(a) for a in arts.values()):,} articles across {len(arts)} wikis")

    inraw = set(pd.read_parquet(RAW / "museums.parquet").qid)
    results = [measure_wiki(db, cfg[db], arts[db], inraw) for db in arts]

    # Aggregate by QID, not by article: a missing museum usually has articles in
    # several trees, and counting rows would multiply it. The duplication gives
    # cross-wiki agreement for free.
    by_qid: dict[str, dict[str, str]] = {}
    for r in results:
        for t, lab in r["labels"].items():
            by_qid.setdefault(r["qid"][t], {})[r["dbname"]] = lab

    RANK = ["museum", "partly", "adjacent", "not"]

    def consensus(labels):
        c = Counter(labels.values())
        top = max(c.values())
        for r in RANK:  # ties break toward the stricter label
            if c[r] == top:
                return r

    cons = {q: consensus(v) for q, v in by_qid.items()}
    json.dump(cons, open(GAP / "consensus.json", "w"))

    strict = [q for q, v in cons.items() if v == "museum"]
    p31 = p31_of(sorted(strict))
    keep = [q for q in strict if not set(p31.get(q, [])) & OUT_OF_SCOPE]
    json.dump(sorted(keep), open(GAP / "in_scope_qids.json", "w"))

    n = Counter(cons.values())
    tin = sum(r["usage"][0] for r in results)
    tout = sum(r["usage"][1] for r in results)
    print(f"\n{len(by_qid):,} candidate QIDs not in the corpus")
    for k in RANK:
        print(f"  {k:<9} {n[k]:>7,}")
    print(f"\nin scope (strict museum, minus vessels and dealer galleries): {len(keep):,}")
    print(f"wrote {GAP / 'in_scope_qids.json'}")
    print(f"classifier cost ~${tin / 1e6 * 1.0 + tout / 1e6 * 5.0:.2f}")


if __name__ == "__main__":
    main()
