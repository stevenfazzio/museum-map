# The Museum Map — what the full corpus shows

The probe asked a go/no-go question on 2,000 museums: is the embedding space of
museum Wikipedia leads just a restatement of country and type? It said no, and
that type is real recoverable content. This is the same set of questions asked of
the built map, on **49,218 museums in 158 languages** — every museum in Wikidata
with a Wikipedia article.

Map: `reports/map_full_short.html`. Numbers: `data/processed/map_full/analysis_short.json`.

## The headline

**The probe's conclusions replicate, and the two that matter get stronger.** But
the stratified 2,000-museum sample was actively misleading about geography, and
one finding I carried forward from it turns out to be wrong (see *Corrections*).

| | probe (2,000, stratified) | full (49,218) |
|---|---|---|
| region ARI vs country | +0.016 | **+0.002** |
| region ARI vs language | +0.017 | **+0.002** |
| type probe vs majority baseline | 0.54–0.57 vs 0.266 | **0.655 vs 0.230** |
| 10-NN country purity (vs chance) | 0.140 (0.007) | **0.435 (0.041)** |
| neighbourhood radius vs random pair | 0.38x | **0.14x** |

## The map is not a restatement of country, language, or type

Adjusted Rand Index between the discovered regions and each candidate
explanation, at every layer:

| layer | regions | vs country | vs type | vs language |
|---|---|---|---|---|
| 0 (finest) | 984 | +0.002 | +0.001 | +0.002 |
| 1 | 287 | +0.002 | +0.021 | −0.001 |
| 2 | 85 | +0.005 | +0.036 | −0.001 |
| 3 | 21 | +0.009 | +0.054 | +0.021 |
| 4 (coarsest) | 7 | +0.013 | +0.025 | +0.033 |

None of the three partitions the space at any scale. The coarsest seven regions
are subject matter, not places:

> Regional Art and History · War and Military Memorials · Historic Houses ·
> Natural History · Contemporary Art · Municipal and City Heritage ·
> Ethnographic and Folk Traditions

The 21-region layer below it is where the map is most readable:

> Military Aviation Heritage · Vintage and Classic Vehicles · War and Military
> Memorials · Chinese Regional History · Japanese Local History and Art ·
> Heritage and Tourist Railways · Historic Mills and Mining Heritage · Medieval
> Religious Architecture · English Country Houses and Estates · Maritime and
> Naval Heritage · European Castles and Palaces · Interactive Science Centers ·
> Natural History and Paleontology · Historic House Museums · Writers' and
> Artists' Memorial Houses · Diocesan Sacred Art and Treasuries · Municipal and
> City Heritage · Ethnographic and Folk Traditions · Artist-Focused Commercial
> Galleries · Contemporary and Modern Art · American and University Art

