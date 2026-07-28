"""Finding museums Wikidata does not type as museums.

`p01_harvest` defines the corpus as `wdt:P31/wdt:P279* wd:Q33506`, which is a
claim about Wikidata's typing rather than about the world. It misses 5,560
museums that have a Wikipedia article and sit in that wiki's museum category
tree — 24% of US museums, against 2% for Italy and Japan. See `COVERAGE.md`.

This module is the second recall channel: walk each wiki's museum category tree
and ask, of every article not already in the corpus, whether its own text calls
it a museum.

Three things here were learned the hard way and are load-bearing.

**Containment, not blocklisting.** Only descend into a category that is itself
museum-named. A name-based blocklist cannot anticipate where a category graph
goes: at depth 12 from `Category:Museums` it still reached "National Film
Registry films" (749 articles), "Royal Academicians" (594) and "Psalms" (188),
by way of a museum -> its collection -> the works in it. Containment cut the
English crawl from 63,964 articles to 33,216 and lost nothing real.

**Per-wiki configuration comes from Wikidata, not from hand-written lists.**
Q33506 carries labels in 192 languages and its P910 category has sitelinks on
196 wikis. Hand-writing stems for 30 languages is both tedious and wrong:
Japanese needs 博物館 *and* 美術館 (no shared characters), and Arabic's category
is the broken plural متاحف, which does not contain the singular متحف.

**A drift term that matches a wiki's own vocabulary empties it in silence.**
`musei` was added to catch `museologia`; it is Italian for *museums* and pruned
the entire Italian tree to 9 articles — a plausible small number, not an error.
`check_drift(...)` fails loudly on that class of mistake.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

from museum_map.common import WIKIDATA_API, request_json

MUSEUM = "Q33506"
MAIN_CAT = "Q7139164"  # P910 of Q33506: the "Museums" category, sitelinked per wiki

# Major subclasses, so a language with a distinct word per museum kind is covered.
# Every QID here is looked up, never recalled: on the first pass Q1091803 (the
# natural number 335) and Q184876 ("frame of reference") were supplied from
# memory and put "335" and "bezugssystem" into 28 of 30 derived configs.
SUBCLASSES = [
    "Q207694",    # art museum
    "Q16735822",  # history museum
    "Q1595639",   # local museum
    "Q756102",    # open-air museum
    "Q3329412",   # archaeological museum
    "Q1970365",   # natural history museum
    "Q2772772",   # military museum
    "Q12104174",  # ethnographic museum
    "Q1863818",   # maritime museum
    "Q18704634",  # railway museum
    "Q588140",    # science museum
    "Q1007870",   # art gallery
    "Q2281788",   # public aquarium
    "Q148319",    # planetarium
]
CJK = {"ja", "zh", "ko", "zh-hans", "zh-hant", "wuu", "yue"}

MAX_DEPTH = 12

# Branches inside the museum domain that are about people or lists. Containment
# keeps the walk in the domain; this keeps it out of the domain's biographical
# corners. Anything slipping through is caught by NOT_AN_INSTITUTION later.
DRIFT = re.compile(
    r"""\b(
      lists? \s+ of | collections? | curators? | directors? | founders? | people
    | staff | employees | stubs? | museology | proposed | images | photographs
    | inductees? | recipients? | honou?rees? | laureates? | winners?
    | listen? | sammlung(en)? | kurator(en|in)? | direktor(en|in)? | personen?
    | museumsleiter | gemälde | skulptur(en)? | ausstellung(en)?
    | muzealnicy | muséologie | museologia
    )\b""",
    re.I | re.X,
)

# Wikidata classes that cannot be an institution, whatever an article says.
NOT_AN_INSTITUTION = {
    "Q5",           # human
    "Q13406463",    # Wikimedia list article
    "Q11753321",    # Wikimedia navigational template
    "Q4167410",     # Wikimedia disambiguation page
    "Q17317604",    # professional wrestling event
    "Q138840755",   # hall of fame ceremony
    "Q1656682",     # event
    "Q3305213",     # painting
    "Q860861",      # sculpture
    "Q571",         # book
    "Q11424",       # film
    "Q366301",      # scientific expedition
}

# Classes kept out of the recovered corpus because they are outside the Q33506
# closure the corpus is defined by. Counting them would measure a different
# corpus than the one that exists.
OUT_OF_SCOPE = {
    "Q130326199",  # preserved watercraft
    "Q11446",      # ship
    "Q2055880",    # sailing ship
    "Q1229765",    # watercraft
    "Q1007870",    # art gallery (a dealer gallery is not a museum)
}

_print_lock = threading.Lock()


def _log(msg):
    with _print_lock:
        print(msg, flush=True)


def _entities(ids, props, namespace):
    out = {}
    for i in range(0, len(ids), 50):
        r = request_json(WIKIDATA_API, namespace=namespace, method="POST", data={
            "action": "wbgetentities", "format": "json",
            "ids": "|".join(ids[i : i + 50]), "props": props})
        out.update(r.get("entities", {}))
    return out


def _stem(word: str, lang: str) -> str:
    """Crude inflection-tolerant stem. CJK does not inflect, so keep it whole."""
    w = word.strip().lower()
    if lang in CJK or len(w) <= 4:
        return w
    return w[: max(4, len(w) - 2)]


def derive_config(dbnames: list[str]) -> dict:
    """dbname -> {lang, root category, museum stems}, entirely from Wikidata."""
    ent = _entities([MUSEUM, MAIN_CAT] + SUBCLASSES, "labels|aliases|sitelinks", "gap_cfg")
    cats = ent[MAIN_CAT]["sitelinks"]
    cfg = {}
    for dbname in dbnames:
        site = cats.get(dbname)
        if not site:
            continue
        title = site["title"]
        lang = dbname[:-4].replace("_", "-")
        words = {title.split(":", 1)[1]} if ":" in title else {title}
        for qid in [MUSEUM] + SUBCLASSES:
            lab = ent.get(qid, {}).get("labels", {}).get(lang, {}).get("value")
            if lab:
                words.add(lab)
        for a in ent.get(MUSEUM, {}).get("aliases", {}).get(lang, []):
            words.add(a["value"])
        # Multiword terms are kept whole: Vietnamese for museum is "Bảo tàng",
        # and dropping multiword entries left viwiki with no stem at all.
        stems = sorted({_stem(w, lang) if " " not in w else w.strip().lower()
                        for w in words if w}, key=len)
        keep = []
        for st in stems:
            if not any(st.startswith(k) for k in keep):
                keep.append(st)
        cfg[dbname] = {"lang": lang, "root": title, "stems": keep}
    return cfg


def check_drift(cfg: dict) -> None:
    """Fail loudly if a drift term matches a wiki's own museum vocabulary."""
    bad = []
    for db, c in cfg.items():
        root = c["root"].split(":", 1)[1] if ":" in c["root"] else c["root"]
        for probe in [root] + c["stems"]:
            if DRIFT.search(probe):
                bad.append((db, probe))
    if bad:
        for db, probe in bad:
            print(f"  !! DRIFT matches {db}'s own vocabulary: {probe!r}")
        raise SystemExit("drift list collides with museum vocabulary; fix before crawling")


