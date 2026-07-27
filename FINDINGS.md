# The Museum Map — what the full corpus shows

The probe asked a go/no-go question on 2,000 museums: is the embedding space of
museum Wikipedia leads just a restatement of country and type? It said no, and
that type is real recoverable content. This is the same set of questions asked of
the built map, on **49,218 museums in 183 languages** — every museum in Wikidata
with a Wikipedia article.

Map: `reports/map_full_short.html`. Numbers: `data/processed/map_full/analysis_short.json`.

## The headline

**The probe's conclusions replicate, and the two that matter get stronger.** But
the stratified 2,000-museum sample was actively misleading about geography, and
one finding I carried forward from it turns out to be wrong (see *Corrections*).

| | probe (2,000, stratified) | full (49,218) |
|---|---|---|
| region ARI vs country | +0.016 | **+0.004** |
| region ARI vs language | +0.017 | **+0.006** |
| type probe vs majority baseline | 0.54–0.57 vs 0.266 | **0.657 vs 0.230** |
| 10-NN country purity (vs chance) | 0.140 (0.007) | **0.447 (0.041)** |
| neighbourhood radius vs random pair | 0.38x | **0.14x** |

## The map is not a restatement of country, language, or type

Adjusted Rand Index between the discovered regions and each candidate
explanation, at every layer:

| layer | regions | vs country | vs type | vs language |
|---|---|---|---|---|
| 0 (finest) | 951 | +0.004 | −0.002 | +0.006 |
| 1 | 269 | +0.004 | +0.005 | −0.001 |
| 2 | 80 | +0.004 | +0.042 | −0.008 |
| 3 (coarsest) | 20 | +0.012 | +0.033 | +0.013 |

None of the three partitions the space at any scale. The coarsest twenty regions
are subject matter, not places:

> Japanese Prefectural Art and Heritage · Chinese and Taiwanese Arts · Heritage
> Railways · Military Aviation History · Regional Folk Heritage · War Memorials ·
> Diocesan Sacred Art · Historic European Religious Architecture · Maritime and
> Naval Heritage · Medieval Castles · English Country Houses and Estates ·
> Historic Residences · Writers' and Artists' Birthplaces · Natural History ·
> Science Centers · University and American Contemporary Art · Regional Heritage
> · National Heritage Museums · Contemporary Art Galleries · International Modern
> Art Collections

