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

It also writes `places.parquet`, the gazetteer behind the map's nearby control:
the settlements a visitor can name, each with a coordinate to measure a radius
from. It is built here rather than in its own stage because the places are the
P131 values already sitting in `leads.admins`, whose English labels this stage
already fetches — splitting it would mean two stages resolving the same QIDs.
Three things about it:

  * **Settlements only.** `admin_label` is a mix of scales — the commonest
    values are `New York`, `Rome`, `Florida`, `California`, `Manhattan` — because
    the pick among a museum's several P131 values is arbitrary (see below). A
    radius around a state is a disc dropped on its centroid: 100 km around
    Florida's misses Jacksonville and Miami and says nothing about it. So the
    gazetteer keeps only the Q486972 subclass closure. The P31 values stay in the
    cache, so admitting coarser places later costs no network.
  * **A place with no P625 is dropped**, because there is nothing to measure from.
  * **`country` is derived, not fetched.** It exists to tell the two Cambridges
    apart in the typeahead, and the museums referencing a place already carry a
    country, so it is their plurality rather than another round of requests.

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

from museum_map.common import (  # noqa: E402
    SETTLEMENT_SUBCLASSES,
    SUBDIVISION_SUBCLASSES,
    qid,
    sparql,
    write_parquet,
)
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


# What the gazetteer needs about an administrative entity. Same
# GROUP_CONCAT-then-pick-in-Python shape as FACTS, and for the same reason: the
# pick is explicit and stable across re-runs.
#
# `parents` is one level of P131, deliberately not the transitive `P131*`. The
# transitive form with the subdivision type test inlined
# (`?p wdt:P131* ?r . ?r wdt:P31/wdt:P279* wd:Q10864048`) does not return inside
# WDQS's budget at this stage's chunk size — measured past five minutes on a
# single 2,000-QID partition, against about twenty seconds for the shape below.
# Walking one level at a time in Python costs a handful of extra round trips, all
# cached, and each one is a query shape this stage already knows finishes.
ADMIN = """
SELECT ?p
  (GROUP_CONCAT(DISTINCT STR(?coord); separator="|") AS ?coords)
  (GROUP_CONCAT(DISTINCT STRAFTER(STR(?type),   "entity/"); separator="|") AS ?types)
  (GROUP_CONCAT(DISTINCT STRAFTER(STR(?parent), "entity/"); separator="|") AS ?parents)
WHERE {
  VALUES ?p { %s }
  OPTIONAL { ?p wdt:P625 ?coord }
  OPTIONAL { ?p wdt:P31  ?type }
  OPTIONAL { ?p wdt:P131 ?parent }
}
GROUP BY ?p
"""

# How far up the containment chain to look for a first-level subdivision. A
# settlement reaches its state in two or three steps (Portland -> Multnomah
# County -> Oregon); the cap is what stops a P131 cycle, which Wikidata does
# contain, from walking forever.
REGION_DEPTH = 6


def point_latlon(point: str) -> tuple[float, float] | None:
    """(lat, lon) from a WKT `Point(lon lat)` literal — note the order swap."""
    if not point.startswith("Point("):
        return None
    try:
        lon, lat = point[6:-1].split()
        return float(lat), float(lon)
    except ValueError:
        return None


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

    write_places(leads, sorted(admin_qids), labels, out_dir)


