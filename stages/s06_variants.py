"""Stage 06 — build the three text variants.

  (a) full     the lead as fetched
  (b) nofirst  lead with the first sentence removed (the sentence that almost
               always reads "X is a museum in <city>, <country>")
  (c) noloc    full lead with location entities stripped

Variant (c) uses two independent strippers because neither alone is enough:
  * a per-museum gazetteer built from Wikidata — every label and alias, in every
    language, of the museum's country and its whole P131 containment chain, plus
    demonyms (P1549) to catch "French", "italiana", "deutsche"
  * spaCy's multilingual NER (xx_ent_wiki_sm) LOC spans, to catch place names
    that are not in the museum's own containment chain

Caveat worth knowing when reading the report: the multilingual NER frequently
tags the museum's own name as LOC ("Louvre" -> LOC), so variant (c) is in
practice "geography *and* much of the institution's proper name removed". The
stage measures how often that happens (`label_hit`) so the effect is visible
rather than silent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import spacy
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from probe.common import INTERIM, qid, sparql, write_parquet  # noqa: E402
from probe.textproc import build_pattern, split_first_sentence, strip_locations  # noqa: E402
from probe.wiki import fetch_labels_aliases  # noqa: E402

MIN_CHARS = 20
CHUNK = 200

P131_CHAIN = """
SELECT ?m ?a WHERE {
  VALUES ?m { %s }
  ?m wdt:P131+ ?a .
}
"""

DEMONYMS = """
SELECT ?e ?d WHERE {
  VALUES ?e { %s }
  ?e wdt:P1549 ?d .
}
"""


def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def main() -> None:
    leads = pd.read_parquet(INTERIM / "leads.parquet")
    print(f"{len(leads):,} leads to process")

    # ---- containment chain -------------------------------------------------
    print("resolving P131 containment chains...")
    chain: dict[str, set[str]] = {q: set() for q in leads.qid}
    qids = sorted(leads.qid)
    for batch in tqdm(list(chunked(qids, CHUNK)), desc="  P131+"):
        rows = sparql(
            P131_CHAIN % " ".join(f"wd:{q}" for q in batch), namespace="wdqs_p131", timeout=180
        )
        for r in rows:
            chain[qid(r["m"])].add(qid(r["a"]))

    # Seed with what s01 already found, plus the country itself.
    for q, admins, cq in zip(leads.qid, leads.admins, leads.country_qid):
        if admins:
            chain[q].update(a for a in admins.split("|") if a)
        if cq and cq != "NONE":
            chain[q].add(cq)

    geo_qids = sorted({g for s in chain.values() for g in s})
    print(f"  {len(geo_qids):,} distinct geographic entities referenced")

    # ---- gazetteer ---------------------------------------------------------
    print("fetching labels/aliases (all languages)...")
    names = fetch_labels_aliases(geo_qids)

    print("fetching demonyms...")
    demonyms: dict[str, set[str]] = {}
    for batch in tqdm(list(chunked(geo_qids, CHUNK)), desc="  P1549"):
        rows = sparql(
            DEMONYMS % " ".join(f"wd:{g}" for g in batch), namespace="wdqs_demonym", timeout=180
        )
        for r in rows:
            demonyms.setdefault(qid(r["e"]), set()).add(r["d"])
    print(f"  demonyms for {len(demonyms):,} entities")

    # ---- NER ---------------------------------------------------------------
    print("running multilingual NER...")
    nlp = spacy.load("xx_ent_wiki_sm")
    nlp.max_length = 2_000_000
    texts = list(leads.text)
    ner_spans: list[list[tuple[int, int]]] = []
    for doc in tqdm(nlp.pipe(texts, batch_size=64), total=len(texts), desc="  LOC"):
        ner_spans.append([(e.start_char, e.end_char) for e in doc.ents if e.label_ == "LOC"])

    # ---- assemble ----------------------------------------------------------
    pat_cache: dict[tuple[str, ...], object] = {}
    out = []
    for i, row in enumerate(tqdm(leads.itertuples(index=False), total=len(leads), desc="  build")):
        full = row.text
        first, rest = split_first_sentence(full)

        key = tuple(sorted(chain[row.qid]))
        if key not in pat_cache:
            terms: set[str] = set()
            for g in key:
                terms |= names.get(g, set())
                terms |= demonyms.get(g, set())
            pat_cache[key] = build_pattern(terms)
        noloc = strip_locations(full, pat_cache[key], ner_spans[i])

        removed = len(full) - len(noloc)
        label_hit = bool(row.label) and row.label.lower() not in noloc.lower() \
            and row.label.lower() in full.lower()
        out.append(
            {
                "qid": row.qid,
                "text_full": full,
                "text_nofirst": rest,
                "text_noloc": noloc,
                "first_sentence": first,
                "n_geo_entities": len(key),
                "chars_removed_noloc": removed,
                "frac_removed_noloc": removed / max(1, len(full)),
                "label_hit": label_hit,
                "split_found": bool(rest),
            }
        )

    v = pd.DataFrame(out)
    v = leads.merge(v, on="qid", how="inner")
    for name, col in [("a", "text_full"), ("b", "text_nofirst"), ("c", "text_noloc")]:
        v[f"usable_{name}"] = v[col].str.len() >= MIN_CHARS
    v["usable_all"] = v.usable_a & v.usable_b & v.usable_c

    write_parquet(
        v, INTERIM / "variants.parquet",
        expect_cols=["qid", "text_full", "text_nofirst", "text_noloc", "usable_all"],
    )

    print(f"\nfirst-sentence split found: {v.split_found.mean():.1%}")
    print(f"location stripping removed {v.frac_removed_noloc.mean():.1%} of characters on average "
          f"(median {v.frac_removed_noloc.median():.1%})")
    print(f"museum's own name removed by the stripper: {v.label_hit.mean():.1%} of leads")
    print("\nusable rows per variant (>= %d chars):" % MIN_CHARS)
    for name in "abc":
        print(f"  variant {name}: {v[f'usable_{name}'].sum():,}")
    print(f"  all three : {v.usable_all.sum():,}  <- the common subset used for the headline table")


if __name__ == "__main__":
    main()
