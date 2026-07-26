"""Shared plumbing: paths, on-disk HTTP cache, polite retrying session.

Every network response is cached to disk keyed by a hash of the full request, so
reruns of any stage are free and the whole experiment is reproducible offline
once the cache is warm.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import random
import tempfile
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "cache"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
REPORTS = ROOT / "reports"
FIGS = REPORTS / "figs"

for _d in (CACHE, RAW, INTERIM, PROCESSED, REPORTS, FIGS):
    _d.mkdir(parents=True, exist_ok=True)

SEED = 42
N_SAMPLE = 2000

USER_AGENT = (
    "museum-map-probe/0.1 (https://github.com/stevenfazzio/museum-map; fazzios@gmail.com) "
    "python-requests"
)

WDQS = "https://query.wikidata.org/sparql"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"

# ---------------------------------------------------------------- disk cache


def _key(namespace: str, payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(f"{namespace}\x00{blob}".encode()).hexdigest()


def cache_path(namespace: str, payload: Any) -> Path:
    h = _key(namespace, payload)
    p = CACHE / namespace / h[:2]
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{h}.json.gz"


def cache_get(namespace: str, payload: Any) -> Any | None:
    p = cache_path(namespace, payload)
    if not p.exists():
        return None
    try:
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, EOFError, json.JSONDecodeError):
        p.unlink(missing_ok=True)  # corrupt/partial entry: drop and refetch
        return None


def cache_put(namespace: str, payload: Any, value: Any) -> None:
    p = cache_path(namespace, payload)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    os.close(fd)
    try:
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(value, fh, ensure_ascii=False)
        os.replace(tmp, p)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------- atomic IO


def write_parquet(df, path: Path, *, expect_cols: list[str] | None = None) -> None:
    """Write-new-then-verify-then-rename. Never clobber an expensive file in place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".parquet.tmp")
    os.close(fd)
    try:
        df.to_parquet(tmp, index=False)
        import pandas as pd

        back = pd.read_parquet(tmp)
        assert len(back) == len(df), f"row mismatch {len(back)} != {len(df)}"
        if expect_cols:
            missing = set(expect_cols) - set(back.columns)
            assert not missing, f"missing columns {missing}"
        os.replace(tmp, path)
        print(f"  wrote {path.relative_to(ROOT)}  ({len(df):,} rows, {len(df.columns)} cols)")
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------- http


_LAST_CALL: dict[str, float] = {}
_SESSION: requests.Session | None = None


def session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
        _SESSION = s
    return _SESSION


def _throttle(host: str, min_interval: float) -> None:
    now = time.monotonic()
    last = _LAST_CALL.get(host, 0.0)
    wait = min_interval - (now - last)
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL[host] = time.monotonic()


class HttpError(RuntimeError):
    pass


def request_json(
    url: str,
    *,
    namespace: str,
    params: dict | None = None,
    data: dict | None = None,
    method: str = "GET",
    min_interval: float = 0.2,
    max_retries: int = 5,
    timeout: int = 90,
    cache: bool = True,
) -> Any:
    """Cached, throttled, retrying JSON fetch. Cache key covers url+params+data."""
    ckey = {"url": url, "params": params, "data": data, "method": method}
    if cache:
        hit = cache_get(namespace, ckey)
        if hit is not None:
            return hit

    host = url.split("/")[2]
    last_err: Exception | None = None
    for attempt in range(max_retries):
        _throttle(host, min_interval)
        try:
            resp = session().request(
                method, url, params=params, data=data, timeout=timeout
            )
            if resp.status_code in (429, 502, 503, 504):
                raise HttpError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            ctype = resp.headers.get("Content-Type", "")
            if "json" not in ctype:
                raise HttpError(f"non-JSON response ({ctype}): {resp.text[:200]}")
            value = resp.json()
        except (requests.RequestException, HttpError, json.JSONDecodeError) as exc:
            last_err = exc
            if attempt == max_retries - 1:
                break
            backoff = min(2**attempt * 3, 60) + random.uniform(0, 2)
            print(f"    retry {attempt + 1}/{max_retries} after {exc} -> sleep {backoff:.1f}s")
            time.sleep(backoff)
            continue
        if cache:
            cache_put(namespace, ckey, value)
        return value
    raise HttpError(f"failed after {max_retries} attempts: {url} :: {last_err}")


def sparql(query: str, *, namespace: str = "wdqs", timeout: int = 90) -> list[dict]:
    """Run a WDQS query (POST — GET 502s on long queries) and return simplified bindings."""
    res = request_json(
        WDQS,
        namespace=namespace,
        method="POST",
        data={"query": query, "format": "json"},
        min_interval=1.0,
        timeout=timeout,
    )
    return [{k: v["value"] for k, v in row.items()} for row in res["results"]["bindings"]]


def qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]