def _members(api, cat):
    pages, subs, cont = [], [], {}
    while True:
        r = request_json(api, namespace="catmem", min_interval=0.4, params={
            "action": "query", "format": "json", "formatversion": "2",
            "list": "categorymembers", "cmtitle": cat, "cmtype": "page|subcat",
            "cmlimit": "500", **cont})
        for m in r["query"]["categorymembers"]:
            (subs if m["ns"] == 14 else pages).append(m["title"])
        if "continue" not in r:
            return pages, subs
        cont = r["continue"]


def crawl_wiki(dbname: str, cfg: dict, n_corpus: int = 0) -> dict[str, str]:
    """Article title -> the category it was found in, for one wiki."""
    api = f"https://{cfg['lang']}.wikipedia.org/w/api.php"
    keep = re.compile("|".join(re.escape(s) for s in cfg["stems"]), re.I)
    seen, articles, pruned = {cfg["root"]}, {}, 0
    q = deque([(cfg["root"], 0)])
    n = 0
    while q:
        cat, depth = q.popleft()
        try:
            pages, subs = _members(api, cat)
        except Exception as exc:
            _log(f"  ! {dbname} {cat}: {exc}")
            continue
        for p in pages:
            articles.setdefault(p, cat)
        if depth < MAX_DEPTH:
            for s in subs:
                if s in seen:
                    continue
                seen.add(s)
                name = s.split(":", 1)[1] if ":" in s else s
                if DRIFT.search(name) or not keep.search(name):
                    pruned += 1
                    continue
                q.append((s, depth + 1))
        n += 1
        if n % 500 == 0:
            _log(f"  {dbname}: {n:,} cats, {len(q):,} queued, {len(articles):,} articles")
    # The tree is a superset of the corpus by construction, so far fewer articles
    # than the corpus already holds for this wiki means the config or the drift
    # list silently emptied it.
    flag = ""
    if n_corpus and len(articles) < 0.5 * n_corpus:
        flag = f"  <-- SUSPECT: {len(articles):,} vs {n_corpus:,} in corpus"
    _log(f"  {dbname}: DONE {n:,} cats, {pruned:,} pruned, {len(articles):,} articles{flag}")
    return articles


