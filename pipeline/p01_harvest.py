"""Stage 01 — harvest every museum in Wikidata that has at least one sitelink.

Museum = wdt:P31/wdt:P279* wd:Q33506 (the transitive form; the Louvre is an
instance of "art museum", not of "museum" directly, so a plain P31 match misses it).

Partitioning strategy — this took three attempts against WDQS's 60s budget:
  * one unpartitioned paged query        -> times out (GROUP BY + deep OFFSET
                                            forces a full sort of ~81k rows)
  * partition by country, keep the path  -> works but re-walks the P279* closure
                                            once per country, ~20-37s x 200
  * inline the 371 subclasses as VALUES  -> worse; Blazegraph expands it badly
  * partition by type, no ORDER BY/OFFSET-> what we do. The closure is resolved
                                            once, each partition is a plain
                                            wdt:P31 lookup, and the largest
                                            (Q33506, 32.5k rows) returns in 38s.

Any partition that hits the row cap is split recursively over QID number ranges,
so the stage stays correct if a type ever outgrows a single response.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from museum_map.common import RAW, SUBCLASSES, qid, sparql, write_parquet  # noqa: E402

ROW_CAP = 50_000
QID_MAX = 200_000_000
MAX_DEPTH = 10


# "http://www.wikidata.org/entity/Q" is 32 chars, so SUBSTR(...,33) is the number.
TMPL = """
SELECT ?m ?mLabel ?coord ?sl ?c
       (GROUP_CONCAT(DISTINCT STRAFTER(STR(?type),  "entity/"); separator="|") AS ?types)
       (GROUP_CONCAT(DISTINCT STRAFTER(STR(?admin), "entity/"); separator="|") AS ?admins)
WHERE {
  ?m wdt:P31 wd:%(type)s ; wikibase:sitelinks ?sl .
  FILTER(?sl > 0)
  %(range)s
  OPTIONAL { ?m wdt:P17  ?c }
  OPTIONAL { ?m wdt:P625 ?coord }
  OPTIONAL { ?m wdt:P31  ?type }
  OPTIONAL { ?m wdt:P131 ?admin }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
GROUP BY ?m ?mLabel ?coord ?sl ?c
LIMIT %(limit)d
"""

COUNTRY_LABELS = """
SELECT ?c ?cLabel WHERE {
  VALUES ?c { %s }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""


def parse_point(p: str | None) -> tuple[float | None, float | None]:
    if not p or not p.startswith("Point("):
        return None, None
    try:
        lon, lat = p[6:-1].split()
        return float(lat), float(lon)
    except ValueError:
        return None, None


def fetch_type(t: str, lo: int = 0, hi: int = QID_MAX, depth: int = 0) -> list[dict]:
    rng = ""
    if depth:
        rng = (
            "BIND(xsd:integer(SUBSTR(STR(?m), 33)) AS ?num) "
            f"FILTER(?num >= {lo} && ?num < {hi})"
        )
    q = TMPL % {"type": t, "range": rng, "limit": ROW_CAP}
    try:
        rows = sparql(q, namespace="wdqs_bytype", timeout=300)
        capped = len(rows) >= ROW_CAP
    except Exception as exc:
        if depth >= MAX_DEPTH:
            print(f"    ! {t}[{lo},{hi}) giving up: {exc}")
            return []
        print(f"    {t}[{lo},{hi}) failed ({exc}); splitting")
        rows, capped = [], True

    if capped and depth < MAX_DEPTH:
        mid = (lo + hi) // 2
        return fetch_type(t, lo, mid, depth + 1) + fetch_type(t, mid, hi, depth + 1)
    return rows


def main() -> None:
    types = [qid(r["t"]) for r in sparql(SUBCLASSES, namespace="wdqs_subclasses")]
    types = sorted(set(types))
    print(f"{len(types)} types in the Q33506 subclass closure")

    seen: dict[str, dict] = {}
    for i, t in enumerate(types, 1):
        for r in fetch_type(t):
            q = qid(r["m"])
            cq = qid(r["c"]) if r.get("c") else "NONE"
            prev = seen.get(q)
            # A museum with two P17 values yields two rows; keep the
            # lexicographically first country so reruns are stable.
            if prev is not None and prev["country_qid"] <= cq:
                continue
            lat, lon = parse_point(r.get("coord"))
            seen[q] = {
                "qid": q,
                "label": r.get("mLabel", ""),
                "lat": lat,
                "lon": lon,
                "country_qid": cq,
                "types": r.get("types", ""),
                "admins": r.get("admins", ""),
                "sitelink_count": int(r["sl"]),
            }
        if i % 25 == 0 or i == len(types):
            print(f"  [{i}/{len(types)}] {t}: {len(seen):,} unique museums so far")

    df = pd.DataFrame(sorted(seen.values(), key=lambda r: r["qid"]))

    countries = sorted(c for c in df.country_qid.unique() if c != "NONE")
    labs = sparql(
        COUNTRY_LABELS % " ".join(f"wd:{c}" for c in countries),
        namespace="wdqs_countrylabels",
    )
    cmap = {qid(r["c"]): r.get("cLabel", "") for r in labs}
    cmap["NONE"] = "(no country)"
    df["country_label"] = df.country_qid.map(cmap).fillna(df.country_qid)
    df["has_label"] = df.label != df.qid

    write_parquet(df, RAW / "museums.parquet", expect_cols=["qid", "country_qid", "types"])

    print(f"\n{len(df):,} museums, {df.country_qid.nunique()} countries")
    print(f"with coords {df.lat.notna().mean():.1%} | with label {df.has_label.mean():.1%} "
          f"| no country {(df.country_qid == 'NONE').mean():.1%}")
    print("\ntop countries (raw, unstratified):")
    vc = df.country_label.value_counts().head(12)
    for k, v in vc.items():
        print(f"  {k:<22} {v:>6,}  {v / len(df) * 100:4.1f}%")


if __name__ == "__main__":
    main()
