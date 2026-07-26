"""Wikibase + Wikipedia API helpers (all cached through probe.common.request_json)."""

from __future__ import annotations

from probe.common import WIKIDATA_API, request_json

# action=query&prop=extracts is capped at 20 titles per request for anonymous callers.
EXTRACT_BATCH = 20
ENTITY_BATCH = 50


def wikipedia_sites() -> dict[str, dict]:
    """dbname -> {lang, url} for every open Wikipedia.

    Sitelink keys cannot be filtered by an `endswith("wiki")` rule: `abstractwiki`,
    `commonswiki`, `specieswiki` and friends all match it but are not Wikipedias.
    The sitematrix is authoritative.
    """
    res = request_json(
        WIKIDATA_API,
        namespace="sitematrix",
        params={"action": "sitematrix", "format": "json", "formatversion": "2"},
    )
    out: dict[str, dict] = {}
    for key, group in res["sitematrix"].items():
        if not key.isdigit():
            continue
        for site in group.get("site", []):
            if site.get("code") != "wiki" or "closed" in site:
                continue
            out[site["dbname"]] = {"lang": group.get("code", ""), "url": site["url"]}
    return out


def fetch_sitelinks(qids: list[str]) -> dict[str, dict[str, str]]:
    """qid -> {dbname: page title}, restricted to real Wikipedias."""
    sites = wikipedia_sites()
    out: dict[str, dict[str, str]] = {}
    for i in range(0, len(qids), ENTITY_BATCH):
        chunk = sorted(qids[i : i + ENTITY_BATCH])
        res = request_json(
            WIKIDATA_API,
            namespace="wbsitelinks",
            params={
                "action": "wbgetentities",
                "format": "json",
                "formatversion": "2",
                "props": "sitelinks",
                "ids": "|".join(chunk),
            },
        )
        for q, ent in res.get("entities", {}).items():
            out[q] = {
                db: sl["title"]
                for db, sl in ent.get("sitelinks", {}).items()
                if db in sites
            }
    return out


def fetch_labels_aliases(qids: list[str]) -> dict[str, set[str]]:
    """qid -> every label and alias in every language (the location gazetteer source)."""
    out: dict[str, set[str]] = {}
    uniq = sorted(set(qids))
    for i in range(0, len(uniq), ENTITY_BATCH):
        chunk = uniq[i : i + ENTITY_BATCH]
        res = request_json(
            WIKIDATA_API,
            namespace="wblabels",
            params={
                "action": "wbgetentities",
                "format": "json",
                "formatversion": "2",
                "props": "labels|aliases",
                "ids": "|".join(chunk),
            },
        )
        for q, ent in res.get("entities", {}).items():
            names: set[str] = set()
            for lab in ent.get("labels", {}).values():
                names.add(lab["value"])
            for al in ent.get("aliases", {}).values():
                for a in al:
                    names.add(a["value"])
            out[q] = names
    return out


def fetch_en_labels(qids: list[str]) -> dict[str, str]:
    """qid -> English label (falls back to the qid itself)."""
    out: dict[str, str] = {}
    uniq = sorted(set(qids))
    for i in range(0, len(uniq), ENTITY_BATCH):
        chunk = uniq[i : i + ENTITY_BATCH]
        res = request_json(
            WIKIDATA_API,
            namespace="wblabels_en",
            params={
                "action": "wbgetentities",
                "format": "json",
                "formatversion": "2",
                "props": "labels",
                "languages": "en",
                "ids": "|".join(chunk),
            },
        )
        for q, ent in res.get("entities", {}).items():
            out[q] = ent.get("labels", {}).get("en", {}).get("value", q)
    return {q: out.get(q, q) for q in uniq}


def _resolve_title_map(query: dict) -> dict[str, str]:
    """Requested title -> final title, following normalization then redirects."""
    step: dict[str, str] = {}
    for key in ("normalized", "redirects"):
        for m in query.get(key, []):
            step[m["from"]] = m["to"]
    resolved: dict[str, str] = {}
    for src in list(step):
        cur, seen = src, set()
        while cur in step and cur not in seen:
            seen.add(cur)
            cur = step[cur]
        resolved[src] = cur
    return resolved


def fetch_leads(api_url: str, titles: list[str]) -> dict[str, str]:
    """Requested title -> plain-text lead section (missing/empty pages omitted)."""
    out: dict[str, str] = {}
    for i in range(0, len(titles), EXTRACT_BATCH):
        chunk = sorted(titles[i : i + EXTRACT_BATCH])
        try:
            res = request_json(
                api_url,
                namespace="extracts",
                params={
                    "action": "query",
                    "format": "json",
                    "formatversion": "2",
                    "prop": "extracts",
                    "exintro": "1",
                    "explaintext": "1",
                    "exlimit": str(EXTRACT_BATCH),
                    "redirects": "1",
                    "titles": "|".join(chunk),
                },
                min_interval=0.15,
                timeout=60,
                max_retries=3,
            )
        except Exception as exc:  # a single dead wiki must not kill the stage
            print(f"    ! {api_url}: {exc}")
            continue
        query = res.get("query", {})
        forward = _resolve_title_map(query)
        by_final = {
            p["title"]: (p.get("extract") or "")
            for p in query.get("pages", [])
            if "missing" not in p
        }
        for t in chunk:
            text = by_final.get(forward.get(t, t), "")
            if text.strip():
                out[t] = text
    return out
