"""Build 13 — render the interactive map.

Label layers are passed to datamapplot in Toponymy's own order (finest first,
coarsest last), which is exactly the order datamapplot wants. `Unlabelled` is
handed through as the noise label rather than filtered: those points are the
unnamed space between named regions at a given zoom, and they still carry their
coarser-layer name — dropping them would quietly delete a third of the corpus
from the map.

Selecting a point opens its Wikipedia article — a click on desktop, and on touch
an action button on the tap-to-inspect card, since a tap that navigated away
would leave no chance to read the card first. The article URL is rebuilt from the
language code rather than stored, because the sitematrix code *is* the subdomain
for every open Wikipedia, and not every corpus carries the `dbname` column.
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
from museum_map.nearby import NearbyControl  # noqa: E402
from museum_map.wiki import language_names  # noqa: E402

TITLE = "Museum Map"
# Only what the interface cannot teach on its own. The search box, the palette
# control and the card are all visible or one gesture away; that museums near
# each other are about similar things is the one thing a visitor has to be told,
# and it is what makes everything else on screen mean anything.
SUBTITLE = "{n:,} museums from Wikipedia, arranged so that similar ones sit close together."

# Point radius spans this ratio from the least to the most linked museum, on a
# log scale. Prominent museums are not spread evenly — the majors cluster — so a
# wide ratio would inflate the apparent density of whichever regions happen to
# hold famous institutions, which reads as "this region matters more" when it
# only means "this region has famous members". 3x is enough to find the Louvre
# inside the art museums at mid zoom without distorting the shape of the map.
SIZE_RATIO = 3.0

# Founding date is bucketed rather than ramped, for two reasons. Wikidata folds
# date precision into the same ISO string, so a century-precision value arrives
# looking exact; and for a heritage site P571 dates the *structure*, which is why
# the corpus contains Stonehenge at -1848 and Colchester Castle at 1069. A
# continuous scale would spend its whole range on a handful of ancient buildings
# and crush the 20th century, where the median museum actually sits.
#
# `not recorded` is a category with a colour, not a gap. 43.3% of the corpus has
# no date at all, and that absence is not evenly spread — 30.9% coverage on the
# recovered museums against 51.6% on the Wikidata-typed ones — so rendering it as
# one end of a ramp would draw missing metadata as if it were an early founding.
ERA_CUTS = ((1800, "before 1800"), (1900, "1800s"), (1950, "1900–1949"),
            (1980, "1950–1979"), (2000, "1980–1999"))
ERA_LAST = "2000 or later"
ERA_NONE = "not recorded"
ERA_COLORS = {
    "before 1800": "#440154", "1800s": "#414487", "1900–1949": "#2a788e",
    "1950–1979": "#22a884", "1980–1999": "#7ad151", "2000 or later": "#fde725",
    ERA_NONE: "#9e9e9e",
}

# p04 labels a museum with the least common of its P31 values, so `museum` means
# "typed, but only generically" and `other` means "no museum type in the top 25
# at all". Neither tells you what the museum is about, so both get grey rather
# than a colour of their own — the grey is where this view has nothing to say,
# and it covers most of the map.
TYPE_GENERIC = "museum (generic)"
TYPE_NONE = "no specific type"
NO_COUNTRY = "(no country)"  # what p01 writes when a museum has no P17

# datamapplot's categorical colormaps cap at twenty. Fifteen named values plus the
# neutral buckets stays under it and keeps the legend readable at a glance; past
# about fifteen the entries are too close in colour to tell apart on a point.
CAT_TOP_N = 15
CAT_OTHER = "other"

# Reserved for buckets that are an absence rather than a category. Keeping them
# grey means the eye reads them as "nothing recorded here" instead of ranking
# them alongside the named values.
NEUTRAL_GREYS = ("#adadad", "#d6d6d6", "#8a8a8a")

# What goes in the lat/lon point metadata for a museum with no P625. It has to be
# a real number: datamapplot ships that metadata as JSON built by `json.dumps`,
# which writes a bare `NaN` for a missing float, and the browser parses it with a
# strict `JSON.parse` inside a worker. That throws, and the failure mode is not a
# broken control — it is the whole map loading with no metadata, so no tooltips
# and no search either. 999 is outside the latitude range, so the nearby control
# can recognise it, and no arithmetic on it can produce a plausible distance.
NO_COORD = 999.0


def era_of(year) -> str:
    if pd.isna(year):
        return ERA_NONE
    for cut, name in ERA_CUTS:
        if year < cut:
            return name
    return ERA_LAST


def categorical_buckets(
    values: pd.Series, *, top_n: int = CAT_TOP_N, neutral: tuple[str, ...] = (),
    other: str = CAT_OTHER,
) -> tuple[list[str], dict[str, str]]:
    """Keep the `top_n` commonest values, fold the rest into one bucket.

    `neutral` names buckets that say "not recorded" rather than naming a value:
    they are always kept, are never ranked against the real values, and are
    coloured grey. `other` is neutral too — it is a statement about the legend's
    size, not about the museums in it.
    """
    from matplotlib import colormaps
    from matplotlib.colors import to_hex

    ranked = values[~values.isin(neutral)].value_counts()
    keep = list(ranked.index[:top_n])
    out = values.where(values.isin([*keep, *neutral]), other)

    # tab20 indices 14 and 15 are its own grey pair, dropped so that grey stays
    # unambiguously "no value" rather than also meaning some particular country.
    wheel = [to_hex(c) for i, c in enumerate(colormaps["tab20"].colors) if i not in (14, 15)]
    colors = {lab: NEUTRAL_GREYS[i % len(NEUTRAL_GREYS)]
              for i, lab in enumerate([*neutral, other])}
    colors.update({k: wheel[i % len(wheel)] for i, k in enumerate(keep)})
    assert len(set(out)) <= 20, f"{len(set(out))} categories exceeds datamapplot's cap"
    return out.tolist(), colors


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

    # The fixture's leads carry type_label already, because p05 samples a corpus
    # that has been through p04; the full corpora get it as a side file.
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

    # p09's Wikidata facts are optional in exactly the way p06's summaries are:
    # they enrich the card and the palette, and a corpus that has not been through
    # p09 should still render a correct map rather than fail.
    facts_path = out_dir / "facts.parquet"
    if facts_path.exists():
        n_before = len(leads)
        leads = leads.merge(
            pd.read_parquet(facts_path)[
                ["qid", "website", "founded_year", "heritage", "admin_label"]
            ],
            on="qid", how="left",
        )
        assert len(leads) == n_before, f"facts merge changed row count: {n_before} -> {len(leads)}"
        print(f"wikidata facts: founded year for {leads.founded_year.notna().mean():.1%}, "
              f"admin area for {(leads.admin_label.fillna('') != '').mean():.1%}")
    else:
        print(f"note: no facts ({facts_path} missing) — run pipeline/p09_facts.py")
        leads["founded_year"] = pd.array([pd.NA] * len(leads), dtype="Int64")
        for col in ("website", "heritage", "admin_label"):
            leads[col] = ""

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

    # The facts line is emitted with its own markup rather than as a bare field,
    # because the template is a plain format string: there is no way to drop an
    # empty row from it, and 10.5% of museums have nothing to put here. Building
    # the wrapper alongside the text lets those cards close up instead of showing
    # a blank gap. datamapplot substitutes raw, so this must be escaped here —
    # the same reason `snippet` already is.
    admin = leads.admin_label.fillna("").astype(str)
    heritage = leads.heritage.fillna("").astype(str)
    website = leads.website.fillna("").astype(str)
    facts_line = [
        " · ".join(
            p for p in (a, f"founded {y}" if pd.notna(y) else "", h) if p
        )
        for a, y, h in zip(admin, leads.founded_year, heritage)
    ]
    facts_html = [
        f"<div style='opacity:.7;font-size:.78em;margin-bottom:.35rem'>{html.escape(t)}</div>"
        if t else ""
        for t in facts_line
    ]
    n_facts = sum(1 for t in facts_line if t)
    print(f"cards carrying a facts line: {n_facts:,} ({n_facts / len(leads):.1%})")

    # The website is a domain, not a link: the card is a hover tooltip, so it
    # disappears the moment you move the pointer towards anything in it. As text
    # it still says "this is an operating institution with a web presence".
    domain = website.str.replace(r"^https?://(www\.)?", "", regex=True).str.split("/").str[0]
    footer = [
        f"{s} · {html.escape(d)}" if d else s for s, d in zip(source_note, domain)
    ]

    # The search corpus is an explicit column rather than `hover_text`: supplying
    # `hover_text_html_template` replaces hover_text with the rendered tooltip
    # markup, so `search_field="hover_text"` ends up searching HTML. Verified by
    # searching "Germany" against 34 German museums in the fixture and matching
    # essentially none of them.
    #
    # `admin` is the only one of these that can be empty (13.6% of museums), and
    # it is last, so the trailing separator is what `strip` removes.
    search_blob = (
        name + " · " + country + " · " + type_label + " · " + admin
    ).str.strip(" ·")

    # lat/lon are here for the nearby control and are never shown on the card.
    # They ride in the point metadata rather than in the control's own JS because
    # this payload is gzipped inside the HTML and a second copy would not be.
    has_coord = leads.lat.notna() & leads.lon.notna()
    extra = pd.DataFrame({
        "name": name,
        "country": country,
        "type": type_label,
        "lang": leads.lang.astype(str),
        "url": url,
        "snippet": snippet,
        "facts": facts_html,
        "source_note": footer,
        "region": label_layers[0],
        "search": search_blob,
        "lat": leads.lat.where(has_coord, NO_COORD).astype(float),
        "lon": leads.lon.where(has_coord, NO_COORD).astype(float),
    })
    # See NO_COORD: a null in here reaches the browser as a bare `NaN` and takes
    # the map's whole metadata payload down with it, quietly and at load time.
    # Cheaper to fail the build than to debug that from a blank tooltip.
    nan_cols = [c for c in extra.columns if extra[c].isna().any()]
    assert not nan_cols, f"nulls in point metadata would break JSON.parse: {nan_cols}"
    print(f"coordinates: {has_coord.mean():.1%} of museums carry one")

    hover_template = (
        "<div style='max-width:22rem'>"
        "<div style='font-weight:600;margin-bottom:.2rem'>{name}</div>"
        "<div style='opacity:.75;font-size:.85em;margin-bottom:.4rem'>"
        "{country} · {type} · {lang}.wikipedia</div>"
        "{facts}"
        "<div style='font-size:.85em;line-height:1.35'>{snippet}</div>"
        "<div style='opacity:.55;font-size:.72em;margin-top:.45rem'>{source_note}</div>"
        "</div>"
    )

    # ---- point size: how many wikis and sister projects link this museum ----
    #
    # datamapplot renormalises this array by its own mean before handing it to
    # deck.gl's getRadius, so only the ratios matter, not the units. log1p first:
    # sitelink_count runs 1 to 167 with a median of 2, and raw values would put a
    # 46x radius on the Louvre.
    #
    # This is the one field in the corpus with no coverage skew — mean 3.59 on the
    # Wikidata-typed museums against 3.50 on the recovered ones, zero nulls in
    # either — which is why prominence gets the permanent channel and every
    # sparser field is left to the palette control, where choosing it is opt-in.
    linked = np.log1p(leads.sitelink_count.to_numpy(dtype=float))
    span = max(linked.max() - linked.min(), 1e-9)
    marker_size = 1.0 + (SIZE_RATIO - 1.0) * (linked - linked.min()) / span

    # ---- what the palette control can recolour by ----
    #
    # datamapplot always offers "Clusters" first and these ride alongside it, so
    # the map still opens coloured by region. Everything here is either complete
    # by construction (country, language, sitelinks, declared type) or carries its
    # own explicit "not recorded" category. Nothing sparse gets a continuous ramp:
    # coverage of the Wikidata fields tracks how thorough a country's editors have
    # been, so a ramp over one would draw editor attention and read as geography.
    era = [era_of(y) for y in leads.founded_year]
    type_bucket, type_colors = categorical_buckets(
        leads.type_label.fillna("").astype(str).replace(
            {"museum": TYPE_GENERIC, "other": TYPE_NONE}),
        top_n=12, neutral=(TYPE_GENERIC, TYPE_NONE), other="other type",
    )
    # Country and language answer the two questions people ask of a point once
    # they have found it: where is this, and who wrote about it. They also make the
    # shape of the space legible — country is confetti at a glance and clumped up
    # close, which is what "geography is a gradient, not a partition" looks like.
    # The two colour similarly, because `select_leads` picks a museum's lead from
    # its country's languages; language earns its slot on the wikis that span many
    # countries.
    country_bucket, country_colors = categorical_buckets(
        leads.country_label.fillna(NO_COUNTRY).astype(str), neutral=(NO_COUNTRY,))
    lang_names = language_names()
    lang_bucket, lang_colors = categorical_buckets(
        leads.lang.astype(str).map(lambda c: lang_names.get(c, c)))

    # Positional: entry i of rawdata is described by entry i of metadata.
    colormap_rawdata = [np.array(country_bucket), np.array(lang_bucket),
                        np.array(era), np.array(type_bucket), linked]
    colormap_metadata = [
        {"field": "country", "description": "Country", "kind": "categorical",
         "color_mapping": country_colors},
        {"field": "language", "description": "Article language", "kind": "categorical",
         "color_mapping": lang_colors},
        {"field": "era", "description": "Founded", "kind": "categorical",
         "color_mapping": ERA_COLORS},
        {"field": "wdtype", "description": "Wikidata type", "kind": "categorical",
         "color_mapping": type_colors},
        {"field": "sitelinks", "description": "Prominence (sitelinks, log)",
         "kind": "continuous", "cmap": "viridis"},
    ]
    print(f"\npalette options: {', '.join(m['description'] for m in colormap_metadata)}")
    for name_, series in (("founded", era), ("country", country_bucket),
                          ("language", lang_bucket)):
        vc = pd.Series(series).value_counts()
        top = ", ".join(f"{k} {v / len(leads) * 100:.0f}%" for k, v in vc.head(4).items())
        print(f"  {name_:<9} {len(vc):>2} buckets — {top}")

    # ---- the nearby control ----
    #
    # Optional in the same way p09's facts are: a corpus that has not been
    # through p09 still renders, without the control rather than not at all.
    # It is injected through the `custom_*` parameters rather than as a widget;
    # museum_map/nearby.py says why, and the reason is not a preference.
    places_path = out_dir / "places.parquet"
    custom = {"custom_html": None, "custom_css": None, "custom_js": None}
    if places_path.exists():
        places = pd.read_parquet(places_path)
        # A gazetteer written before regions existed would otherwise fail deep
        # inside the payload builder, on an attribute rather than on the file.
        stale = {"qid", "name", "region", "lat", "lon", "country"} - set(places.columns)
        if stale:
            raise SystemExit(f"{places_path} is missing {sorted(stale)} — "
                             "rerun pipeline/p09_facts.py for this corpus")
        control = NearbyControl(
            places, no_coord=NO_COORD, missing_share=float(1 - has_coord.mean()),
        )
        custom = {"custom_html": control.html, "custom_css": control.css,
                  "custom_js": control.javascript}
        print(f"nearby control: {len(places):,} settlements, "
              f"{', '.join(places.name.head(3))}, …")
    else:
        print(f"note: no places ({places_path} missing) — run pipeline/p09_facts.py")

    out = Path(args.out) if args.out else ROOT / "reports" / f"map_{args.corpus}{tag}.html"
    out.parent.mkdir(parents=True, exist_ok=True)

    plot = datamapplot.create_interactive_plot(
        np.ascontiguousarray(coords[["x", "y"]].to_numpy(), dtype=np.float32),
        *label_layers,
        hover_text=search_blob.tolist(),
        extra_point_data=extra,
        hover_text_html_template=hover_template,
        marker_size_array=marker_size,
        colormap_rawdata=colormap_rawdata,
        colormap_metadata=colormap_metadata,
        on_click="window.open(`{url}`)",
        # TODO once datamapplot's tap-to-inspect lands on PyPI (merged in 934c541,
        # unreleased as of 0.7.3): pass `on_click_label`. On touch the tap opens a
        # card rather than firing on_click, and the card's action button carries
        # that label — unset, a mobile visitor gets datamapplot's default wording
        # where this map wants something like "Open Wikipedia article".
        enable_search=True,
        search_field="search",
        noise_label="Unlabelled",
        darkmode=args.darkmode,
        cvd_safer=True,
        title=TITLE,
        sub_title=SUBTITLE.format(n=len(leads)),
        inline_data=True,
        **custom,
    )
    plot.save(out)
    print(f"\nwrote {out.relative_to(ROOT)}  ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
