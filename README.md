# museum-map — embedding-space probe

A go/no-go experiment, not a product. **Question:** if you embed the Wikipedia
lead of every museum in the world, is the resulting space just a restatement of
*country* and *museum type*? If so, a semantic map of museums has no subject —
a choropleth with a type filter would carry the same information.

Output: `reports/report.md` plus scatter figures in `reports/figs/`.

## Result

Tested with **two encoders** (`multilingual-e5-large` and `BAAI/bge-m3`), which
turned out to matter more than anything else.

### What replicates across both

- The map is **not** a restatement of country (ARI +0.076 / +0.016) or of museum
  type (−0.004 / −0.003). Neither is the organising axis.
- **Museum type is real, recoverable content.** The probe on specifically-typed
  museums reaches 0.54–0.57 against a 0.266 baseline. The project has a subject.
- **Geography is a gradient, not a partition** — which is why the country ARI
  missed it. It decomposes into a steep local effect that dies by ~1,000 km
  (+0.21 above mean similarity under 1 km, at the permutation null past
  ~3,000 km) and a flat national offset that never decays. Mantel r −0.116 /
  −0.119; the two encoders agree to within noise.
- That yields a **local↔universal axis** — median distance to a museum's 10
  nearest neighbours — which recovers the same unprompted ordering under both
  encoders: local, ethnographic and archaeological museums at one end; military,
  railway and natural-history at the other. Local-history museums are *about*
  their locality; wars, trains and dinosaurs are globally shared subject matter.

### What turned out to be an encoder artefact

The first run, on e5-large alone, found article **language** dominating
everything at ARI **+0.769** — an artefact of the "longest article across
languages" sampling rule. That conclusion does not survive the second encoder:

| | e5-large | BGE-M3 |
|---|---|---|
| language ARI, raw | **+0.769** | **+0.017** |
| language 10-NN purity, raw | 0.708 | 0.261 |
| cross-lingual retrieval P@1, raw | 0.854 | **0.941** |
| type-specific probe, raw | 0.274 | **0.513** |

**BGE-M3's space is already language-neutral** — it is trained for cross-lingual
alignment, and it shows. Type is recoverable in its raw space without any
correction at all, where e5 needed the language axis removed first to see it.

**So: use BGE-M3.** Per-language centring (`probe/debias.py:centered`) still adds
a little on top — cross-lingual P@1 0.941 → 0.966, language ARI +0.017 → −0.010 —
but it is no longer load-bearing. Under e5 it was the difference between a map of
Wikipedia language editions and a map of museums.

The centring transform is validated against ground truth rather than against a
clustering metric: 1,113 museums have articles in ≥2 languages, and the same
institution described twice should retrieve itself across languages. Judging a
de-biasing transform by "did language ARI fall" is circular.

Geography is deliberately **not** centred out. Language was a corpus artefact and
parallel articles gave an oracle to confirm the removal took the artefact rather
than the content. Location is constitutive of what a museum is, and there is no
"same museum, different place" to validate against.

Honest caveat on both encoders: post-centring HDBSCAN noise is ~40%, so the space
is smooth rather than clumpy. That is a description, not a problem — see
`NOTES.md`.

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