Geography appears as a modifier on subject ("Japanese Prefectural Art and
Heritage"), never as the top-level split.

## The map recovers subject matter that Wikidata does not record

This is the strongest argument that the map carries information a choropleth with
a type filter could not.

**64.1% of the corpus (31,565 museums) carries only the generic `museum` P31 or
no museum type at all.** Of those, **17,697 land inside a *named* coarse region**
— the map assigns a subject to them that their metadata does not have.

| region | museums | of which Wikidata types generically |
|---|---|---|
| Regional Heritage | 7,377 | 70.9% |
| Natural History | 1,919 | 72.8% |
| Writers' and Artists' Birthplaces | 1,958 | 69.5% |
| Heritage Railways | 2,409 | 51.2% |
| War Memorials | 1,755 | 68.0% |
| Maritime and Naval Heritage | 949 | 79.1% |

The Heritage Railways region holds 469 declared `heritage railway` and 432
declared `railway museum` entries — and **847 museums Wikidata calls nothing more
specific than "museum"**. The text knows they are about railways; the structured
data does not.

The linear probe puts a number on it: **0.657 accuracy against a 0.230 majority
baseline** on the 17,653 specifically-typed museums, up from 0.54–0.57 on the
probe's sample. Type is *more* recoverable at scale, not less.

## Geography: the stratified sample hid most of it

The probe found a steep local decay and concluded geography was a gradient rather
than a partition. That holds — country ARI is +0.004 — but the *strength* was
badly understated, and the sampling rule is why.

The probe's 2,000 were allocated across countries ∝ √n, deliberately flattening
Italy/Germany/US from ~30% of all museums down to a fraction of that. That
flattening also, by construction, pushed each museum's neighbours into different
countries. Removing it:

- **Median distance to a museum's 10 nearest *embedding* neighbours: 782 km**,
  against a 5,721 km random-pair baseline — **0.14x**, where the stratified
  sample said 0.38x.
- 10-NN country purity **0.447 against 0.041 chance — 11x**.

So a museum's semantic neighbours are, typically, a few hundred kilometres away.
Geography is much more present in this space than the probe could see.

**The local↔universal axis reproduces the probe's unprompted ordering:**

| most locally rooted | | most internationally legible | |
|---|---|---|---|
| independent museum | 205 km | aviation museum | 1,538 km |
| religious museum | 347 km | natural history museum | 1,060 km |
| museum of a public entity | 369 km | sculpture garden | 1,057 km |
| local museum | 379 km | railway museum | 847 km |
| historic house museum | 406 km | working life museum | 830 km |

Local-history and religious museums are *about* their locality; aircraft,
dinosaurs and locomotives are globally shared subject matter. A nice detail: a
*heritage railway* (483 km) is a local institution, while a *railway museum*
(847 km) is an international genre.

## Language

Raw 10-NN language purity is 0.404 against 0.073 chance, which looks alarming
next to a language ARI of +0.006. It is almost entirely geography: German museums
sit in Germany, are described in German, and are near each other.

**Controlling for country** — looking only at neighbour pairs within the same
country, against each country's own language mix — the same-language rate is
**0.760 against 0.614 chance, a ratio of 1.24x.** There is a small residual
language effect. It is not what organises the map.

This is after per-language leave-one-out centring with shrinkage, which is still
warranted: **40 of the 183 languages have exactly one museum**, and plain
per-language centring maps a singleton group onto the origin, manufacturing a
dense fake cluster at the centre of the map.

## Corrections

**The stub finding does not replicate, and I had it backwards.** On the fixture,
museums with leads under 150 characters were 48.4% unlabelled against 38.2% for
the longest, and sat at the largest neighbourhood radius — I reported this as the
map's main quality risk. At full scale it is **flat**:

| lead length | museums | unlabelled | radius |
|---|---|---|---|
| <150 chars | 6,255 | 54.7% | 616 km |
| 150–300 | 9,631 | 56.4% | 750 km |
| 300–600 | 13,703 | 56.4% | 825 km |
| 600–1,200 | 12,463 | 55.4% | 850 km |
| 1,200+ | 7,166 | 57.1% | 748 km |

Point-biserial correlation between lead length and being unlabelled: **+0.011**.
By decile the range is 54.3%–57.6%, and the *shortest* decile is the least
unlabelled. Short leads are also slightly more locally rooted, not more
dispersed.

The likely reason the fixture said otherwise: at 2,000 museums the stubs are
sparse and scatter into noise, while at 49,218 there are enough of them to form
their own dense, nameable regions. Scale changed the answer.

**The unlabelled fraction is higher at scale** — 56.0% at the finest layer
against 41.4% on the fixture — but it is not the stubs causing it, and it is not
a defect. Toponymy names *regions of the space*; a point in an unnamed gap at the
finest layer still sits inside a named region at a coarser one.

## Method notes

- **Corpus.** All 55,280 Wikidata museums; 49,243 have a Wikipedia article
  (`sitelink_count` counts Commons and Wikiquote, hence the 6,037 shortfall), and
  49,218 yield a usable lead from 145,712 articles.
- **Which article represents a museum.** The lead is taken from an official
  language of the museum's country when that article is at least half as long as
  the longest available, otherwise the longest wins. Plain longest-wins left
  30.4% of museums that *have* a local-language article represented by another
  one. The confound is not language but **perspective**: the Spanish article on
  the Seoul Museum of Art leads with a Joseon royal palace, the Korean one with
  its status as a bureau of the city government. Always preferring the local
  article overcorrects — it pushes leads under 200 characters from 18.4% to
  23.7%. The 50% rule buys 13 points of locality (56.0% → 69.1%) for one point of
  stubs.
- **What the tooltip shows, and why it is not what the map is built from.** 80.9%
  of leads are not in English — the direct consequence of preferring the
  local-language article — so the tooltip was unreadable for most of the map.
  Each museum now gets a one-sentence English summary of *its embedded lead*
  (Haiku 4.5, ~$21 for the corpus), not of its English Wikipedia article, because
  the tooltip should explain why a point sits where it does.

  These are shown, never embedded. A paired A/B on the same 2,000 fixture museums
  found summaries were *not* homogenising — pairwise-similarity spread was
  slightly wider (0.078 vs 0.074) and cluster structure nearly identical (61 vs
  62 fine regions, same layer count, same unlabelled rate) — and they scored
  higher on the type probe (0.523 vs 0.470). That gain is not trustworthy: the
  probe is measured against Wikidata's *English* type labels, which English
  summaries are lexically closer to by construction.

  The decisive number is grounding. An Opus 5 audit of 150 summaries, weighted
  toward thin leads, found **8% assert something their source does not** — drift
  rather than invention ("named after the anatomist Luigi Cattaneo" → "made by
  him"; "a 1676 Dutch prison" → "a fort"). Acceptable for a reading aid labelled
  as machine-generated with the article one click away; not acceptable for the
  embedding, where it would place ~1 museum in 12–20 partly by a claim its
  article never made, unauditably, and would falsify the project's own
  description of what the map is.
- **What a museum is called.** 15.1% of the corpus (7,421 museums) has no English
  label on Wikidata, and the harvest stores the QID in the label column for those
  rather than leaving it null — so a `fillna` fallback silently never fires and
  the tooltip reads "Q24254667". Names now fall back to the Wikipedia article
  title, which is present for all 7,421 and is the better name regardless: it is
  what the museum is actually called, in its own language. Germany, Poland,
  Russia and Ukraine are the most affected.
- **Encoder.** BGE-M3, sequence capped at 2,048 tokens (0.04% of leads
  truncated). One text variant: the lead as fetched.
- **Layout.** Per-language leave-one-out centring with shrinkage, then UMAP to
  2D, `random_state=42`.
- **Naming.** Toponymy with Claude Haiku 4.5, 1,320 regions across 4 layers, with
  an explicit brevity instruction — the default names run 12–15 words and are
  unusable as map labels.

## What is still open

- **56% unlabelled at the finest layer** is a description of a smooth space, not
  a failure, but it is worth asking whether a larger `base_min_cluster_size`
  gives a more useful finest layer than 951 regions of which most points sit
  outside any of them.
- **Hover and click on the rendered map are unverified.** Synthetic pointer
  events do not reach a WebGL canvas, so these were confirmed only as far as the
  data going in. The search box was verified end to end.
- **The residual 1.24x language effect** has not been chased down. The probe's
  cross-lingual retrieval test (parallel articles for the same museum) was never
  re-run at full scale; that is the clean way to settle it.
