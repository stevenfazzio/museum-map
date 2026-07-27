"""Build 13 — render the interactive map.

Label layers are passed to datamapplot in Toponymy's own order (finest first,
coarsest last), which is exactly the order datamapplot wants. `Unlabelled` is
handed through as the noise label rather than filtered: those points are the
unnamed space between named regions at a given zoom, and they still carry their
coarser-layer name — dropping them would quietly delete a third of the corpus
from the map.

Clicking a point opens its Wikipedia article. The article URL is rebuilt from the
language code rather than stored, because the sitematrix code *is* the subdomain
for every open Wikipedia, and the probe's fixture leads predate the `dbname`
column that the full-corpus fetch writes.
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common import ROOT, corpus_paths  # noqa: E402

TITLE = "The Museum Map"
SUBTITLE = (
    "{n:,} museums, placed by what the lead section of their Wikipedia article says "
    "about them. Regions are named by Toponymy; colour carries region identity only. "
    "Click a point to open its article."
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="fixture")
    ap.add_argument("--tag", default="haiku")
    ap.add_argument("--darkmode", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    import datamapplot

    leads_path, out_dir = corpus_paths(args.corpus)
    leads = pd.read_parquet(leads_path).sort_values("qid").reset_index(drop=True)
    coords = pd.read_parquet(out_dir / "coords.parquet")
    tag = f"_{args.tag}" if args.tag else ""
    topics = pd.read_parquet(out_dir / f"topics{tag}.parquet")

    assert (coords.qid.to_numpy() == leads.qid.to_numpy()).all(), "coords/leads order drift"
    assert (topics.qid.to_numpy() == leads.qid.to_numpy()).all(), "topics/leads order drift"

    layer_cols = sorted(
        [c for c in topics.columns if c.endswith("_name")],
        key=lambda c: int(c.removeprefix("layer").removesuffix("_name")),
    )
    label_layers = [topics[c].to_numpy().astype(str) for c in layer_cols]
    print(f"corpus={args.corpus}  n={len(leads):,}  layers={len(label_layers)} (fine -> coarse)")
    for c, layer in zip(layer_cols, label_layers):
        named = layer[layer != "Unlabelled"]
        print(f"  {c}: {len(np.unique(named))} regions, "
              f"{(layer == 'Unlabelled').mean():.1%} Unlabelled")

    # The fixture's leads carry type_label already (the probe's s04 wrote it into
    # the sample); the full corpus gets it from b03 as a side file.
    if "type_label" not in leads.columns:
        types_path = leads_path.parent / "types.parquet"
        if types_path.exists():
            n_before = len(leads)
            leads = leads.merge(pd.read_parquet(types_path)[["qid", "type_label"]],
                                on="qid", how="left")
            # A duplicated qid on the right would silently fan rows out and
            # desynchronise every point from its coordinates.
            assert len(leads) == n_before, f"type merge changed row count: {n_before} -> {len(leads)}"
        else:
            print(f"note: no type labels ({types_path} missing) — run b03_types.py")
            leads["type_label"] = ""

    # 15.1% of museums have no English label on Wikidata, and the harvest stores
    # the QID in the label column for those rather than leaving it null — so a
    # `fillna` fallback silently never fires and the tooltip reads "Q24254667".
    # The Wikipedia article title is always present and is a better name anyway:
    # it is what the museum is actually called, in its own language.
    has_label = (
        leads.has_label.fillna(False) if "has_label" in leads.columns
        else leads.label != leads.qid
    )
    name = leads.label.where(has_label, leads.title).fillna(leads.qid).astype(str)
    n_from_title = int((~has_label).sum())
    if n_from_title:
        print(f"names taken from the article title (no English Wikidata label): "
              f"{n_from_title:,} ({n_from_title / len(leads):.1%})")
    country = leads.country_label.fillna("").astype(str)
    type_label = leads.type_label.fillna("").astype(str)
    url = (
        "https://" + leads.lang.astype(str) + ".wikipedia.org/wiki/"
        + leads.title.astype(str).str.replace(" ", "_", regex=False)
    )
    # 80.9% of leads are not in English, because the corpus prefers the
    # local-language article. Right for placing a museum, unreadable for most
    # people looking at one — so the tooltip shows p06's English summary where it
    # exists and falls back to the lead itself where it does not.
    #
    # Summaries are a reading aid, NOT what the map is built from. An audit of 150
    # (weighted toward thin leads) found 8% assert something their source does not
    # — usually drift rather than invention, e.g. "named after the anatomist" ->
    # "made by him". That is a fine trade for a tooltip with the article one click
    # away, and not a fine trade for the embedding, so the summaries are shown and
    # the originals are embedded. The tooltip says which is which.
    summ_path = out_dir / "summaries.parquet"
    summary = pd.Series([""] * len(leads), index=leads.index)
    if summ_path.exists():
        n_before = len(leads)
        leads = leads.merge(pd.read_parquet(summ_path), on="qid", how="left")
        assert len(leads) == n_before, "summary merge changed row count"
        summary = leads.summary.fillna("")
        print(f"english summaries: {(summary != '').mean():.1%} of museums")
    else:
        print(f"note: no summaries ({summ_path} missing) — run pipeline/p06_summaries.py")

    lead_snippet = leads.text.fillna("").astype(str).str.slice(0, 240)
    is_summary = summary != ""
    snippet = summary.where(is_summary, lead_snippet).astype(str).map(html.escape)
    source_note = np.where(is_summary, "AI summary", "lead section")

    # The search corpus is an explicit column rather than `hover_text`: supplying
    # `hover_text_html_template` replaces hover_text with the rendered tooltip
    # markup, so `search_field="hover_text"` ends up searching HTML. Verified by
    # searching "Germany" against 34 German museums in the fixture and matching
    # essentially none of them.
    search_blob = (name + " · " + country + " · " + type_label).str.strip(" ·")

    extra = pd.DataFrame({
        "name": name,
        "country": country,
        "type": type_label,
        "lang": leads.lang.astype(str),
        "url": url,
        "snippet": snippet,
        "source_note": source_note,
        "region": label_layers[0],
        "search": search_blob,
    })

    hover_template = (
        "<div style='max-width:22rem'>"
        "<div style='font-weight:600;margin-bottom:.2rem'>{name}</div>"
        "<div style='opacity:.75;font-size:.85em;margin-bottom:.4rem'>"
        "{country} · {type} · {lang}.wikipedia</div>"
        "<div style='font-size:.85em;line-height:1.35'>{snippet}</div>"
        "<div style='opacity:.55;font-size:.72em;margin-top:.45rem'>{source_note}</div>"
        "</div>"
    )

    out = Path(args.out) if args.out else ROOT / "reports" / f"map_{args.corpus}{tag}.html"
    out.parent.mkdir(parents=True, exist_ok=True)

    plot = datamapplot.create_interactive_plot(
        np.ascontiguousarray(coords[["x", "y"]].to_numpy(), dtype=np.float32),
        *label_layers,
        hover_text=search_blob.tolist(),
        extra_point_data=extra,
        hover_text_html_template=hover_template,
        on_click="window.open(`{url}`)",
        enable_search=True,
        search_field="search",
        enable_topic_tree=True,
        noise_label="Unlabelled",
        darkmode=args.darkmode,
        cvd_safer=True,
        # Black label text rather than per-cluster colour. The CVD-safer palette
        # runs light enough that a pale label on a pale background is a coin flip,
        # and point colour already carries region identity, so tying the label to
        # it buys little. (Note: labels that overlap a neighbour are *also* faded
        # by deck.gl's collision filter, which looks identical to a contrast
        # problem in a static screenshot and is not fixed by this.)
        color_label_text=False,
        title=TITLE,
        sub_title=SUBTITLE.format(n=len(leads)),
        font_family="Inter",
        label_wrap_width=20,
        initial_zoom_fraction=0.995,
        inline_data=True,
    )
    plot.save(out)
    print(f"\nwrote {out.relative_to(ROOT)}  ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
