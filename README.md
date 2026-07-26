# museum-map — embedding-space probe

A go/no-go experiment, not a product. **Question:** if you embed the Wikipedia
lead of every museum in the world, is the resulting space just a restatement of
*country* and *museum type*? If so, a semantic map of museums has no subject —
a choropleth with a type filter would carry the same information.

Output: `reports/report.md` plus scatter figures in `reports/figs/`.

## Result

**Neither.** Across 1,999 museums in 209 countries, HDBSCAN clusters match
country at ARI **+0.076** and museum type at **−0.004**. The map is not a
restatement of either.

But the axis that *does* dominate is an artefact of the corpus rather than a fact
about museums: **the language the article is written in**, at ARI **+0.769** and
70.8% 10-NN purity. Because the lead is taken from whichever Wikipedia had the
longest article, the embedding space is first of all a map of Wikipedia language
editions — and since language tracks country, part of the (secondary, real)
country signal is language wearing a country label. Stripping location entities
removes 36% of the country signal but only 2% of the language signal.

**The confound is removable, and cheaply.** 1,113 museums have articles in ≥2
languages, which gives a ground truth that owes nothing to any clustering metric:
the same institution described twice should retrieve itself across languages.
Per-language centroid subtraction (leave-one-out, shrunk toward the global mean)
takes that cross-lingual retrieval from P@1 **0.854 → 0.954**, cuts language
neighbour purity **0.421 → 0.098** (chance 0.041), and *raises* country purity
rather than destroying it. INLP suppresses language slightly harder but strips
543 of 1024 dimensions and takes country down with it, for worse retrieval.

**And with language centred out, the project turns out to have a subject.**
Re-running the full analysis on the centred map corpus:

| label | ARI vs clusters | linear probe (baseline) |
|---|---|---|
| language | +0.769 → **+0.007** | 0.567 → 0.137 *(0.175 — below baseline)* |
| country | +0.076 → +0.006 | 0.150 → **0.178** *(0.022)* |
| type, specifically-typed | −0.004 → **+0.049** | 0.274 → **0.542** *(0.266)* |

Language stops being linearly recoverable at all. Country survives and its probe
*improves* — it was real, not purely a language proxy. And museum type roughly
doubles from at-baseline to clearly predictable: it was in the embedding the
whole time, drowned out. The honest caveat is that HDBSCAN noise rises 7% → 41%,
so what remains is gradients rather than islands.

Do not restrict the corpus to English — it exists for only 48% of the sample and
re-introduces the anglophone bias the stratification was built to remove.

**Geography is present, but as a gradient, not a partition** — which is why the
country ARI missed it. Measured continuously over the 81.6% of museums carrying
coordinates, the relationship decomposes into two separable effects:

- a **steep local effect that dies by ~1,000 km**: museums within 1 km of each
  other sit +0.208 above the mean similarity, falling to +0.018 by 316–1,000 km
  and reaching the permutation null past ~3,000 km. This is *same-place-ness*,
  not continental culture.
- a **flat national effect that never decays**: same-country pairs stay ~+0.06
  above the mean whether they are 500 km or 5,000 km apart. Country is an offset,
  not a gradient.

That yields a **local↔universal axis** — the median distance to a museum's 10
nearest embedding neighbours — which recovers an unprompted and sensible
ordering: local (1,256 km), open-air (1,392) and archaeological (1,539) museums
at one end; military (4,151), railway (3,374) and natural history (3,244) at the
other. Local-history museums are *about* their locality; wars, trains and
dinosaurs are globally shared subject matter.

Geography is deliberately **not** centred out. Language was a corpus artefact of
the "longest article" sampling rule, and parallel articles gave an oracle to
confirm the removal took the artefact rather than the content. Location is
constitutive of what a museum is, and there is no "same museum, different place"
to validate against — so a geographic residualisation could not be distinguished
from having gutted the space.

## Run

```bash
uv sync
./run_all.sh
# or a different encoder:
MODEL=BAAI/bge-m3 ./run_all.sh
```

Every HTTP response (SPARQL, Wikipedia, Wikibase) is cached to `data/cache/`
keyed by a hash of the full request, so reruns are free and the experiment
reproduces offline once the cache is warm. `random_state=42` throughout,
including UMAP.

