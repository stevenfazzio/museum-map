"""Stage 09 — figures and the markdown report.

On the figures: a 2,000-point scatter carrying ~150 countries cannot be coloured
by country directly. Only four hues of the reference categorical palette clear
the all-pairs CVD/normal-vision floors that scatter requires (verified with the
palette validator: blue/orange/aqua/violet pass, any fifth fails), so the primary
figure for each variant is a small-multiple grid — every point drawn in grey,
one category highlighted per panel. Colour carries no identity there (panel
position and title do), so the palette question disappears and overplotting stops
hiding the answer. The literal single-panel version is emitted alongside it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from probe.common import FIGS, PROCESSED, REPORTS  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GREY = "#d5d4d0"
ACCENT = "#2a78d6"
# Fixed order, never cycled. Documented caveat: this exceeds the all-pairs gate
# for scatter, which is exactly why the facet grid is the primary figure.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7", "#eda100", "#e87ba4", "#008300", "#e34948"]

VARIANT_TITLE = {
    "a_full": "(a) full lead",
    "b_nofirst": "(b) first sentence removed",
    "c_noloc": "(c) locations stripped",
}
TOP_N = 8


def _bare(ax):
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#e6e5e1")
    ax.set_facecolor(SURFACE)


def facet_figure(df: pd.DataFrame, col: str, title: str, out: Path) -> None:
    top = list(df[col].value_counts().head(TOP_N).index)
    n = len(top) + 1
    ncol = 3
    nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(ncol * 3.0, nrow * 3.0), facecolor=SURFACE)
    axes = np.atleast_1d(axes).ravel()

    groups = top + ["(all other)"]
    for ax, g in zip(axes, groups):
        sel = ~df[col].isin(top) if g == "(all other)" else (df[col] == g)
        ax.scatter(df.x, df.y, s=3, c=GREY, linewidths=0, rasterized=True)
        ax.scatter(df.x[sel], df.y[sel], s=6, c=ACCENT, linewidths=0, rasterized=True)
        ax.set_title(f"{g}  (n={int(sel.sum())})", fontsize=8, color=INK, pad=4)
        _bare(ax)
    for ax in axes[len(groups):]:
        ax.axis("off")

    fig.suptitle(title, fontsize=11, color=INK, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def scatter_figure(df: pd.DataFrame, col: str, title: str, out: Path) -> None:
    top = list(df[col].value_counts().head(TOP_N).index)
    fig, ax = plt.subplots(figsize=(7.2, 5.6), facecolor=SURFACE)
    other = ~df[col].isin(top)
    ax.scatter(df.x[other], df.y[other], s=4, c=GREY, linewidths=0,
               label=f"other ({int(other.sum())})", rasterized=True)
    for i, g in enumerate(top):
        sel = df[col] == g
        ax.scatter(df.x[sel], df.y[sel], s=9, c=SERIES[i], linewidths=0,
                   label=f"{g} ({int(sel.sum())})", rasterized=True)
    _bare(ax)
    ax.set_title(title, fontsize=11, color=INK)
    ax.legend(fontsize=7, loc="center left", bbox_to_anchor=(1.01, 0.5),
              frameon=False, labelcolor=INK2, markerscale=1.6)
    fig.tight_layout()
    fig.savefig(out, dpi=130, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def length_figure(chars: pd.Series, cutoff: float, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.2), facecolor=SURFACE)
    ax.hist(chars, bins=60, color=ACCENT, linewidth=0)
    ax.axvline(cutoff, color="#eb6834", linewidth=2)
    ax.text(cutoff, ax.get_ylim()[1] * 0.92, f"  25th pct = {cutoff:.0f}",
            color="#eb6834", fontsize=8, va="top")
    ax.set_xlabel("lead length (characters)", fontsize=9, color=INK2)
    ax.set_ylabel("museums", fontsize=9, color=INK2)
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#e6e5e1")
    ax.tick_params(colors=INK2, labelsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def dissolve_figure(df: pd.DataFrame, out: Path, n_langs: int = 4) -> None:
    """Rows = representation, columns = language. Watch the blobs dissolve."""
    spaces = ["raw", "centered", "inlp"]
    titles = {"raw": "raw", "centered": "per-language centered", "inlp": "INLP-projected"}
    top = list(df[df.space == "raw"].lang.value_counts().head(n_langs).index)
    fig, axes = plt.subplots(
        len(spaces), n_langs, figsize=(n_langs * 2.6, len(spaces) * 2.7), facecolor=SURFACE
    )
    for r, sp in enumerate(spaces):
        d = df[df.space == sp]
        for c, lg in enumerate(top):
            ax = axes[r, c]
            sel = (d.lang == lg).to_numpy()
            # Equal marker size, translucent highlight: an oversized opaque
            # highlight saturates the tight INLP cloud and fakes "fully mixed".
            ax.scatter(d.x, d.y, s=3, c=GREY, linewidths=0, rasterized=True)
            ax.scatter(d.x[sel], d.y[sel], s=3, c=ACCENT, linewidths=0,
                       alpha=0.7, rasterized=True)
            _bare(ax)
            if r == 0:
                ax.set_title(f"{lg}  (n={int(sel.sum())})", fontsize=9, color=INK, pad=4)
            if c == 0:
                ax.set_ylabel(titles[sp], fontsize=9, color=INK2)
    fig.suptitle(
        "Same 6,885 articles, three representations — each panel highlights one language",
        fontsize=10, color=INK, y=0.998,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.975))
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def _midpoints(edges: list[float]) -> np.ndarray:
    e = np.asarray(edges, dtype=float)
    mid = np.sqrt(np.maximum(e[:-1], 0.5) * e[1:])  # geometric, log axis
    mid[0] = 0.5
    return mid


def decay_figure(G: dict, out: Path, min_pairs: int = 50) -> None:
    """Similarity above each space's own global mean, against great-circle distance."""
    mid = _midpoints(G["bin_edges_km"])
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.0), facecolor=SURFACE)

    def series(ax, block, colour, label, band=True, ref=None):
        y = np.array([np.nan if s is None else s for s in block["mean_similarity"]])
        n = np.array(block["n_pairs"])
        # Two series drawn on one axis must share a reference. Each *space* gets
        # its own global mean (different similarity scales), but the same-country
        # subset must be referenced to its space's all-pairs mean, or it looks
        # like it dips below zero when it is in fact the higher curve.
        gm = block["global_mean"] if ref is None else ref
        ok = n >= min_pairs
        ax.plot(mid[ok], (y - gm)[ok], color=colour, linewidth=2, label=label, zorder=3)
        ax.scatter(mid[ok], (y - gm)[ok], s=18, color=colour, zorder=4)
        if band and block.get("null_lo"):
            lo = np.array([np.nan if s is None else s for s in block["null_lo"]]) - gm
            hi = np.array([np.nan if s is None else s for s in block["null_hi"]]) - gm
            ax.fill_between(mid[ok], lo[ok], hi[ok], color=GREY, alpha=0.7, linewidth=0, zorder=1)

    ax = axes[0]
    series(ax, G["spaces"]["raw"]["all_pairs"], SERIES[0], "raw")
    series(ax, G["spaces"]["centered"]["all_pairs"], SERIES[1], "language-centered")
    ax.set_title("All pairs — near museums are more alike", fontsize=10, color=INK)

    ax = axes[1]
    cen = G["spaces"]["centered"]
    ref = cen["all_pairs"]["global_mean"]
    series(ax, cen["all_pairs"], SERIES[1], "all pairs", ref=ref)
    series(ax, cen["same_country"], SERIES[3], "same country only", band=False, ref=ref)
    ax.set_title("Centered space — distance vs. national membership", fontsize=10, color=INK)

    for ax in axes:
        ax.set_xscale("log")
        ax.axhline(0, color="#c9c8c3", linewidth=1, zorder=0)
        ax.set_xlabel("great-circle distance (km)", fontsize=9, color=INK2)
        ax.set_facecolor(SURFACE)
        ax.tick_params(colors=INK2, labelsize=8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color("#e6e5e1")
        ax.legend(fontsize=8, frameon=False, labelcolor=INK2)
    axes[0].set_ylabel("mean cosine similarity\nabove that space's global mean",
                       fontsize=9, color=INK2)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.text(0.5, 0.015, "Grey band = permutation null (coordinates shuffled)",
             ha="center", fontsize=8.5, color=INK2)
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def radius_figure(by_type: dict, out: Path) -> None:
    """Median distance to a museum's 10 nearest embedding neighbours, by type."""
    items = sorted(by_type.items(), key=lambda kv: kv[1]["median_km"])
    names = [f"{k}  (n={v['n']})" for k, v in items]
    vals = [v["median_km"] for _, v in items]
    fig, ax = plt.subplots(figsize=(7.6, 0.34 * len(items) + 1.4), facecolor=SURFACE)
    ax.barh(range(len(items)), vals, color=ACCENT, height=0.62, linewidth=0)
    ax.set_yticks(range(len(items)))
    ax.set_yticklabels(names, fontsize=8.5, color=INK)
    ax.invert_yaxis()
    for i, val in enumerate(vals):
        ax.text(val + 60, i, f"{val:,.0f}", va="center", fontsize=8, color=INK2)
    ax.set_xlabel("median km to 10 nearest embedding neighbours  "
                  "(← locally rooted · internationally legible →)",
                  fontsize=9, color=INK2)
    ax.set_facecolor(SURFACE)
    ax.tick_params(colors=INK2, labelsize=8)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#e6e5e1")
    fig.tight_layout()
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def fmt(x, spec="+.3f"):
    return "n/a" if x is None else format(x, spec)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="intfloat/multilingual-e5-large")
    args = ap.parse_args()
    tag = args.model.split("/")[-1]

    M = json.loads((PROCESSED / f"metrics_{tag}.json").read_text())
    V = list(M["variants"])

    coords = {v: pd.read_parquet(PROCESSED / f"coords_{tag}_{v}.parquet") for v in V}

    print("rendering figures...")
    for v in V:
        df = coords[v]
        facet_figure(df, "lang", f"{VARIANT_TITLE[v]} — by article language",
                     FIGS / f"{v}_language_facets.png")
        scatter_figure(df, "lang", f"{VARIANT_TITLE[v]} — by article language",
                       FIGS / f"{v}_language_scatter.png")
        facet_figure(df, "country_label", f"{VARIANT_TITLE[v]} — by country",
                     FIGS / f"{v}_country_facets.png")
        facet_figure(df, "type_label", f"{VARIANT_TITLE[v]} — by type",
                     FIGS / f"{v}_type_facets.png")
        scatter_figure(df, "country_label", f"{VARIANT_TITLE[v]} — by country",
                       FIGS / f"{v}_country_scatter.png")
        scatter_figure(df, "type_label", f"{VARIANT_TITLE[v]} — by type",
                       FIGS / f"{v}_type_scatter.png")
    length_figure(coords[V[0]].chars, M["shortest_quartile_char_cutoff"],
                  FIGS / "lead_lengths.png")

    CEN = None
    cmpath = PROCESSED / f"metrics_{tag}_centered.json"
    if cmpath.exists():
        CEN = json.loads(cmpath.read_text())
        cc = PROCESSED / f"coords_{tag}_centered_a_full.parquet"
        if cc.exists():
            cdf = pd.read_parquet(cc)
            for col, nice, fn in [("lang", "article language", "language"),
                                  ("type_label", "type", "type"),
                                  ("country_label", "country", "country")]:
                facet_figure(cdf, col,
                             f"(a) full lead, per-language centered — by {nice}",
                             FIGS / f"centered_{fn}_facets.png")

    G = None
    gpath = PROCESSED / f"geo_{tag}.json"
    if gpath.exists():
        G = json.loads(gpath.read_text())
        decay_figure(G, FIGS / "distance_decay.png")
        radius_figure(G["radius_by_type"], FIGS / "radius_by_type.png")

    P = None
    ppath = PROCESSED / f"parallel_{tag}.json"
    if ppath.exists():
        P = json.loads(ppath.read_text())
        cpath = PROCESSED / f"parallel_coords_{tag}.parquet"
        if cpath.exists():
            dissolve_figure(pd.read_parquet(cpath), FIGS / "language_dissolve.png")

    # ---------------------------------------------------------------- report
    L = M["length_distribution"]
    S = M["stripping"]

    def table(subset: str, key: str) -> str:
        head = (
            "| variant | n | clusters | noise | ARI | AMI | silhouette (cosine) | "
            "silhouette (2D) | 10-NN purity | chance | linear probe | baseline |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        )
        rows = []
        for v in V:
            r = M["variants"][v][subset]
            k = r[key]
            rows.append(
                f"| {VARIANT_TITLE[v]} | {r['n']} | {r['n_clusters']} | "
                f"{r['noise_fraction']:.0%} | {fmt(k['ari_all'])} | {fmt(k['ami_all'])} | "
                f"{fmt(k['silhouette']['cosine'])} | {fmt(k['silhouette']['umap2d'])} | "
                f"{k['knn_purity']:.3f} | {k['knn_chance']:.3f} | "
                f"{fmt(k['probe']['accuracy'], '.3f')} | {fmt(k['probe']['baseline'], '.3f')} |"
            )
        return head + "\n".join(rows)

    def specific_table(subset: str) -> str:
        head = (
            "| variant | n | types | ARI | AMI | silhouette (cosine) | 10-NN purity | "
            "chance | linear probe | baseline |\n|---|---|---|---|---|---|---|---|---|---|\n"
        )
        rows = []
        for v in V:
            k = M["variants"][v][subset].get("type_specific")
            if not k:
                continue
            rows.append(
                f"| {VARIANT_TITLE[v]} | {k['n']} | {k['n_types']} | {fmt(k['ari_all'])} | "
                f"{fmt(k['ami_all'])} | {fmt(k['silhouette']['cosine'])} | "
                f"{k['knn_purity']:.3f} | {k['knn_chance']:.3f} | "
                f"{fmt(k['probe']['accuracy'], '.3f')} | {fmt(k['probe']['baseline'], '.3f')} |"
            )
        return head + "\n".join(rows)

    def all_tables(subset: str) -> str:
        r0 = M["variants"][V[0]][subset]
        return (
            f"**vs language of the lead** ({r0.get('n_languages', '?')} languages)\n\n"
            + table(subset, "language")
            + f"\n\n**vs country** ({r0['n_countries']} countries)\n\n"
            + table(subset, "country")
            + f"\n\n**vs type** ({r0['n_types']} types, incl. the generic bucket)\n\n"
            + table(subset, "type")
            + "\n\n**vs type, specifically-typed museums only** (generic `museum` and `other` "
            "dropped — with 62% of the sample in one bucket the table above is a "
            "majority-class artefact)\n\n"
            + specific_table(subset)
        )

    single_sent = 1 - M["variants"]["b_nofirst"]["own"]["n"] / M["variants"]["a_full"]["own"]["n"]
    langs = M["language_distribution"]
    lang_str = ", ".join(f"`{k}` {v}" for k, v in list(langs.items())[:12])

    # ---- computed verdict --------------------------------------------------
    A = M["variants"]["a_full"]["own"]
    B = M["variants"]["b_nofirst"]["own"]
    C = M["variants"]["c_noloc"]["own"]
    ac, cc = A["country"], C["country"]
    al, cl, bl = A["language"], C["language"], B["language"]
    ats = A.get("type_specific")

    def lift(k):
        return k["knn_purity"] / k["knn_chance"] if k["knn_chance"] else float("nan")

    drop = (ac["knn_purity"] - cc["knn_purity"]) / ac["knn_purity"] if ac["knn_purity"] else 0.0
    lang_drop = (al["knn_purity"] - cl["knn_purity"]) / al["knn_purity"] if al["knn_purity"] else 0

    # Which label best explains the clustering? Compare ARI head-to-head.
    ranked = sorted(
        [("the language the article is written in", al["ari_all"]),
         ("country", ac["ari_all"]),
         ("museum type", A["type"]["ari_all"])],
        key=lambda kv: -kv[1],
    )
    winner, w_ari = ranked[0]
    runner, r_ari = ranked[1]

    if w_ari > 0.4 and w_ari > 3 * max(r_ari, 0.01):
        headline = (
            f"**The dominant axis is not country or type — it is {winner}.** "
            f"HDBSCAN's clusters line up with it at ARI **{w_ari:+.3f}**, against "
            f"**{r_ari:+.3f}** for {runner}. The map you would build from these "
            "embeddings today is, first and foremost, a map of Wikipedia language "
            "editions."
        )
    elif w_ari > 0.25:
        headline = (f"**{winner.capitalize()} is the strongest single explanation** of the cluster "
                    f"structure (ARI {w_ari:+.3f}), ahead of {runner} ({r_ari:+.3f}).")
    else:
        headline = ("**No single metadata field explains the cluster structure.** The best of "
                    f"them, {winner}, reaches only ARI {w_ari:+.3f}.")

    if drop > 0.5:
        strip_read = (f"Stripping locations removes **{drop:.0%}** of the country signal, so most "
                      "of it rides on explicit place names — addressable by preprocessing.")
    elif drop > 0.15:
        strip_read = (f"Stripping locations removes **{drop:.0%}** of the country signal, but only "
                      f"**{lang_drop:.0%}** of the language signal. Place names carry a real share "
                      "of the geography; they carry almost none of the language effect, which is "
                      "why (c) barely moves the map.")
    else:
        strip_read = (f"Stripping locations barely moves country purity (**{drop:.0%}**): the "
                      "signal is not carried by place names but by language and writing "
                      "conventions, which this preprocessing does not touch.")

    type_read = (
        f"Museum type is close to absent: ARI **{A['type']['ari_all']:+.3f}**, and even among the "
        f"{ats['n']} specifically-typed museums the linear probe reaches "
        f"**{ats['probe']['accuracy']:.1%}** against a **{ats['probe']['baseline']:.1%}** "
        f"baseline. Neighbourhoods are mildly type-ish ({ats['knn_purity']:.1%} vs "
        f"{ats['knn_chance']:.1%} chance) but type is nowhere near an organising axis."
        if ats else "Museum type could not be assessed: too few specifically-typed museums."
    )

    verdict = f"""## Verdict

Headline numbers, full lead (variant a), {A["n"]} museums.

| label | do clusters equal it? (ARI) | do 10 neighbours share it? | chance | lift | linear probe | baseline |
|---|---|---|---|---|---|---|
| **language of the lead** | **{al["ari_all"]:+.3f}** | **{al["knn_purity"]:.1%}** | {al["knn_chance"]:.1%} | **{lift(al):.0f}x** | {al["probe"]["accuracy"]:.1%} | {al["probe"]["baseline"]:.1%} |
| country | {ac["ari_all"]:+.3f} | {ac["knn_purity"]:.1%} | {ac["knn_chance"]:.1%} | {lift(ac):.0f}x | {ac["probe"]["accuracy"]:.1%} | {ac["probe"]["baseline"]:.1%} |
| type (all) | {A["type"]["ari_all"]:+.3f} | {A["type"]["knn_purity"]:.1%} | {A["type"]["knn_chance"]:.1%} | {lift(A["type"]):.1f}x | {A["type"]["probe"]["accuracy"]:.1%} | {A["type"]["probe"]["baseline"]:.1%} |

Read the **ARI** and **purity** columns, not the lift column, when comparing rows
against each other. Lift is purity ÷ chance, and chance depends on how many
categories the label has ({A["n_countries"]} countries vs
{A.get("n_languages", "?")} languages), so country's larger lift only says
country is far from *its own* much lower chance floor — it does not make country
the stronger axis.

{headline}

**Country is real but secondary, and partly a language proxy.** Neighbour purity
is {ac["knn_purity"]:.1%} against {ac["knn_chance"]:.1%} chance ({lift(ac):.0f}x), yet
silhouette is ~0 ({ac["silhouette"]["cosine"]:+.3f}) and ARI only {ac["ari_all"]:+.3f}:
country information is present and distributed, not the shape of the space. Because the
lead is taken from whichever Wikipedia had the longest article, and language tracks
country closely, an unknown part of that {lift(ac):.0f}x is language wearing a country
label.

{strip_read}

**The opening sentence carries a large share of both effects.** Removing just the
first sentence (variant b) drops language ARI from {al["ari_all"]:+.3f} to
{bl["ari_all"]:+.3f} and country neighbour purity from {ac["knn_purity"]:.1%} to
{B["country"]["knn_purity"]:.1%}. Wikipedia's opening line is highly formulaic and
its template differs per language edition, so it encodes both "what language is
this" and "where is this" more strongly than the rest of the lead.

{type_read}

### What this implies for the map

The good news for the project is that the trivial outcome did *not* happen: the
embedding is not a restatement of country, and it is certainly not a restatement
of museum type. The bad news is the confound that replaced it — the map is
currently organised by which Wikipedia the text came from, which is an artefact
of the sampling rule ("longest article across languages"), not a property of
museums.

It is also fixable, and the two sections below measure the fix rather than
speculating about it. **Per-language centring removes the language axis
essentially completely** (ARI +0.769 → +0.007; language stops being linearly
recoverable at all) while *improving* cross-lingual retrieval — so it is not
quietly deleting the museum along with the language.

And with language out of the way, **museum type stops being invisible**: the
probe on specifically-typed museums roughly doubles, from at-baseline to clearly
predictable. That, not the raw numbers above, is the answer to "does the project
have a subject."

Restricting the corpus to English is the option to avoid: English exists for only
{M.get("english_available", 0)} of {A["n"]} museums
({M.get("english_available", 0) / A["n"]:.0%}), so it halves the sample and
re-introduces exactly the anglophone bias the stratification was built to remove.

"""

    # ---- what survives once language is centred out ------------------------
    centered_md = ""
    if CEN:
        RA = M["variants"]["a_full"]["own"]
        CA = CEN["variants"]["a_full"]["own"]
        rows = []
        for key, nice in [("language", "language of the lead"), ("country", "country"),
                          ("type", "type (all)")]:
            r_, c_ = RA[key], CA[key]
            rows.append(
                f"| {nice} | {r_['ari_all']:+.3f} → **{c_['ari_all']:+.3f}** | "
                f"{r_['knn_purity']:.3f} → **{c_['knn_purity']:.3f}** | {r_['knn_chance']:.3f} | "
                f"{r_['probe']['accuracy']:.3f} → **{c_['probe']['accuracy']:.3f}** | "
                f"{r_['probe']['baseline']:.3f} |"
            )
        rts, cts = RA["type_specific"], CA["type_specific"]
        rows.append(
            f"| type (specifically-typed, n={rts['n']}) | "
            f"{rts['ari_all']:+.3f} → **{cts['ari_all']:+.3f}** | "
            f"{rts['knn_purity']:.3f} → **{cts['knn_purity']:.3f}** | {rts['knn_chance']:.3f} | "
            f"{rts['probe']['accuracy']:.3f} → **{cts['probe']['accuracy']:.3f}** | "
            f"{rts['probe']['baseline']:.3f} |"
        )
        best = max([("country", CA["country"]["ari_all"]), ("type", CA["type"]["ari_all"]),
                    ("language", CA["language"]["ari_all"])], key=lambda kv: kv[1])
        type_gain = cts["probe"]["accuracy"] / rts["probe"]["accuracy"]

        centered_md = f"""## What survives once language is centred out

Applying the winning transform to the map corpus itself — per-language centring,
centroids estimated within these {RA["n"]:,} museums — and re-running the whole
analysis.

| label | ARI vs clusters | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|
{chr(10).join(rows)}

**Language is gone.** ARI {RA["language"]["ari_all"]:+.3f} → {CA["language"]["ari_all"]:+.3f},
and the linear probe falls to {CA["language"]["probe"]["accuracy"]:.3f} — *below* its
own {CA["language"]["probe"]["baseline"]:.3f} majority baseline, i.e. no longer
linearly recoverable at all.

**Country survives, and is confirmed as real rather than a language proxy.** Its
probe accuracy actually *rises*, {RA["country"]["probe"]["accuracy"]:.3f} →
{CA["country"]["probe"]["accuracy"]:.3f} against a
{CA["country"]["probe"]["baseline"]:.3f} baseline, because removing the dominant
language direction makes the weaker country direction easier for a linear model
to reach. Its neighbourhood purity drops
({RA["country"]["knn_purity"]:.3f} → {CA["country"]["knn_purity"]:.3f}) — that
part *was* language wearing a country label — but ARI stays near zero throughout:
country is present and distributed, never the shape of the space.

**And museum type comes out from under it.** This is the result that changes the
project's answer. Among specifically-typed museums the probe goes
{rts["probe"]["accuracy"]:.3f} → **{cts["probe"]["accuracy"]:.3f}** against a
{cts["probe"]["baseline"]:.3f} baseline — a {type_gain:.1f}x jump, from
indistinguishable-from-guessing to genuinely predictable. Neighbourhood purity
rises {rts["knn_purity"]:.3f} → {cts["knn_purity"]:.3f} (chance
{rts["knn_chance"]:.3f}), and type becomes the label best aligned with the cluster
structure ({best[0]}, ARI {best[1]:+.3f}). Type was in the embedding the whole
time; language was drowning it.

One honest caveat: HDBSCAN's noise fraction jumps from
{RA["noise_fraction"]:.0%} to {CA["noise_fraction"]:.0%}. Centring removes the
easy, dominant partition and what remains is a flatter, less clumpy space. The
structure that survives is real but weaker — a map of it will look like gradients,
not islands.

![centered, by type](figs/centered_type_facets.png)

![centered, by language](figs/centered_language_facets.png)

"""

    # ---- geography (stage 11) ----------------------------------------------
    geo_md = ""
    if G:
        e = G["bin_edges_km"]
        cen = G["spaces"]["centered"]
        rows = []
        for i in range(len(e) - 1):
            n = cen["all_pairs"]["n_pairs"][i]
            if n < 50:
                continue
            # Both columns are deviations from the *same* reference — the
            # all-pairs global mean — so the two are directly comparable.
            ref = cen["all_pairs"]["global_mean"]
            a = cen["all_pairs"]["mean_similarity"][i] - ref
            sc = cen["same_country"]["mean_similarity"][i]
            nsc = cen["same_country"]["n_pairs"][i]
            sc_s = f"{sc - ref:+.3f}" if sc is not None and nsc >= 30 else "—"
            rows.append(f"| {e[i]:,.0f}–{e[i + 1]:,.0f} | {n:,} | **{a:+.3f}** | {sc_s} | {nsc:,} |")
        rr, rc = G["spaces"]["raw"]["mantel"], G["spaces"]["centered"]["mantel"]
        rad = G["radius"]
        by_t = sorted(G["radius_by_type"].items(), key=lambda kv: kv[1]["median_km"])
        local3 = ", ".join(f"**{k}** ({v['median_km']:,.0f} km)" for k, v in by_t[:3])
        univ3 = ", ".join(f"**{k}** ({v['median_km']:,.0f} km)" for k, v in reversed(by_t[-3:]))

        geo_md = f"""## Geography: the continuous version of the question

Country ARI came out near zero, which reads as "geography is not in the
embedding". That was the wrong instrument rather than the right answer — ARI
compares *partitions*, and geography is a gradient. Measured continuously against
the {G["n_museums"]:,} museums that carry `P625` coordinates
({G["coord_coverage"]:.1%} of the sample), it is emphatically present.

Correlation between log great-circle distance and embedding similarity (negative
= farther apart means less alike): raw **r = {rr["r"]:+.3f}**
(z = {rr["z"]:+.0f} against a shuffled-coordinate null), language-centred
**r = {rc["r"]:+.3f}** (z = {rc["z"]:+.0f}).

### The decay is local, and it stops

| distance (km) | pairs | similarity above global mean | same-country only | pairs |
|---|---|---|---|---|
{chr(10).join(rows)}

![distance decay](figs/distance_decay.png)

Two separable effects fall out of that table, and they are not the same thing:

1. **A steep local effect that dies by ~1,000 km.** Museums within a kilometre of
   each other sit **{cen["all_pairs"]["mean_similarity"][0] - cen["all_pairs"]["global_mean"]:+.3f}**
   above the global mean; by 316–1,000 km it is down to
   {cen["all_pairs"]["mean_similarity"][6] - cen["all_pairs"]["global_mean"]:+.3f}, and beyond
   ~3,000 km it is at the permutation null. This is not a continental or
   civilisational effect — it is *same-place-ness*. Museums in one city are
   genuinely about overlapping subject matter.
2. **A flat national effect that does not decay at all.** Same-country pairs stay
   roughly constant above the mean whether they are 500 km or 5,000 km apart.
   Country contributes an offset, not a gradient — which is exactly why a
   partition metric like ARI could see so little while the continuous
   relationship is this strong.

### Local vs. universal: a candidate axis for the map

Per museum, the median great-circle distance to its 10 nearest embedding
neighbours. Small means its peers are down the road; large means its peers are
everywhere. On the centred space the median museum sits at
{rad["centered"]["median"]:,.0f} km against a
{G["random_pair_median_km"]:,.0f} km random-pair baseline
({rad["centered"]["vs_random"]:.2f}x).

![neighbourhood radius by type](figs/radius_by_type.png)

The ordering is not something the method was told: most locally rooted are
{local3}; most internationally legible are {univ3}. Local-history and open-air
museums are *about* their locality; wars, railways and natural history are
globally shared subject matter. That the score recovers this unprompted is decent
evidence it measures something real, and it is a better organising principle for
a map than anything erasing geography would produce.

**Why geography is not centred out the way language was.** Language entered
through the sampling rule — "longest article across languages" — so it is a fact
about Wikipedia's editorial communities, not about museums, and the parallel
articles gave an oracle to confirm the removal took the artefact rather than the
content. Location is constitutive: a local-history museum in Bavaria *is* about
Bavaria. There is no "same museum, different place" to validate against, so a
geographic residualisation could not be distinguished from having gutted the
space — and every metric would move by construction. The local/universal score
above uses the same information as a lens instead.

**Caveat.** Stratifying by country left only
{cen["same_country"]["n_pairs"][6]:,}–{cen["same_country"]["n_pairs"][5]:,} same-country
pairs in the mid-distance bins and very few past 3,000 km, so the flat national
effect is measured on thin data at the long end. Reading it as "roughly constant"
is safe; reading exact values per bin is not.

"""

    # ---- language-removal section (stage 10) -------------------------------
    parallel_md = ""
    if P:
        SP = P["spaces"]
        raw_, cen_, in_ = SP["raw"], SP["centered"], SP["inlp"]
        rows = []
        for key, nice in [("raw", "raw"), ("centered", "per-language centered"),
                          ("inlp", f"INLP ({P['inlp_dims_removed']}/{P['inlp_dims_total']} dims removed)")]:
            s_ = SP[key]
            rows.append(
                f"| {nice} | {s_['p_at_1']:.3f} | {s_['recall_at_10']:.3f} | {s_['mrr']:.3f} | "
                f"{s_['crowding_same_language']:.2f} | {s_['language_knn_purity']:.3f} | "
                f"{s_['country_knn_purity']:.3f} |"
            )
        name_rows = []
        for key, nice in [("raw", "raw"), ("centered", "per-language centered"), ("inlp", "INLP")]:
            s_ = SP[key]
            ns, na = s_.get("name_shared"), s_.get("name_absent")
            if ns and na:
                name_rows.append(
                    f"| {nice} | {ns['p_at_1']:.3f} | {na['p_at_1']:.3f} | "
                    f"{ns['p_at_1'] - na['p_at_1']:+.3f} |"
                )
        gain = (cen_["p_at_1"] - raw_["p_at_1"]) / raw_["p_at_1"]

        parallel_md = f"""## Can language just be subtracted out?

Judging a de-biasing transform by "did language ARI fall" is circular — subtract
the language means and the language clusters loosen by construction. It says
nothing about whether the *museum* survived the surgery.

So this uses a ground truth that owes nothing to any clustering metric.
**{P["n_museums_multilingual"]:,} of the {P["n_museums"]:,} museums have articles in
two or more languages** — the same institution, described twice, independently.
If a representation is language-neutral, those two articles should find each
other.

- **query**: one article · **pool**: all {P["n_articles"]:,} articles, same-language
  distractors included, because their crowding is the effect being measured
- **correct**: any other article about the same museum (necessarily another language)
- **crowding**: of the articles outranking the true match, what share are in the
  query's own language — the direct read on "language is in the way"

| representation | P@1 | R@10 | MRR | crowding | language 10-NN | country 10-NN |
|---|---|---|---|---|---|---|
{chr(10).join(rows)}

(chance for language 10-NN is {raw_["language_knn_chance"]:.3f}; for country
{raw_["country_knn_chance"]:.3f})

**Centring works, and better than the clustering numbers suggested.** Per-language
centroid subtraction takes cross-lingual P@1 from {raw_["p_at_1"]:.3f} to
**{cen_["p_at_1"]:.3f}** ({gain:+.0%}), drops language neighbour purity from
{raw_["language_knn_purity"]:.3f} to {cen_["language_knn_purity"]:.3f} against a
{raw_["language_knn_chance"]:.3f} floor, and *raises* country purity
({raw_["country_knn_purity"]:.3f} → {cen_["country_knn_purity"]:.3f}) rather than
destroying it. Same-language crowding falls from {raw_["crowding_same_language"]:.2f}
to {cen_["crowding_same_language"]:.2f}.

**INLP over-corrects.** It suppresses language hardest
({in_["language_knn_purity"]:.3f}, nearly the {raw_["language_knn_chance"]:.3f}
floor) but strips {P["inlp_dims_removed"]} of {P["inlp_dims_total"]} dimensions and
takes country purity down with it
({raw_["country_knn_purity"]:.3f} → {in_["country_knn_purity"]:.3f}), for *worse*
retrieval than centring. Its own trace shows why: linear language accuracy
collapses from {P["inlp_train_acc_per_iter"][0]:.3f} to
{P["inlp_train_acc_per_iter"][1]:.3f} after a single projection and then plateaus —
iterations 2 and 3 remove hundreds more dimensions for no further gain. One
iteration would have been the right stopping point.

### Is this just matching the museum's name?

The same museum's articles tend to repeat its proper name verbatim, so retrieval
could be string matching wearing a semantic costume. Splitting the queries by
whether the museum's Wikidata label appears in both articles:

| representation | P@1, name in both | P@1, name absent | gap |
|---|---|---|---|
{chr(10).join(name_rows)}

The gap is small: even with no shared name string, centred P@1 is
{cen_["name_absent"]["p_at_1"]:.3f} across {cen_["name_absent"]["n"]:,} queries. The
cross-lingual signal is real content, not surface overlap. (Conservative
caveat: "name absent" only checks the *English* label verbatim — a translated or
transliterated form of the name could still be present in both texts.)

![language dissolving](figs/language_dissolve.png)

In the bottom row every language covers the whole cloud — but so does everything
else. INLP does not so much mix the languages as flatten the space into a ball;
that is what removing {P["inlp_dims_removed"]} of {P["inlp_dims_total"]}
dimensions looks like, and it is why its retrieval is worse than centring's
despite the better language score.

**One caveat on comparing these numbers to the tables above.** This section runs
on a different corpus: {P["n_articles"]:,} articles including *several languages
per museum*, where the main analysis uses one article per museum. Same-museum
articles in different languages attract each other, so the language effect is
weaker here by construction — raw language 10-NN purity is
{raw_["language_knn_purity"]:.3f} in this corpus versus
{M["variants"]["a_full"]["own"]["language"]["knn_purity"]:.3f} in the map corpus.
The raw-vs-centred-vs-INLP comparison is internally valid; the absolute purity
values are not interchangeable between sections.

"""

    md = f"""# Does country or museum type already explain the embedding space?

> **Short answer: neither — but article *language* does, and that is a confound
> introduced by the sampling rule rather than a fact about museums.**

A go/no-go probe for the museum map: if the embedding of a museum's Wikipedia
lead is mostly a proxy for *where it is* and *what kind of museum it is*, then a
semantic map adds nothing over a choropleth with a type filter.

**Model:** `{M["model"]}` · **UMAP:** 10D for clustering, 2D for display,
`random_state=42` · **Clustering:** HDBSCAN (`min_cluster_size=15`,
`min_samples=5`)

{verdict}{parallel_md}{centered_md}{geo_md}## How to read this

`ARI` compares two *partitions*, so ~{A["n_clusters"]} HDBSCAN clusters
against {A["n_countries"]} countries is penalised for cardinality
mismatch even when the space is strongly geographic. Two measures without that
problem are reported next to it:

- **10-NN country purity** — of a museum's 10 nearest neighbours, what share sit
  in the same country? Compare against **chance** (`sum p_i^2`). This is the
  number to look at first.
- **linear probe** — cross-validated accuracy of logistic regression recovering
  the country from the embedding, against the majority-class **baseline**. This
  is the ceiling on how much country information is present at all.

A map is "trivial" if neighbourhoods are overwhelmingly same-country *and*
removing explicit geography collapses that.

## Sample

{M["variants"][V[0]]["own"]["n"]} museums, stratified by country with allocation
proportional to `sqrt(n_country)` — the raw Wikidata distribution is Italy 8.9k /
Germany 8.5k / US 7.0k, which a uniform draw would reproduce.

Lead text is the **longest** available article across all Wikipedia languages,
not English by default. Selected-language mix: {lang_str}.

Note that "longest in characters" is not script-neutral — the same content is far
shorter in Japanese or Chinese than in German — so CJK articles are
systematically under-selected.

### Lead length

| stat | chars |
|---|---|
| mean | {L["mean"]:.0f} |
| p10 | {L["10%"]:.0f} |
| p25 | {L["25%"]:.0f} |
| median | {L["50%"]:.0f} |
| p75 | {L["75%"]:.0f} |
| p90 | {L["90%"]:.0f} |
| max | {L["max"]:.0f} |

![lead lengths](figs/lead_lengths.png)

### Location stripping (variant c)

Gazetteer built per museum from every label and alias, in every language, of its
country and its full `P131` containment chain, plus demonyms (`P1549`); combined
with spaCy `xx_ent_wiki_sm` LOC spans.

- mean characters removed: **{S["mean_frac_chars_removed"]:.1%}** (median {S["median_frac_chars_removed"]:.1%})
- leads where the museum's own name was also removed: **{S["museum_name_removed_share"]:.1%}**

That last number matters: multilingual NER tags institution names as `LOC`
("Louvre" → LOC), so variant (c) is in practice *geography and much of the
institution's proper name* removed, which makes it a stricter test than intended.

## Results — each variant on its own usable rows

The faithful per-variant read. Variant (b) has a smaller `n` because
{single_sent:.0%} of leads are a single sentence, leaving nothing behind once it
is removed.

{all_tables("own")}

## Results — common subset (identical museums in all three variants)

Restricting all three to the same museums makes the numbers directly comparable,
at the cost of skewing long: dropping the single-sentence leads removes the
shortest stubs.

{all_tables("common")}

## Results — common subset, shortest length quartile dropped

Cut at {M["shortest_quartile_char_cutoff"]:.0f} characters.

{all_tables("drop_shortest_quartile")}

## Figures

Each variant gets a small-multiple grid (all points grey, one category
highlighted) and the single-panel coloured scatter.

"""
    for v in V:
        md += f"""### {VARIANT_TITLE[v]}

**By article language** — the dominant axis

![{v} language facets](figs/{v}_language_facets.png)

![{v} language scatter](figs/{v}_language_scatter.png)

**By country**

![{v} country facets](figs/{v}_country_facets.png)

![{v} country scatter](figs/{v}_country_scatter.png)

**By type**

![{v} type facets](figs/{v}_type_facets.png)

![{v} type scatter](figs/{v}_type_scatter.png)

"""

    md += """## Caveats

- Character-length selection of the "longest" article biases against CJK scripts.
- Variant (c) also removes institution names (see above), so it under-states how
  much signal survives geography removal.
- Type labels are the most specific of a museum's `P31` values among the 15 most
  common museum types; Wikidata typing is uneven, and a large "museum"/"other"
  bucket is unavoidable.
- HDBSCAN noise points are kept as a single group for `ARI_all`; the
  clustered-only figures are in `metrics_*.json`.
- One encoder, one clustering setting. Rerun with `--model BAAI/bge-m3` to check
  the conclusion is not an artefact of the encoder.
"""

    out = REPORTS / "report.md"
    out.write_text(md)
    print(f"wrote {out}")
    print(f"wrote {len(list(FIGS.glob('*.png')))} figures to {FIGS}")


if __name__ == "__main__":
    main()
