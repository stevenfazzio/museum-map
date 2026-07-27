"""Paths and shared helpers for the full-corpus build.

The probe's 2,000-museum artefacts stay exactly where they are and keep their
names — they are the dev fixture now, and every build stage must be runnable
against either corpus. Full-corpus artefacts therefore live in their own
subdirectories rather than being distinguished by filename suffix, so nothing
here can overwrite a fixture file by accident.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from probe.common import INTERIM, PROCESSED, ROOT, qid, sparql  # noqa: E402,F401

FULL_INTERIM = INTERIM / "full"
FULL_PROCESSED = PROCESSED / "full"
LEAD_SHARDS = FULL_INTERIM / "lead_shards"

for _d in (FULL_INTERIM, FULL_PROCESSED, LEAD_SHARDS):
    _d.mkdir(parents=True, exist_ok=True)


CORPORA = ("fixture", "full")


def corpus_paths(name: str) -> tuple[Path, Path]:
    """(leads parquet, output dir) for a corpus name.

    `fixture` is the probe's 2,000-museum sample, kept as the fast iteration path;
    `full` is all 55,280. Every map stage takes `--corpus` and is otherwise
    identical between the two, so nothing can be validated on the fixture and then
    silently diverge on the real run.
    """
    if name not in CORPORA:
        raise SystemExit(f"unknown corpus {name!r}; expected one of {CORPORA}")
    if name == "full":
        leads = FULL_INTERIM / "leads.parquet"
    else:
        # b04 re-selects the fixture's leads under the map's rule; the probe's own
        # leads.parquet keeps the longest-wins rule that report.md was written from.
        leads = INTERIM / "fixture_map_leads.parquet"
        if not leads.exists():
            raise SystemExit(f"missing {leads} — run build/b04_fixture_leads.py first")
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
  ?c wdt:P37 ?lang .
  ?lang wdt:P424 ?code .
}
"""


def official_languages() -> dict[str, set[str]]:
    """country QID -> Wikimedia language codes of its official languages (cached)."""
    out: dict[str, set[str]] = {}
    for row in sparql(COUNTRY_LANGS, namespace="wdqs_country_lang"):
        out.setdefault(qid(row["c"]), set()).add(row["code"])
    return out


def select_leads(
    all_leads: pd.DataFrame,
    country_by_qid: dict[str, str],
    *,
    min_fraction: float = LOCAL_MIN_FRACTION,
) -> pd.DataFrame:
    """One row per museum: the local-language lead if long enough, else the longest.

    `all_leads` needs qid/lang/chars. Ties break on language code so re-runs are
    identical. Museums whose country has no official language on record, or which
    have no article in one, fall through to longest-wins.
    """
    langs = official_languages()
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
