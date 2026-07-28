# The Museum Map — what it shows

This page describes what is in the map and what it can tell you about museums.
Three things stand out: some kinds of museum are local institutions while others
are an international genre; the map knows what a museum is about even when
Wikidata does not; and geography runs through all of it as a gradient rather than
as a set of borders.

Most numbers on this page are measured on the `full` corpus — **49,218 museums in
158 languages**, every museum Wikidata *types* as a museum — because that is the
corpus the analysis was run against. The map that ships is `full_recovered`
(54,778), which adds the 5,560 museums Wikidata types as houses and buildings;
*Adding the missing museums changes nothing* recomputes everything against it.

Numbers: `data/processed/map_full/analysis_short.json`.
Maps: `reports/map_full_recovered_short.html` (shipped),
`reports/map_full_short.html` (what these numbers describe).

## Some kinds of museum are local, others are an international genre

The most legible thing the map measures. For each museum, take its 10 nearest
neighbours *in the embedding* and ask how far away they are on the ground:

| most locally rooted | | most internationally legible | |
|---|---|---|---|
| independent museum | 204 km | aviation museum | 1,496 km |
| local museum | 371 km | sculpture garden | 1,246 km |
| religious museum | 380 km | natural history museum | 965 km |
| museum of a public entity | 406 km | national museum | 943 km |
| historic house museum | 436 km | railway museum | 921 km |

Local-history and religious museums are *about* their locality; aircraft,
dinosaurs and locomotives are globally shared subject matter. The sharpest case is
a pair that structured data treats as near-synonyms: a **heritage railway** is a
local institution at 487 km, a **railway museum** an international genre at
921 km.

This is the axis that tells you which museums reward travelling for, and it falls
out of the text alone — nothing in the pipeline was told where anything is.

## The map knows what a museum is about when Wikidata does not

**64.1% of the corpus (31,565 museums) carries only the generic `museum` type, or
nothing among the 25 commonest museum types.** Of those, **14,500 land inside a
*named* region** at the 21-region layer — the map gives them a subject their
metadata does not have.

Add back the 5,560 museums the corpus misses — none of which carries a museum type
at all — and it is **67.8% (37,125 of 54,778)**, of which **19,277** land in a
named region at the 22-region layer. The metadata is poorer than the corpus's own
headline suggests, and the text carries correspondingly more of the load.

| region | museums | of which Wikidata types generically |
|---|---|---|
| Municipal and City Heritage | 2,290 | 73.5% |
| War and Military Memorials | 2,020 | 67.4% |
| Writers' and Artists' Memorial Houses | 1,844 | 67.3% |
| Ethnographic and Folk Traditions | 1,803 | 68.2% |
| Natural History and Paleontology | 1,284 | 66.2% |
| European Castles and Palaces | 1,273 | 65.8% |

The Heritage and Tourist Railways region holds 461 declared `heritage railway`
and 393 declared `railway museum` entries — and **410 museums Wikidata calls
nothing more specific than "museum"**. Natural History and Paleontology holds 290
declared `natural history museum` entries against **710 generic ones**. Those 410
and 710 are museums you could not have found by filtering Wikidata at all.

A linear probe puts a number on how recoverable type is from the text alone:
**0.655 accuracy against a 0.230 majority baseline** on the 17,653
specifically-typed museums.

## What the regions actually are

The coarsest seven, which is what you see zoomed all the way out:

> Regional Art and History · War and Military Memorials · Historic Houses ·
> Natural History · Contemporary Art · Municipal and City Heritage ·
> Ethnographic and Folk Traditions

The 21-region layer below it is where the map is most readable, and it is the
best single answer to "what kinds of museum are there":

