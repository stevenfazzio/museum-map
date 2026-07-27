"""Paths and shared helpers for the map pipeline.

Every stage runs against either corpus via `--corpus`, so the two must never be
able to touch each other's files. Full-corpus artefacts live under their own
subdirectories rather than being distinguished by a filename suffix, which makes
an accidental overwrite a missing-file error instead of silent corruption.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from museum_map.common import INTERIM, PROCESSED, ROOT, qid, sparql  # noqa: E402,F401

FULL_INTERIM = INTERIM / "full"
FULL_PROCESSED = PROCESSED / "full"
LEAD_SHARDS = FULL_INTERIM / "lead_shards"

for _d in (FULL_INTERIM, FULL_PROCESSED, LEAD_SHARDS):
    _d.mkdir(parents=True, exist_ok=True)


CORPORA = ("fixture", "full")


def corpus_paths(name: str) -> tuple[Path, Path]:
    """(leads parquet, output dir) for a corpus name.

    `fixture` is a 2,000-museum random sample of the corpus (p05), kept as the
    fast iteration path; `full` is all 49,218 museums with a usable lead. Every
    map stage takes `--corpus` and is otherwise identical between the two, so
    nothing can be validated on the fixture and then silently diverge on the real
    run.
    """
    if name not in CORPORA:
        raise SystemExit(f"unknown corpus {name!r}; expected one of {CORPORA}")
    if name == "full":
        leads = FULL_INTERIM / "leads.parquet"
    else:
        # The fixture is a random sample of the finished corpus, built by p05.
        # It deliberately does not reuse the probe stratified sample.
        leads = INTERIM / "fixture_leads.parquet"
        if not leads.exists():
            raise SystemExit(f"missing {leads} — run pipeline/p05_fixture.py first")
    out = PROCESSED / f"map_{name}"
    out.mkdir(parents=True, exist_ok=True)
    if not leads.exists():
        raise SystemExit(f"missing {leads} — run the fetch stages for corpus {name!r} first")
    return leads, out


# ------------------------------------------------------- which lead represents a museum

# A museum's lead is taken from its country's official language when that article
# is at least this fraction as long as the longest article in any language;
# otherwise the longest wins.
#
# Plain longest-wins leaves 30.4% of the museums that *have* a local-language
# article represented by a different one. The confound that creates is not
# language — BGE-M3 is cross-lingually aligned and per-language centring runs on
# top — but *perspective*: the Spanish article on the Seoul Museum of Art leads
# with a Joseon royal palace, the Korean one leads with its status as a bureau of
# the city government. Those place the museum differently in subject space, and
# nothing downstream removes it. It is also not randomly distributed: museums in
# countries with a small Wikipedia get described by whoever found them
# interesting from outside.
#
# Always preferring the local article overcorrects. It pushes the share of leads
# under 200 characters from 18.4% to 23.7% — a 29% increase in the bucket that
# already labels worst (48.4% unlabelled on the fixture) — because 26.4% of local
# articles are stubs. At 0.5 the trade is 13 points of locality (56.0% -> 69.1%)
# for one point of stubs (18.4% -> 19.4%).
LOCAL_MIN_FRACTION = 0.5

COUNTRY_LANGS = """
SELECT ?c ?code WHERE {
  ?c wdt:P31/wdt:P279* wd:Q6256 .
  ?c wdt:%s ?lang .
  ?lang wdt:P424 ?code .
}
"""

# P37 is "official language"; P2936 is "language used". P37 alone is not a usable
# definition of "the local language" for three reasons found in the corpus:
#
#   * A country can have no official language. Wikidata lists the United States'
#     P37 as Spanish and Hawaiian — English is absent, because there is no
#     federal official language. Under P37 alone the rule therefore treats
#     Spanish as local for all 5,080 US museums and actively prefers the Spanish
#     article over the English one.
#   * P37 codes are not always Wikipedia codes. China's is `zh-cn` and Taiwan's
#     `zh-tw`; Wikipedia has neither, only `zh`, so no Chinese article ever
#     counted as local for a Chinese or Taiwanese museum.
#   * P2936 alone is no better — it skews to minority and indigenous languages
#     (China's list is Tibetan, Hakka, Kazakh...; Japan's includes Ainu).
#
# The union of the two, with region subtags stripped when the bare code is a real
# Wikipedia, covers every country in the corpus with 100+ museums.
LANG_PROPERTIES = ("P37", "P2936")


def official_languages(wiki_langs: set[str] | None = None) -> dict[str, set[str]]:
    """country QID -> Wikipedia language codes spoken there (cached).

    `wiki_langs` is the set of codes that actually exist as Wikipedias; a
    Wikidata code is kept when it is one of those, and otherwise retried with its
    region subtag stripped (`zh-tw` -> `zh`). Codes that match neither are
    dropped, which is what should happen to a language with no Wikipedia.
    """
    raw: dict[str, set[str]] = {}
    for prop in LANG_PROPERTIES:
        for row in sparql(COUNTRY_LANGS % prop, namespace=f"wdqs_country_lang_{prop}"):
            raw.setdefault(qid(row["c"]), set()).add(row["code"])
    if wiki_langs is None:
        return raw

    out: dict[str, set[str]] = {}
    for country, codes in raw.items():
        keep = set()
        for code in codes:
            if code in wiki_langs:
                keep.add(code)
            elif "-" in code and code.split("-")[0] in wiki_langs:
                # `be-tarask` and `zh-yue` are real Wikipedias and are kept by the
                # branch above; this only fires for region subtags that are not.
                keep.add(code.split("-")[0])
        if keep:
            out[country] = keep
    return out


def select_leads(
    all_leads: pd.DataFrame,
    country_by_qid: dict[str, str],
    *,
    min_fraction: float = LOCAL_MIN_FRACTION,
) -> pd.DataFrame:
    """One row per museum: the local-language lead if long enough, else the longest.

    `all_leads` needs qid/lang/chars. Ties break on language code so re-runs are
    identical. Museums whose country has no language on record, or which have no
    article in one, fall through to longest-wins.
    """
    # The corpus's own language set is what decides whether a Wikidata code names
    # a real Wikipedia, so it is derived here rather than fetched again.
    langs = official_languages(set(all_leads.lang.unique()))
    local = [lg in langs.get(country_by_qid.get(q, ""), ()) for q, lg in
             zip(all_leads.qid, all_leads.lang)]
    df = all_leads.assign(is_local=local)

    longest = df.groupby("qid").chars.transform("max")
    # A local article is eligible only if it is not much thinner than the best
    # available; `eligible` is then sorted ahead of everything else.
    df = df.assign(eligible=df.is_local & (df.chars >= min_fraction * longest))
    return (
        df.sort_values(["qid", "eligible", "chars", "lang"],
                       ascending=[True, False, False, True])
        .drop_duplicates("qid", keep="first")
        .drop(columns=["eligible"])
        .reset_index(drop=True)
    )


def fmt_eta(seconds: float) -> str:
    if seconds < 0 or seconds != seconds or seconds == float("inf"):
        return "?"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"