def crawl_all(cfg: dict, corpus_sizes: dict, workers: int = 3) -> dict[str, dict]:
    """Crawl every configured wiki. One process, so the global throttle applies.

    Separate processes each keep their own throttle clock; running two at once
    tripped WMF's rate limit and both stalled in exponential backoff at zero
    successful requests.
    """
    check_drift(cfg)
    out = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(crawl_wiki, db, c, corpus_sizes.get(db, 0)): db
                for db, c in cfg.items()}
        for f in as_completed(futs):
            db = futs[f]
            try:
                out[db] = f.result()
            except Exception as exc:
                _log(f"  ! {db} FAILED: {exc}")
    return out


def pageprops(api, titles):
    """title -> (qid, shortdesc, resolved_title), following redirects.

    POST, not GET: 50 titles of Cyrillic, Arabic or Georgian percent-encode to
    6-9 bytes per character and overflow the URL length limit. ruwiki, ukwiki,
    arwiki, arzwiki, hewiki, hywiki, bgwiki and kawiki all died on "414 URI Too
    Long" while every Latin-script wiki passed.

    The resolved title matters: "Boston Tea Party Ships and Museum" redirects to
    "Boston Tea Party", the 1773 event.
    """
    out = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i : i + 50]
        r = request_json(api, namespace="pageprops_post", method="POST", data={
            "action": "query", "format": "json", "formatversion": "2",
            "prop": "pageprops", "redirects": "1", "titles": "|".join(chunk)})
        q = r.get("query", {})
        fwd = {}
        for key in ("normalized", "redirects"):
            for m in q.get(key, []):
                fwd[m["from"]] = m["to"]
        by_final = {p["title"]: p for p in q.get("pages", []) if "missing" not in p}
        for t in chunk:
            p = by_final.get(fwd.get(t, t))
            if not p:
                continue
            pp = p.get("pageprops", {})
            if pp.get("wikibase_item"):
                out[t] = (pp["wikibase_item"], pp.get("wikibase-shortdesc", ""), p["title"])
    return out


def p31_of(qids):
    out = {}
    for i in range(0, len(qids), 50):
        r = request_json(WIKIDATA_API, namespace="wbclaims_post", method="POST", data={
            "action": "wbgetentities", "format": "json",
            "ids": "|".join(qids[i : i + 50]), "props": "claims"})
        for q, e in r.get("entities", {}).items():
            out[q] = [s["mainsnak"]["datavalue"]["value"]["id"]
                      for s in e.get("claims", {}).get("P31", [])
                      if s["mainsnak"].get("datavalue")]
    return out


# ---------------------------------------------------------------------------
# Classification
#
# One Haiku pass in every language, replacing per-language regexes. Those hit
# 90% precision but only 39-67% recall in English, because the hard cases are
# judgement calls rather than lexical variants: a castle housing a museum, a
# heritage railway, a coin cabinet. Two lighthouse leads are near-identical
# whether or not one is a museum; reading separates them, patterns do not.
#
# Validated against hand-scored English samples: 7/7 recall on museums the regex
# missed, 0/18 false positives on hand-judged negatives.
# ---------------------------------------------------------------------------

CLASSIFY_MODEL = "claude-haiku-4-5"
BATCH = 10
CONCURRENCY = 8
MAX_LEAD_CHARS = 700