## Pipeline

| stage | does | writes |
|---|---|---|
| `s01_harvest` | every museum in Wikidata with ≥1 sitelink | `data/raw/museums.parquet` |
| `s02_sample` | sqrt-of-population allocation per country, oversampled | `data/interim/candidates.parquet` |
| `s03_sitelinks` | resolve real Wikipedia articles per candidate | `data/interim/sitelinks.parquet` |
| `s04_finalize` | exact 2,000; assign one type label each | `data/interim/sample.parquet` |
| `s05_leads` | longest lead across all languages | `data/interim/leads{,_all}.parquet` |
| `s06_variants` | the three text variants | `data/interim/variants.parquet` |
| `s07_embed` | multilingual encoder, 3 × 2,000 vectors | `data/processed/emb_*.npy` |
| `s08_analyze` | UMAP + HDBSCAN + metrics | `data/processed/metrics_*.json` |
| `s10_parallel` | cross-lingual retrieval on same-museum article pairs; raw vs centered vs INLP | `data/processed/parallel_*.json` |
| `s11_geography` | distance-decay curve vs a permutation null; local↔universal radius per museum | `data/processed/geo_*.json`, `geo_scores_*.parquet` |
| `s09_report` | figures + markdown (runs last) | `reports/` |

## Decisions worth knowing

**Museum definition.** `wdt:P31/wdt:P279* wd:Q33506` — the transitive form. The
Louvre is an instance of *art museum*, not of *museum*, so a plain `P31` match
misses it (verified: `ASK { wd:Q19675 wdt:P31 wd:Q33506 }` → false).

**Why the harvest is partitioned by type.** WDQS gives a query ~60s. An
unpartitioned paged query times out (`GROUP BY` + deep `OFFSET` forces a full
sort of ~81k rows); partitioning by country works but re-walks the `P279*`
closure ~200 times; inlining the 371 subclasses as `VALUES` is worse still.
Resolving the closure once and issuing one plain `wdt:P31` lookup per type, with
no `ORDER BY` and no `OFFSET`, returns even the largest bucket (Q33506, 32.5k
rows) in ~38s. Partitions that hit the row cap split recursively over QID ranges.

**Stratification.** Allocation ∝ `sqrt(n_country)`: flattens the head
(Italy/Germany/US ≈ 30% of all museums) without giving Vatican City the same
weight as Germany.

**Longest lead, any language.** Length is measured in characters, which is not
script-neutral — CJK articles are systematically under-selected. The chosen
language is stored with the text and reported.

**Variant (c).** Locations are removed with a per-museum gazetteer (every label
and alias, in every language, of the country and the full `P131` containment
chain, plus `P1549` demonyms) *and* spaCy `xx_ent_wiki_sm` LOC spans. The NER
also tags institution names as `LOC`, so (c) removes much of the museum's own
name too; the report measures how often.

**Metrics.** ARI against country and type is reported as asked, but it compares
partitions and is penalised when ~30 clusters meet ~200 countries. 10-NN label
purity (against `sum p_i^2` chance) and a cross-validated linear probe (against
the majority baseline) are reported next to it — those answer "is the
neighbourhood geographic?" without a clustering step in between.

**Judging the language fix.** "Language ARI dropped" cannot validate a
de-biasing transform — subtract the language means and the clusters loosen by
construction. `s10_parallel` uses museums that have articles in several
languages as ground truth instead: if the representation is language-neutral,
the same museum's German and Japanese articles should retrieve each other. That
verdict is independent of any clustering metric. It is also split by whether the
museum's name literally appears in both texts, to rule out string matching.

**Two labels added after the first run,** because the numbers as first specified
could not be interpreted:
- *language of the lead*, without which the country signal is unattributable
  (and which turned out to dominate everything).
- *type among specifically-typed museums only*. 62% of the sample carries just
  the generic `museum` P31, so the all-museums type probe scores exactly the
  majority baseline — that reads as "no signal" no matter what the embedding
  contains.

**Figures.** Only four hues of the categorical palette clear the all-pairs
CVD/normal-vision floors that a scatter demands, so the primary figure per
variant is a small-multiple grid (all points grey, one category highlighted per
panel) where colour carries no identity. The literal single-panel coloured
scatter is emitted alongside it.