> Military Aviation Heritage · Vintage and Classic Vehicles · War and Military
> Memorials · Chinese Regional History · Japanese Local History and Art ·
> Heritage and Tourist Railways · Historic Mills and Mining Heritage · Medieval
> Religious Architecture · English Country Houses and Estates · Maritime and
> Naval Heritage · European Castles and Palaces · Interactive Science Centers ·
> Natural History and Paleontology · Historic House Museums · Writers' and
> Artists' Memorial Houses · Diocesan Sacred Art and Treasuries · Municipal and
> City Heritage · Ethnographic and Folk Traditions · Artist-Focused Commercial
> Galleries · Contemporary and Modern Art · American and University Art

Every one of those is subject matter. None of them is a place, a language or a
Wikidata class — measured as Adjusted Rand Index against each, at every layer:

| layer | regions | vs country | vs type | vs language |
|---|---|---|---|---|
| 0 (finest) | 984 | +0.002 | +0.001 | +0.002 |
| 1 | 287 | +0.002 | +0.021 | −0.001 |
| 2 | 85 | +0.005 | +0.036 | −0.001 |
| 3 | 21 | +0.009 | +0.054 | +0.021 |
| 4 (coarsest) | 7 | +0.013 | +0.025 | +0.033 |

Where geography does show up in a name it is a modifier on subject — *Japanese
Prefectural Art and Heritage* — never the top-level split.

## Adding the missing museums changes nothing

The numbers above are measured on a corpus defined by `wdt:P31/wdt:P279*
wd:Q33506`, which misses 5,560 museums that Wikidata types as houses and
buildings — 24% of US museums, against 2% for Italy and Japan (`COVERAGE.md`).
That is not a neutral omission: it is a systematic hole in one country, and it
would be reasonable to expect the map to look different once it is filled.

So the map was rebuilt with those museums added — `full_recovered`, 54,778
museums — and every metric on this page recomputed. The added set is **31.5% US
against the corpus's 10.3%** and **44% English-lead against 20.3%**, so it pushes
hard in the direction most likely to change the answer.

**Nothing moves.**

| ARI vs country | full | full_recovered |
|---|---|---|
| layer 0 (984 / 1,085 regions) | +0.002 | **+0.002** |
| layer 1 | +0.002 | +0.004 |
| layer 2 | +0.005 | +0.005 |
| layer 3 | +0.009 | +0.010 |
| layer 4 (coarsest) | +0.013 | +0.011 |

Every delta is within ±0.002. Language ARI moves slightly *negative* at every
layer. The type probe is 0.655 → 0.656 on an identical 17,653 specifically-typed
museums, and the local/universal ratio 0.14x → 0.13x.

10-NN purity needs reading as lift over chance, because adding a US-heavy set
raises the chance baseline mechanically:

| 10-NN purity | full | full_recovered |
|---|---|---|
| country | 0.435 = 10.6x chance | 0.446 = **10.2x** chance |
| language | 0.470 = 5.9x chance | 0.488 = **5.6x** chance |
| type | 0.465 = 1.5x chance | 0.433 = **1.6x** chance |

Country purity's raw rise is entirely the chance baseline moving from 0.041 to
0.044. Controlled for composition, geographic determinism goes *down*.

The recovered museums arrive as subject regions, not geographic ones —
`Railway Museums and Heritage Depots`, `Historic Steam-Powered Vessels`,
`National Park Service Visitor Centers`. 1,752 new US museums, overwhelmingly
historic house museums, were absorbed by what they are about.

`full_recovered` is the map that ships
(`reports/map_full_recovered_short.html`), built by `p07_gap` + `p08_recover`.
`full` stays buildable on its own — `p07` and `p08` read its leads as their input,
and `p08` never writes over it — so every other number on this page still
describes `map_full_short.html`, the artifact it was computed on.

## Geography is everywhere in the map, and it is a gradient

Country ARI is +0.002, so country does not *partition* the space. That is easy to
misread as "geography isn't in here." It is, densely:

- **Median distance to a museum's 10 nearest *embedding* neighbours: 825 km**,
  against a 5,721 km random-pair baseline — **0.14x**.