SYSTEM = """\
You decide whether each item is a museum, for a project mapping the world's museums.

You will get a numbered list. Each entry has a title, an optional one-line \
description, and the opening of its Wikipedia article, in any language.

Label each with exactly one of:

"museum" - the subject ITSELF is an institution or site that collects, preserves \
and exhibits a collection for the public. Includes history and art museums, \
historic house museums, open-air museums, heritage railways and museum ships, \
memorial and site museums, treasuries, coin cabinets, herbaria and science museums.

"partly" - the subject is primarily something else (a castle, palace, church, \
fort, park, farm, library, company, university) but houses, contains or operates \
a museum. Use this when the museum is a component of the subject, not the \
subject itself.

"adjacent" - a public attraction of a kind this project does not count as a \
museum: a commercial art gallery that sells work, an aquarium, a planetarium, a \
zoo, or a botanical garden. A publicly-owned ART MUSEUM is "museum"; a dealer \
gallery is "adjacent".

"not" - anything else. A person, a painting or object, a street, an event, a \
species, a list, a film, a video game. Also use "not" for an organisation that \
merely runs or funds museums without being one, and for an award or hall of fame \
that is only a list of honourees with no physical collection.

A building that stands near, inside or behind a museum, or is one exhibit \
building within a larger museum site, is "not" - not "partly". Reserve "partly" \
for a subject that is itself a substantial place housing a museum.

TWO CASES THAT LOOK LIKE MUSEUMS AND ARE NOT.

1. A general article about a KIND of museum, rather than about one specific \
institution, is "not". "An agricultural museum is a museum dedicated to \
preserving agricultural history", "a hembygdsgard is a small local open-air \
museum in Sweden", "an insectarium is a type of zoo or museum for insects" - \
these define a category. Only a specific, named institution can be "museum". If \
the opening sentence defines what the term means rather than describing one \
place, answer "not".

2. A ship, boat, submarine, aircraft, locomotive or other vehicle is "not" \
UNLESS the text says it is preserved as a museum ship or museum vessel, or is \
itself open to visitors as a museum. Being historic, heritage-listed, preserved \
or k-marked is NOT enough - naval and fishing vessels sit in museum categories \
without being museums.

DECIDE FROM THE TEXT, not from what you know. You may recognise some of these; \
ignore that. If the text does not indicate a museum, the answer is "not", even \
if you believe the place has one. If the text is too thin to tell, answer "not".

Reply with a JSON object mapping each number to its label, and nothing else:
{"1": "museum", "2": "not", "3": "partly", "4": "adjacent"}"""

VALID = {"museum", "not", "partly", "adjacent"}


def _build_prompt(rows):
    parts = []
    for n, title, desc, lead in rows:
        head = f"{n}. [{title}]"
        if desc:
            head += f" ({desc})"
        parts.append(f"{head}\n{(lead or '(no text)')[:MAX_LEAD_CHARS]}")
    return "\n\n".join(parts)


def _parse_reply(text, n):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        raw = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    out = {}
    for k, v in raw.items():
        try:
            i = int(str(k).strip())
        except ValueError:
            continue
        v = str(v).strip().lower()
        if 1 <= i <= n and v in VALID:
            out[i] = v
    return out


async def classify(items, model=CLASSIFY_MODEL, batch=BATCH, concurrency=CONCURRENCY,
                   on_progress=None):
    """items: list of (key, title, shortdesc, lead) -> ({key: label}, (tok_in, tok_out))."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set")
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic()
    batches = [items[i : i + batch] for i in range(0, len(items), batch)]
    sem = asyncio.Semaphore(concurrency)
    out, usage, done = {}, [0, 0], [0]

    async def one(chunk):
        rows = [(n + 1, t, d, ld) for n, (_, t, d, ld) in enumerate(chunk)]
        async with sem:
            for attempt in range(3):
                try:
                    resp = await client.messages.create(
                        model=model, max_tokens=1024, system=SYSTEM,
                        messages=[{"role": "user", "content": _build_prompt(rows)}])
                    text = next((b.text for b in resp.content if b.type == "text"), "")
                    got = _parse_reply(text, len(rows))
                    usage[0] += resp.usage.input_tokens
                    usage[1] += resp.usage.output_tokens
                    for n, (key, *_) in enumerate(chunk, 1):
                        if n in got:
                            out[key] = got[n]
                    break
                except Exception as exc:
                    if attempt == 2:
                        print(f"    ! batch failed: {type(exc).__name__}: {exc}", flush=True)
                    else:
                        await asyncio.sleep(2**attempt * 2)
        done[0] += 1
        if on_progress and done[0] % 25 == 0:
            on_progress(done[0], len(batches))

    await asyncio.gather(*(one(c) for c in batches))
    return out, tuple(usage)
