"""Pipeline 09 — the Wikidata facts the tooltip can actually rely on.

A census of every `wdt:` property across the 54,778-museum corpus found only
seven carried by more than half of it, and four of those (P31, P17, P625, P131)
the harvest already stores. This stage fetches the rest, plus a few sparser
fields that are worth a tooltip line where they exist:

    P856   official website        57.8%
    P571   inception               49.5%   -> 56.7% unioned with P1619 and P580
    P373   Commons category        62.0%
    P6375  street address          37.8%
    P1435  heritage designation    23.0%

`P18` (image, 72.5%) is deliberately **not** fetched. Museum lead images are
overwhelmingly building exteriors and logos; a museum is a collection, not a
facade, so a wall of buildings on hover would argue against the thing the map is
for. It is also the only field here that would make the report depend on the
network at view time. Revisit if the thin-lead museums (37.5% of leads are under
300 characters) ever need something to show.

Nothing here is used to *place* a museum — the map is built from lead text and
this stage runs after the layout. It feeds the hover card, the search field and
the colormap selector, so re-running it costs p13 and nothing below it.

Two things not to read too much into:

  * **Coverage is not evenly distributed.** Against the 5,560 museums recovered
    from category trees rather than typed by Wikidata, official website runs
    28.1% against 61.2%, and inception 30.9% against 51.6% — while heritage
    designation *inverts*, 42.7% against 20.7%, because that corpus is largely
    NRHP listings. Anything mapped to colour from these fields is partly a map of
    which country's editors have been thorough. That is why the size channel uses
    `sitelink_count`, which is the one field with no such skew.
  * **`founded_year` is a year, not a founding.** Wikidata truncates date
    precision into the same ISO string, so a value recorded to the century
    arrives looking like an exact year. And for a historic house that later
    became a museum, P571 often dates the *structure*, not the institution.

Multi-valued properties are resolved to their minimum — earliest date,
lexicographically first URL — so a re-run is byte-identical, the same rule the
harvest uses to pick a country.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from museum_map.common import qid, sparql, write_parquet  # noqa: E402
from pipeline.common import corpus_paths  # noqa: E402
from museum_map.wiki import fetch_en_labels  # noqa: E402

# 2,000 QIDs per query keeps every partition inside WDQS's 60s budget with room
# to spare; the census that sized this ran 28 of them without a timeout.
CHUNK = 2000

# Sanity bounds on a parsed year. A museum under construction does carry a future
# inception, but it announces an opening date within a decade or so — nothing
# announces one for the next century. Past that the value is a typo: the Steilneset
# Memorial opened in 2011 and Wikidata records its inception as 2100. The lower
# bound is loose on purpose, because the archaeological sites in the corpus date
# honestly to the fourth millennium BCE (see the docstring's second caveat).
YEAR_MIN, YEAR_MAX = -4000, 2040

# Seven OPTIONALs cross-produce inside the group, but every one of these
# properties is low-cardinality on a museum, so the group collapses immediately.
# GROUP_CONCAT rather than MIN() because Blazegraph's MIN over IRIs is not
# something to depend on; the pick happens in Python where it is explicit.
FACTS = """
SELECT ?m
  (GROUP_CONCAT(DISTINCT STR(?site);    separator="|") AS ?sites)
  (GROUP_CONCAT(DISTINCT STR(?inc);     separator="|") AS ?incs)
  (GROUP_CONCAT(DISTINCT STR(?open);    separator="|") AS ?opens)
  (GROUP_CONCAT(DISTINCT STR(?start);   separator="|") AS ?starts)
  (GROUP_CONCAT(DISTINCT STR(?commons); separator="|") AS ?commonses)
  (GROUP_CONCAT(DISTINCT STR(?addr);    separator="|") AS ?addrs)
  (GROUP_CONCAT(DISTINCT STRAFTER(STR(?herit), "entity/"); separator="|") AS ?herits)
