"""Build 08 — fetch the recovered museums and union them into a corpus.

Takes `data/interim/gap/in_scope_qids.json` from p07 and does for those QIDs
what p01-p03 do for the Wikidata-typed ones: metadata, sitelinks, leads, one
lead per museum. Then writes the union as the `full_recovered` corpus.

It does NOT touch `data/raw/museums.parquet`, `interim/full/sitelinks.parquet`
or `interim/full/leads.parquet`. p02 and p03 read and write fixed paths, so
running them here would overwrite the corpus this is meant to extend — and
`full` is deliberately kept buildable on its own, as the baseline the
sensitivity comparison in FINDINGS.md is measured against.

The same library functions p02 and p03 use are reused here, so recovered rows
are built by the same rules as corpus rows and the union is homogeneous.

Network only, ~30 min. Every stage checkpoints and is skipped when present.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from museum_map.common import INTERIM, RAW, WIKIDATA_API, request_json, write_parquet  # noqa: E402
from museum_map.textproc import normalize_ws  # noqa: E402
from museum_map.wiki import fetch_leads_many, fetch_sitelinks, wikipedia_sites  # noqa: E402
from pipeline.common import select_leads  # noqa: E402

REC = INTERIM / "recovered"
OUT = INTERIM / "full_recovered"


def build_museums(qids: list[str]) -> pd.DataFrame:
    """The p01 schema, for QIDs p01's query never returned."""
    path = REC / "museums.parquet"
    if path.exists():
        return pd.read_parquet(path)
    rows = []
    for i in range(0, len(qids), 50):
        r = request_json(WIKIDATA_API, namespace="rec_ent", method="POST", data={
            "action": "wbgetentities", "format": "json",
            "ids": "|".join(qids[i : i + 50]), "props": "claims|labels|sitelinks"})
        for q, e in r.get("entities", {}).items():
            c = e.get("claims", {})

            def ids(p, _c=c):
                return [s["mainsnak"]["datavalue"]["value"]["id"]
                        for s in _c.get(p, []) if s["mainsnak"].get("datavalue")]

            lat = lon = None
            for s in c.get("P625", []):
                dv = s["mainsnak"].get("datavalue")
                if dv:
                    lat, lon = float(dv["value"]["latitude"]), float(dv["value"]["longitude"])
                    break
            label = e.get("labels", {}).get("en", {}).get("value", "")
            rows.append({
                "qid": q, "label": label or q, "lat": lat, "lon": lon,
                "country_qid": (ids("P17") or ["NONE"])[0],
                # P31 verbatim. Every one of these is outside the Q33506 closure
                # -- that is why it was missing -- so p04 assigns it no museum
                # type, which is itself the finding.
                "types": "|".join(ids("P31")),
                "admins": "|".join(ids("P131")),
                "sitelink_count": len(e.get("sitelinks", {})),
                "has_label": bool(label),
            })
        if (i // 50) % 20 == 0:
            print(f"  entities {i:,}/{len(qids):,}", flush=True)
    df = pd.DataFrame(sorted(rows, key=lambda r: r["qid"]))

    raw = pd.read_parquet(RAW / "museums.parquet")
    cmap = dict(zip(raw.country_qid, raw.country_label))
    miss = sorted({c for c in df.country_qid.unique() if c not in cmap and c != "NONE"})
    for i in range(0, len(miss), 50):
        r = request_json(WIKIDATA_API, namespace="rec_clab", method="POST", data={
            "action": "wbgetentities", "format": "json",
            "ids": "|".join(miss[i : i + 50]), "props": "labels", "languages": "en"})
        for q, e in r.get("entities", {}).items():
            cmap[q] = e.get("labels", {}).get("en", {}).get("value", q)
    cmap["NONE"] = "(no country)"
    df["country_label"] = df.country_qid.map(cmap).fillna(df.country_qid)
    write_parquet(df, path, expect_cols=["qid", "country_qid", "types"])
    return df


def build_sitelinks(qids: list[str]) -> pd.DataFrame:
    path = REC / "sitelinks.parquet"
    if path.exists():
        return pd.read_parquet(path)
    sites = wikipedia_sites()
    got = fetch_sitelinks(qids, workers=4,
                          on_progress=lambda n, t: print(f"  sitelinks {n:,}/{t:,}", flush=True))
    rows = [{"qid": q, "dbname": db, "lang": sites[db]["lang"],
             "api": sites[db]["url"] + "/w/api.php", "title": t}
            for q, by_db in got.items() for db, t in by_db.items() if db in sites]
    sl = pd.DataFrame(rows).sort_values(["qid", "dbname"]).reset_index(drop=True)
    write_parquet(sl, path, expect_cols=["qid", "lang", "title", "api"])
    return sl


def build_leads(sl: pd.DataFrame) -> pd.DataFrame:
    path = REC / "leads_all.parquet"
    if path.exists():
        return pd.read_parquet(path)
    by_api = sl.groupby("api").title.apply(list).to_dict()
    api2db = dict(zip(sl.api, sl.dbname))
    api2lang = dict(zip(sl.api, sl.lang))
    title2qid = {(a, t): q for a, t, q in zip(sl.api, sl.title, sl.qid)}
    frames = []

    def on_done(api, got, n_failed):
        rows = []
        for title, text in got.items():
            q = title2qid.get((api, title))
            if not q:
                continue
            text = normalize_ws(text)
            if text:
                rows.append({"qid": q, "lang": api2lang[api], "dbname": api2db[api],
                             "title": title, "text": text, "chars": len(text)})
        if rows:
            frames.append(pd.DataFrame(rows))
        if n_failed:
            print(f"  ! {api}: {n_failed} failed chunks", flush=True)

    fetch_leads_many(by_api, workers=4, on_wiki_done=on_done,
                     on_progress=lambda n, t, w: (
                         print(f"  leads {n:,}/{t:,} ({w} wikis left)", flush=True)
                         if n % 200 == 0 else None))
    allleads = pd.concat(frames, ignore_index=True)
    write_parquet(allleads, path, expect_cols=["qid", "lang", "text", "chars"])
    return allleads


def main() -> None:
    REC.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    qid_path = INTERIM / "gap" / "in_scope_qids.json"
    if not qid_path.exists():
        raise SystemExit(f"missing {qid_path} — run pipeline/p07_gap.py first")
    qids = sorted(json.load(open(qid_path)))
    print(f"{len(qids):,} recovered museums")

    mus = build_museums(qids)
    print(f"metadata: {len(mus):,} | coords {mus.lat.notna().mean():.1%} "
          f"| en label {mus.has_label.mean():.1%}")

    sl = build_sitelinks(list(mus.qid))
    print(f"sitelinks: {len(sl):,} articles across {sl.dbname.nunique()} wikis")

    allleads = build_leads(sl)
    print(f"leads: {len(allleads):,} articles, {allleads.qid.nunique():,} museums")

    best = select_leads(allleads, dict(zip(mus.qid, mus.country_qid)))
    best = best.merge(mus, on="qid", how="left", suffixes=("", "_m"))
    print(f"recovered with a usable lead: {len(best):,} / {len(mus):,}")

    full = pd.read_parquet(INTERIM / "full" / "leads.parquet")
    cols = list(full.columns)
    missing = [c for c in cols if c not in best.columns]
    if missing:
        raise SystemExit(f"recovered leads missing columns: {missing}")
    union = pd.concat([full[cols], best[cols]], ignore_index=True)
    assert union.qid.is_unique, "duplicate qid in union"
    write_parquet(union, OUT / "leads.parquet",
                  expect_cols=["qid", "lang", "text", "chars", "lat", "lon"])

    # p04's types for the originals; the recovered carry none by construction,
    # and 'other' is p04's label for exactly that.
    types = pd.read_parquet(INTERIM / "full" / "types.parquet")
    add = pd.DataFrame({"qid": mus.qid, "type_qid": "", "type_label": "other"})
    write_parquet(pd.concat([types, add], ignore_index=True).drop_duplicates("qid"),
                  OUT / "types.parquet", expect_cols=["qid", "type_label"])

    print(f"\nfull_recovered: {len(union):,} museums "
          f"({len(full):,} typed by Wikidata + {len(best):,} recovered)")
    print(f"median lead chars: typed {full.chars.median():.0f}, "
          f"recovered {best.chars.median():.0f}")


if __name__ == "__main__":
    main()