- 10-NN country purity **0.435 against 0.041 chance — 11x**.

A museum's semantic neighbours are, typically, a few hundred kilometres away.
Nothing in the pipeline was given a coordinate; this is what museums being about
their own surroundings looks like from the text.

Both facts are true at once, and the map shows both: recolour by country and it
is confetti at a glance, with real concentrations up close. Geography appears in
the region names as a modifier on subject — *Japanese Prefectural Art and
Heritage* — never as the top-level split.

## Language

Raw 10-NN language purity is 0.470 against 0.079 chance, which looks alarming
next to a language ARI of +0.002. It is almost entirely geography: German museums
sit in Germany, are described in German, and are near each other.

**Controlling for country** — looking only at neighbour pairs within the same
country, against each country's own language mix — the same-language rate is
**0.935 against 0.846 chance, a ratio of 1.11x.** There is a small residual
language effect. It is not what organises the map.

Both halves of that moved when the lead-selection rule was fixed, in opposite
directions and for the same reason. Concentrating each country on its dominant
language raised raw purity (0.404 → 0.470) *and* raised the within-country chance
rate further (0.614 → 0.846), so the excess over chance fell: **1.24x → 1.11x**.
Language is now more fully explained by geography, not less. Anyone quoting the
raw purity number alone would reach the opposite conclusion.

This is after per-language leave-one-out centring with shrinkage, which is still
warranted: **30 of the 158 languages have exactly one museum**, and plain
per-language centring maps a singleton group onto the origin, manufacturing a
dense fake cluster at the centre of the map.

## What the shipped map is

Every number above is computed on `full` (49,218), which is the corpus this
analysis was run against. The map that ships is `full_recovered` (54,778) — the
section above shows the two agree wherever it matters. Its Toponymy layers, for
the record:

| layer | regions | Unlabelled |
|---|---|---|
| 0 (finest) | 958 | 55.3% |
| 1 | 268 | 52.8% |
| 2 | 83 | 45.9% |
| 3 | 22 | 45.8% |
| 4 (coarsest) | 6 | 45.7% |

`Unlabelled` is the unnamed gap between named regions at that zoom, recomputed
per layer; it is kept on purpose. 55.3% at the finest layer describes a smooth
space, not a defect.

## Thin articles are not a quality problem

Worth stating because the opposite is the natural assumption, and because a
2,000-museum sample said the opposite first. On that sample, museums with leads
under 150 characters were 48.4% unlabelled against 38.2% for the longest, and sat
at the largest neighbourhood radius — which read as the map's main quality risk.
At full scale it is **flat**:

| lead length | museums | unlabelled | radius |
|---|---|---|---|
| <150 chars | 7,869 | 56.8% | 541 km |
| 150–300 | 11,121 | 57.0% | 768 km |
| 300–600 | 14,196 | 56.8% | 871 km |
| 600–1,200 | 11,005 | 57.4% | 948 km |
| 1,200+ | 5,027 | 56.3% | 945 km |

Point-biserial correlation between lead length and being unlabelled: **+0.011**.
By decile the range is 54.3%–57.6%, and the *shortest* decile is the least
unlabelled. Short leads are also slightly more locally rooted, not more
dispersed.

The likely reason a sample says otherwise: at 2,000 museums the stubs are sparse
and scatter into noise, while at 49,218 there are enough of them to form their own
dense, nameable regions. Scale changes the answer — which is a caution about
sampled fixtures generally, not about this measurement.

It holds a second time on `full_recovered`, whose stub tail is larger (8,397
museums under 150 chars against 7,869) and differently composed: 55.4% unlabelled
for the shortest band against 57.4% for the longest, radius still climbing
monotonically 523 → 925 km. A result that holds on two corpora with different
composition is worth more than one that holds only on the corpus it came from.