WHERE {
  VALUES ?m { %s }
  OPTIONAL { ?m wdt:P856  ?site }
  OPTIONAL { ?m wdt:P571  ?inc }
  OPTIONAL { ?m wdt:P1619 ?open }
  OPTIONAL { ?m wdt:P580  ?start }
  OPTIONAL { ?m wdt:P373  ?commons }
  OPTIONAL { ?m wdt:P6375 ?addr }
  OPTIONAL { ?m wdt:P1435 ?herit }
}
GROUP BY ?m
"""


def first(packed: str) -> str:
    """Lowest of a `|`-joined value list, or "" — deterministic across re-runs."""
    vals = [v for v in (packed or "").split("|") if v]
    return min(vals) if vals else ""


def year_of(iso: str) -> int | None:
    """Year from a Wikidata time literal, including BCE (`-0500-01-01T...`)."""
    if not iso:
        return None
    neg = iso.startswith("-")
    head = (iso[1:] if neg else iso).split("-", 1)[0]
    if not head.isdigit():
        return None
    y = -int(head) if neg else int(head)
    return y if YEAR_MIN <= y <= YEAR_MAX else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="fixture")
    args = ap.parse_args()

    leads_path, out_dir = corpus_paths(args.corpus)
    leads = pd.read_parquet(leads_path).sort_values("qid").reset_index(drop=True)
    qids = leads.qid.tolist()
    n = len(qids)
    print(f"corpus={args.corpus}  {n:,} museums, {(n + CHUNK - 1) // CHUNK} chunks")

    rows: dict[str, dict] = {}
    for i in range(0, n, CHUNK):
        chunk = qids[i : i + CHUNK]
        got = sparql(
            FACTS % " ".join("wd:" + q for q in chunk),
            namespace="wdqs_facts",
            timeout=300,
        )
        for r in got:
            rows[qid(r["m"])] = r
        print(f"  [{i // CHUNK + 1}] {len(rows):,} museums with at least one fact",
              flush=True)

    def field(q: str, key: str) -> str:
        return first(rows.get(q, {}).get(key, ""))

    out = pd.DataFrame({"qid": qids})
    out["website"] = [field(q, "sites") for q in qids]
    out["commons_category"] = [field(q, "commonses") for q in qids]
    out["address"] = [field(q, "addrs") for q in qids]

    # P571 is the museum's own inception where it exists; the other two are the
    # fallbacks that carry the union past half the corpus. Preferring in that
    # order rather than taking the overall earliest keeps "founded" meaning the
    # institution wherever Wikidata bothered to say so.
    years = []
    for q in qids:
        for key in ("incs", "opens", "starts"):
            y = year_of(field(q, key))
            if y is not None:
                years.append(y)
                break
        else:
            years.append(None)
    out["founded_year"] = pd.array(years, dtype="Int64")

    # ---- QID-valued fields resolved to English labels ----
    herit_qids = {
        h for q in qids for h in (rows.get(q, {}).get("herits", "") or "").split("|") if h
    }
    # P131 is already in the corpus from the harvest and has never been used; it
    # only ever needed labels. 5.0% of museums carry more than one value (up to
    # 35), and nothing distinguishes them without walking the containment
    # hierarchy, so the pick is arbitrary-but-stable rather than most-specific.
    admin_qids = {
        a for s in leads.admins.fillna("") for a in s.split("|") if a
    }
    print(f"\nresolving labels: {len(herit_qids):,} heritage designations, "
          f"{len(admin_qids):,} administrative areas")
    labels = fetch_en_labels(sorted(herit_qids | admin_qids))

    def named(packed: str, limit: int) -> str:
        vals = sorted({v for v in (packed or "").split("|") if v})[:limit]
        return "; ".join(labels.get(v, v) for v in vals)

    out["heritage"] = [named(rows.get(q, {}).get("herits", ""), 2) for q in qids]
    out["admin_label"] = [
        labels.get(first(s), "") for s in leads.admins.fillna("")
    ]

    assert (out.qid.to_numpy() == leads.qid.to_numpy()).all(), "facts/leads order drift"
    write_parquet(out, out_dir / "facts.parquet",
                  expect_cols=["qid", "website", "founded_year", "admin_label"])

    print(f"\ncoverage over {n:,} museums:")
    for col in ("website", "commons_category", "address", "heritage", "admin_label"):
        have = (out[col] != "").sum()
        print(f"  {col:<18} {have:>7,}  {have / n * 100:5.1f}%")
    fy = out.founded_year.notna()
    print(f"  {'founded_year':<18} {fy.sum():>7,}  {fy.mean() * 100:5.1f}%")
    if fy.any():
        print(f"    years {int(out.founded_year.min())} to {int(out.founded_year.max())}, "
              f"median {int(out.founded_year.median())}")


if __name__ == "__main__":
    main()
