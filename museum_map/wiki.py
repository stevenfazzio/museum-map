"""Wikibase + Wikipedia API helpers (all cached through museum_map.common.request_json)."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from museum_map.common import WIKIDATA_API, request_json

# action=query&prop=extracts is capped at 20 titles per request for anonymous callers.
EXTRACT_BATCH = 20
ENTITY_BATCH = 50

# The fetch is latency-bound, not throttle-bound: observed spacing is ~3.3 s per
# request against a 0.15 s floor, so the floor never binds in practice. It is
# raised here anyway because it becomes the *only* thing bounding per-host rate
# once several workers can land on the same wiki at once.
EXTRACT_MIN_INTERVAL = 0.5
ENTITY_MIN_INTERVAL = 0.5


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


def _sitelinks_chunk(chunk: list[str], sites: dict[str, dict]) -> dict[str, dict[str, str]]:
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
        min_interval=ENTITY_MIN_INTERVAL,
    )
    return {
        q: {db: sl["title"] for db, sl in ent.get("sitelinks", {}).items() if db in sites}
        for q, ent in res.get("entities", {}).items()
    }


def fetch_sitelinks(
    qids: list[str],
    *,
    workers: int = 1,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, dict[str, str]]:
    """qid -> {dbname: page title}, restricted to real Wikipedias.

    Every chunk hits the same host, so per-host throttling still spaces them;
    `workers` only overlaps the round-trip latency, which is what dominates.
    """
    sites = wikipedia_sites()
    ordered = sorted(qids)
    chunks = [ordered[i : i + ENTITY_BATCH] for i in range(0, len(ordered), ENTITY_BATCH)]
    out: dict[str, dict[str, str]] = {}

    if workers <= 1:
        for n, chunk in enumerate(chunks, 1):
            out.update(_sitelinks_chunk(chunk, sites))
            if on_progress:
                on_progress(n, len(chunks))
        return out

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_sitelinks_chunk, c, sites) for c in chunks]
        for n, fut in enumerate(as_completed(futures), 1):
            out.update(fut.result())
            if on_progress:
                on_progress(n, len(chunks))
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


def _extract_chunk(api_url: str, chunk: list[str]) -> dict[str, str]:
    """One extracts request. Raises on permanent failure; caller decides what that costs."""
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
        min_interval=EXTRACT_MIN_INTERVAL,
        timeout=60,
        max_retries=3,
    )
    query = res.get("query", {})
    forward = _resolve_title_map(query)
    by_final = {
        p["title"]: (p.get("extract") or "")
        for p in query.get("pages", [])
        if "missing" not in p
    }
    out = {}
    for t in chunk:
        text = by_final.get(forward.get(t, t), "")
        if text.strip():
            out[t] = text
    return out


def _chunks(titles: list[str]) -> list[list[str]]:
    ordered = sorted(titles)
    return [ordered[i : i + EXTRACT_BATCH] for i in range(0, len(ordered), EXTRACT_BATCH)]


def fetch_leads(api_url: str, titles: list[str]) -> dict[str, str]:
    """Requested title -> plain-text lead section (missing/empty pages omitted)."""
    out: dict[str, str] = {}
    for chunk in _chunks(titles):
        try:
            out.update(_extract_chunk(api_url, chunk))
        except Exception as exc:  # a single dead wiki must not kill the stage
            print(f"    ! {api_url}: {exc}")
    return out


def fetch_leads_many(
    jobs: dict[str, list[str]],
    *,
    workers: int = 4,
    on_wiki_done: Callable[[str, dict[str, str], int], None],
    on_progress: Callable[[int, int, int], None] | None = None,
) -> None:
    """Fetch leads across many wikis concurrently, reporting each wiki as it finishes.

    Work is queued at (wiki, 20-title chunk) granularity rather than per wiki. One
    worker per wiki would be near-useless here: the article distribution is severely
    skewed, so enwiki alone would still be running long after the other ~300 wikis
    had finished and freed their workers.

    `on_wiki_done(api_url, {title: lead}, n_failed_chunks)` fires as soon as a wiki's
    last chunk lands, and its results are dropped immediately afterwards, so peak
    memory tracks the widest concurrent wiki rather than the whole corpus. A wiki
    that reports failed chunks is incomplete — the caller should not treat it as
    done for resumption purposes.
    """
    tasks = [(api, chunk) for api, titles in jobs.items() for chunk in _chunks(titles)]
    # Largest wikis first: their long tail of chunks is what sets total wall-clock,
    # so they should be in flight from the start rather than picked up at the end.
    tasks.sort(key=lambda t: (-len(jobs[t[0]]), t[0]))

    pending = {api: 0 for api in jobs}
    for api, _ in tasks:
        pending[api] += 1
    results: dict[str, dict[str, str]] = {api: {} for api in jobs}
    failures: dict[str, int] = dict.fromkeys(jobs, 0)

    # Wikis with no titles never get a task, so they would otherwise never be
    # reported; settle them up front.
    for api in [a for a, n in pending.items() if n == 0]:
        on_wiki_done(api, {}, 0)
        del pending[api], results[api]

    done_tasks = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_extract_chunk, api, chunk): api for api, chunk in tasks}
        for fut in as_completed(futures):
            api = futures[fut]
            try:
                results[api].update(fut.result())
            except Exception as exc:
                failures[api] += 1
                print(f"    ! {api}: {exc}", flush=True)
            pending[api] -= 1
            done_tasks += 1
            if pending[api] == 0:
                on_wiki_done(api, results.pop(api), failures[api])
                del pending[api]
            if on_progress:
                on_progress(done_tasks, len(tasks), len(pending))