def write_places(leads: pd.DataFrame, admin_qids: list[str],
                 labels: dict[str, str], out_dir: Path) -> None:
    """The settlements a visitor can name, with somewhere to measure a radius from."""
    settlements = {qid(r["t"]) for r in sparql(SETTLEMENT_SUBCLASSES,
                                               namespace="wdqs_settlement_subclasses")}
    print(f"\nplaces: {len(admin_qids):,} administrative areas in the corpus, "
          f"{len(settlements):,} types in the settlement closure")

    got: dict[str, dict] = {}

    def resolve(qids: list[str]) -> None:
        """Fill `got` for any of `qids` not already in it."""
        todo = sorted({q for q in qids if q not in got})
        for i in range(0, len(todo), CHUNK):
            chunk = todo[i : i + CHUNK]
            for r in sparql(ADMIN % " ".join("wd:" + q for q in chunk),
                            namespace="wdqs_admin", timeout=300):
                got[qid(r["p"])] = r
            print(f"  [{i // CHUNK + 1}/{(len(todo) + CHUNK - 1) // CHUNK}] "
                  f"{len(got):,} areas resolved", flush=True)
        for q in todo:  # an entity WDQS returned nothing for still counts as tried
            got.setdefault(q, {})

    resolve(admin_qids)

    # A museum counts towards every area that contains it, not just the one
    # `admin_label` happens to name — the count orders the typeahead, and a
    # visitor typing "Paris" means the city whether or not p09 picked it.
    n_museums: dict[str, int] = {}
    countries: dict[str, list[str]] = {}
    for admins, country in zip(leads.admins.fillna(""), leads.country_label.fillna("")):
        for a in admins.split("|"):
            if a:
                n_museums[a] = n_museums.get(a, 0) + 1
                if country:
                    countries.setdefault(a, []).append(country)

    def packed(q: str, key: str) -> list[str]:
        return sorted({v for v in (got.get(q, {}).get(key, "") or "").split("|") if v})

    keep = []
    no_coord = no_type = 0
    for q in admin_qids:
        if not set(packed(q, "types")) & settlements:
            no_type += 1
            continue
        if point_latlon(first(got.get(q, {}).get("coords", ""))) is None:
            no_coord += 1
            continue
        keep.append(q)
    print(f"  {no_type:,} not settlements, {no_coord:,} settlements without a coordinate")

    region = regions_of(keep, got, resolve)
    region_labels = fetch_en_labels(sorted(set(region.values())))
    print(f"  first-level region found for {len(region):,} of {len(keep):,} settlements")

    rows = []
    for q in keep:
        latlon = point_latlon(first(got[q]["coords"]))
        here = countries.get(q, [])
        name = labels.get(q, q)
        region_name = region_labels.get(region.get(q, ""), "")
        rows.append({
            "qid": q,
            "name": name,
            # A place that *is* its own region reads as an error in the list
            # ("Berlin — Berlin"), so it carries none rather than repeating.
            "region": "" if region_name == name else region_name,
            "lat": latlon[0],
            "lon": latlon[1],
            # Plurality, ties broken by name so a re-run is byte-identical.
            "country": max(sorted(set(here)), key=here.count) if here else "",
            "n_museums": n_museums.get(q, 0),
        })

    places = pd.DataFrame(rows).sort_values(
        ["n_museums", "qid"], ascending=[False, True]).reset_index(drop=True)
    write_parquet(places, out_dir / "places.parquet",
                  expect_cols=["qid", "name", "region", "lat", "lon", "country", "n_museums"])
    if len(places):
        print(f"  most museums: {', '.join(places.name.head(5))}")
        named = places[places.region != ""]
        if len(named):
            print("  e.g. " + "; ".join(f"{r.name} — {r.region}, {r.country}"
                                        for r in named.head(3).itertuples(index=False)))


def regions_of(places: list[str], got: dict[str, dict], resolve) -> dict[str, str]:
    """place qid -> the first-level subdivision containing it, where there is one.

    Walks P131 upwards a level at a time, resolving each level in bulk, and stops
    at the first ancestor typed inside the Q10864048 closure. The place's own
    types are not tested: a city-state is its own subdivision, and answering
    "Singapore" with "Singapore" tells a visitor nothing.

    A place on a boundary can sit under two subdivisions. The pick is the lowest
    QID, which is arbitrary but stable — the same rule this stage uses everywhere
    else it has to choose between equally good values.
    """
    first_level = {qid(r["t"]) for r in sparql(SUBDIVISION_SUBCLASSES,
                                               namespace="wdqs_subdivision_subclasses")}
    found: dict[str, str] = {}
    frontier = {p: [p] for p in places}

    for _ in range(REGION_DEPTH):
        ahead = {}
        for p, nodes in frontier.items():
            up = sorted({a for n in nodes
                         for a in (got.get(n, {}).get("parents", "") or "").split("|") if a})
            if up:
                ahead[p] = up
        if not ahead:
            break
        resolve(sorted({n for nodes in ahead.values() for n in nodes}))
        for p, nodes in ahead.items():
            for n in nodes:
                types = {t for t in (got.get(n, {}).get("types", "") or "").split("|") if t}
                if types & first_level:
                    found[p] = n
                    break
        frontier = {p: nodes for p, nodes in ahead.items() if p not in found}
        if not frontier:
            break
    return found


if __name__ == "__main__":
    main()