**The unlabelled fraction is higher at scale** — 56.9% at the finest layer
against 41.4% on the fixture — but it is not the stubs causing it, and it is not
a defect. Toponymy names *regions of the space*; a point in an unnamed gap at the
finest layer still sits inside a named region at a coarser one.

## Method notes

- **Corpus.** All 55,280 Wikidata museums; 49,243 have a Wikipedia article
  (`sitelink_count` counts Commons and Wikiquote, hence the 6,037 shortfall), and
  49,218 yield a usable lead from 145,712 articles.
- **Which article represents a museum.** The lead comes from a language spoken in
  the museum's country when that article is at least half as long as the longest
  available, otherwise the longest wins; among eligible local articles, the
  better-covered language wins rather than the longer one. **94.2%** of leads are
  now in a local language.

  Plain longest-wins left 30.4% of museums that *have* a local-language article
  represented by another one. The confound is not language but **perspective**:
  the Spanish article on the Seoul Museum of Art leads with a Joseon royal
  palace, the Korean one with its status as a bureau of the city government.
  Always preferring the local article overcorrects — it pushes leads under 200
  characters from 18.4% to 23.7% — so the 50% floor stays.

  Defining "local language" took three attempts, and the first two were wrong in
  ways that were invisible in aggregate:

  1. **Wikidata P37 (official language) alone.** The United States has no
     official language federally, so its P37 is Spanish and Hawaiian — English
     absent. The rule therefore treated Spanish as local for all 5,080 US
     museums and *preferred* it. Separately, China's P37 is `zh-cn` and Taiwan's
     `zh-tw`, codes no Wikipedia uses, so no Chinese article ever counted as
     local for 1,573 museums. 13.5% of the corpus was affected.
  2. **P37 ∪ P2936 ("language used"), region subtags stripped.** Fixes the
     missing language but not the spurious ones: the US now resolves to
     `{en, es, haw}`, and a US museum whose Spanish article is longer than its
     English one is still represented in Spanish. Local-language share 69.1% →
     83.9%, and the National Museum of Mathematics was still on `es.wikipedia`.
  3. **Ranking local languages by coverage.** Among eligible local articles,
     prefer the language with the most articles about *that country's* museums —
     a fact about coverage, not about the current selection, so it does not feed
     back on itself. Resolves the US to English, China and Taiwan to Chinese,
     Japan to Japanese. 83.9% → 94.2%.

  The remaining limitation is structural: country-level data cannot distinguish a
  museum in Puerto Rico (where Spanish *is* local) from one in Manhattan. The
  rule picks the national plurality and is wrong for the minority case.
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
- **Naming.** Toponymy with Claude Haiku 4.5, 1,384 regions across 5 layers, with
  an explicit brevity instruction — the default names run 12–15 words and are
  unusable as map labels.

## What is still open

- **57% unlabelled at the finest layer** is a description of a smooth space, not
  a failure. A sweep of `base_min_cluster_size` settled this: raising it from 10
  to 100 moves unlabelled only 56% → 43% and stops improving after that, while
  costing a whole zoom level and 90% of the fine regions. The space is genuinely
  smooth; that is not a parameter artefact, and the fix is worse than the
  finding.
- **Hover and click were verified by hand**, not by this pipeline — synthetic
  pointer events do not reach a WebGL canvas. The search box was verified end to
  end programmatically. Touch was not exercised at all, and on a phone the card
  is currently unreachable; see the README on mobile.
- **The residual 1.11x language effect** has not been chased down. A cross-lingual
  retrieval test — parallel articles for the same museum, checking whether they
  land together — is the clean way to settle it, and has never been run at full
  scale. It shrank rather than grew when the lead rule was fixed, so it is a lower
  priority than it looks.
- **The lead rule is national, the world is not.** A museum in Puerto Rico or
  Catalonia or Quebec gets its country's plurality language, not its own. Fixing
  it needs subnational data (`P131` is already fetched, and now labelled by `p09`)
  and would matter most for exactly the regions a world map should not flatten.