Geography appears as a modifier on subject ("Japanese Prefectural Art and
Heritage"), never as the top-level split.

## The verdict survives closing the corpus's largest known bias

The numbers above are measured on a corpus defined by `wdt:P31/wdt:P279*
wd:Q33506`, which misses 5,560 museums that Wikidata types as houses and
buildings — 24% of US museums, against 2% for Italy and Japan (`COVERAGE.md`).
That is not a neutral omission: it is a systematic hole in one country, and the
obvious worry is that "the map is not a restatement of country" holds only
because the corpus under-samples its largest country.

So the map was rebuilt with those museums added — `full_recovered`, 54,778
museums — and every metric on this page recomputed. The added set is **31.5% US
against the corpus's 10.3%** and **44% English-lead against 20.3%**, so it pushes
hard in exactly the direction that should break the finding.

**It does not move.**

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

This is a stronger claim than the original run supports. The verdict was not
merely unchallenged; it survived a directed attempt to break it using the
corpus's own worst bias.

`full_recovered` is a parallel corpus (`--corpus full_recovered`), built by
`data/interim/gap/` + a recovery stage. `map_full` is never written by it, so
every number elsewhere on this page still describes the artifact it names.

## The map recovers subject matter that Wikidata does not record

This is the strongest argument that the map carries information a choropleth with
a type filter could not.

**64.1% of the corpus (31,565 museums) carries only the generic `museum` P31 or
no museum type at all.** Of those, **14,500 land inside a *named* region at the
21-region layer** — the map assigns a subject to them that their metadata does
not have.

That figure understates the problem, because the corpus is itself selected on
Wikidata having typed a museum as a museum. Add back the 5,560 it misses — none
of which carries any museum type, definitionally — and it is **67.8% (37,125 of
54,778)**. The metadata is poorer than this page's headline number suggests, and
the text carries correspondingly more of the load.

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
declared `natural history museum` entries against **710 generic ones**. The text
knows what these are about; the structured data does not.

The linear probe puts a number on it: **0.655 accuracy against a 0.230 majority
baseline** on the 17,653 specifically-typed museums, up from 0.54–0.57 on the
probe's sample. Type is *more* recoverable at scale, not less.

## Geography: the stratified sample hid most of it

The probe found a steep local decay and concluded geography was a gradient rather
than a partition. That holds — country ARI is +0.002 — but the *strength* was
badly understated, and the sampling rule is why.

The probe's 2,000 were allocated across countries ∝ √n, deliberately flattening
Italy/Germany/US from ~30% of all museums down to a fraction of that. That
flattening also, by construction, pushed each museum's neighbours into different
countries. Removing it:

- **Median distance to a museum's 10 nearest *embedding* neighbours: 825 km**,
  against a 5,721 km random-pair baseline — **0.14x**, where the stratified
  sample said 0.38x.
- 10-NN country purity **0.435 against 0.041 chance — 11x**.

So a museum's semantic neighbours are, typically, a few hundred kilometres away.
Geography is much more present in this space than the probe could see.

**The local↔universal axis reproduces the probe's unprompted ordering:**

| most locally rooted | | most internationally legible | |
|---|---|---|---|
| independent museum | 204 km | aviation museum | 1,496 km |
| local museum | 371 km | sculpture garden | 1,246 km |
| religious museum | 380 km | natural history museum | 965 km |
| museum of a public entity | 406 km | national museum | 943 km |
| historic house museum | 436 km | railway museum | 921 km |

Local-history and religious museums are *about* their locality; aircraft,
dinosaurs and locomotives are globally shared subject matter. A nice detail: a
*heritage railway* (487 km) is a local institution, while a *railway museum*
(921 km) is an international genre.

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

## Corrections

**The stub finding does not replicate, and I had it backwards.** On the fixture,
museums with leads under 150 characters were 48.4% unlabelled against 38.2% for
the longest, and sat at the largest neighbourhood radius — I reported this as the
map's main quality risk. At full scale it is **flat**:

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

The likely reason the fixture said otherwise: at 2,000 museums the stubs are
sparse and scatter into noise, while at 49,218 there are enough of them to form
their own dense, nameable regions. Scale changed the answer.

It replicates a second time on `full_recovered`, whose stub tail is larger
(8,397 museums under 150 chars against 7,869) and differently composed: 55.4%
unlabelled for the shortest band against 57.4% for the longest, radius still
climbing monotonically 523 → 925 km. A correction that holds on two corpora with
different composition is worth more than one that holds on the corpus it was
derived from.

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
  end programmatically.
- **The residual 1.11x language effect** has not been chased down. The probe's
  cross-lingual retrieval test (parallel articles for the same museum) was never
  re-run at full scale; that is the clean way to settle it. It shrank rather than
  grew when the lead rule was fixed, so it is a lower priority than it looks.
- **The lead rule is national, the world is not.** A museum in Puerto Rico or
  Catalonia or Quebec gets its country's plurality language, not its own. Fixing
  it needs subnational data (`P131` is already fetched for the probe's gazetteer)
  and would matter most for exactly the regions a world map should not flatten.
