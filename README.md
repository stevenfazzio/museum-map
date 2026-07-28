# museum-map

A semantic map of every museum in the world that has a Wikipedia article —
**54,778 museums in 158 languages**, placed by what their article says about
them, with regions named at four zoom levels.

Getting to "every" took two channels. Wikidata types 49,218 of them as museums.
It types another **5,560 as houses and buildings** — 24% of US museums, because
an NRHP listing gets `instance of: house` and nobody adds the museum claim — and
those are recovered from the wikis' own museum category trees. See
[`COVERAGE.md`](COVERAGE.md).

The question behind it: is such a map a real thing, or is it just a choropleth
with a type filter? The answer is in [`FINDINGS.md`](FINDINGS.md). The short
version: **67.8% of these museums carry no museum type in Wikidata beyond the
generic "museum", and the map gives 19,277 of them a subject anyway** at the
22-region layer. The text knows what they are about; the metadata does not —
and the 5,560 recovered museums make that sharper, because Wikidata gives them
no type at all.

## Run it

```bash
uv sync

# 1. Fetch the corpus (network, ~2 h). Watch the logs; never pipe through tail.
uv run python -u pipeline/p01_harvest.py   > logs/p01_harvest.log 2>&1
uv run python -u pipeline/p02_sitelinks.py > logs/p02_sitelinks.log 2>&1
nohup uv run python -u pipeline/p03_leads.py --workers 4 > logs/p03_leads.log 2>&1 &

# 2. Build the map (compute, ~2 h at full scale)
./run.sh fixture          # 2,000 museums, ~10 min — iterate here first
./run.sh full_recovered   # all 54,778 — the real map
./run.sh full             # 49,218, Wikidata-typed only (the baseline)
```

The two extra corpus stages, needed once for `full_recovered`:

```bash
uv run python -u pipeline/p07_gap.py     > logs/p07_gap.log 2>&1
uv run python -u pipeline/p08_recover.py > logs/p08_recover.log 2>&1
```

Needs `ANTHROPIC_API_KEY` for region naming, tooltip summaries and p07's
classifier. Everything is resumable: HTTP responses are cached by request hash,
leads are written as per-wiki shards, embeddings checkpoint every 5,000 rows,
and p06/p10 fingerprint their inputs so a changed lead re-runs only its own row.

### What a full rebuild actually costs

`data/` is gitignored, so a clone has the stages and none of the artifacts.
Building `full_recovered` from nothing:

| stage | wall clock | money |
|---|---|---|
| `p01`–`p03` fetch the Wikidata-typed corpus | ~2 h | — |
| `p07_gap` crawl 30 wikis + classify | **~8 h** | **~$27** |
| `p08_recover` fetch and union the 5,560 | ~30 min | — |
| `run.sh full_recovered` (p10–p14) | ~2 h | ~$8 |
| `p06_summaries` tooltips | ~30 min | ~$10 |
| | **~13 h** | **~$45** |

`p07` is the expensive one and rarely needs re-running: its output
(`data/interim/gap/in_scope_qids.json`) changes only as Wikidata's typing does.
Its 8 hours are ~62,700 HTTP requests at the 2.5/s that WMF tolerates without
rate-limiting — network-bound, not compute-bound. Skip it and build `full`
instead if you only want the map, and accept that it is missing 24% of US
museums.

Output is a single self-contained `reports/map_<corpus>_<tag>.html` — pan, zoom,
search, and click a point to open its Wikipedia article. The map is
`reports/map_full_recovered_short.html`.

## Layout

| | |
|---|---|
| `museum_map/` | shared library: paths, cached/throttled HTTP, text processing, the centring transform |
| `pipeline/` | **the project.** p01–p05 build the corpus, p10–p14 build and analyse the map |
| `probe/` | historical. The go/no-go experiment that preceded the build — see below |
| `FINDINGS.md` | what the finished map shows |
| `COVERAGE.md` | which museums the corpus misses, and why |
| `reports/` | generated maps (gitignored — regenerable, and the full one is ~14 MB) |
| `data/` | everything fetched and computed (gitignored) |

### The pipeline

| stage | does | writes |
|---|---|---|
| `p01_harvest` | every museum Wikidata *types* as one, with ≥1 sitelink | `data/raw/museums.parquet` |
| `p02_sitelinks` | resolve real Wikipedia articles for all 55,280 | `data/interim/full/sitelinks.parquet` |
| `p03_leads` | fetch every article's lead, pick one per museum | `data/interim/full/leads{,_all}.parquet` |
| `p04_types` | one museum type per museum, from its P31s | `data/interim/full/types.parquet` |
| `p05_fixture` | 2,000-museum sample for fast iteration | `data/interim/fixture_leads.parquet` |
| `p07_gap` | museums Wikidata does not type as museums | `data/interim/gap/in_scope_qids.json` |
| `p08_recover` | fetch those, union into a corpus | `data/interim/full_recovered/leads.parquet` |
| `p10_embed` | BGE-M3, sequence capped at 2,048 tokens | `data/processed/map_<corpus>/emb.npy` |
| `p11_layout` | per-language centring → UMAP 2D | `coords.parquet` |
| `p12_topics` | Toponymy region names, all layers | `topics_<tag>.parquet` |
| `p13_map` | datamapplot interactive HTML | `reports/map_<corpus>_<tag>.html` |
| `p14_analyze` | is the map just country/type/language? | `analysis_<tag>.json` |

Every map stage takes `--corpus fixture|full|full_recovered` and is otherwise
identical between them, so nothing validated on the fixture can silently diverge
on the real run — and `full` stays buildable on its own as the baseline
FINDINGS.md's sensitivity comparison is measured against.

## Decisions worth knowing

**Museum definition — two channels, because one is not enough.**
`wdt:P31/wdt:P279* wd:Q33506` is the transitive form: the Louvre is an instance
of *art museum*, not of *museum*, so a plain `P31` match misses it. But the
transitive form still misses 5,560 museums Wikidata types as houses and
buildings with no museum claim at all, so `p07` adds a second channel — the
wikis' own museum category trees, with each article's text judged on whether it
describes a museum. `p01` trusts `P31`; `p07` trusts the prose.
[`COVERAGE.md`](COVERAGE.md) measures the gap between them.

**Which article represents a museum.** The lead comes from an official language
of the museum's country when that article is at least half as long as the longest
available; otherwise the longest wins. Plain longest-wins left 30.4% of museums
that *have* a local-language article represented by another one. The confound is
not language — BGE-M3 is cross-lingually aligned — but **perspective**: the
Spanish article on the Seoul Museum of Art leads with a Joseon royal palace, the
Korean one with its status as a bureau of the city government. Always preferring
the local article overcorrects, pushing sub-200-character leads from 18.4% to
23.7%.

**BGE-M3, not multilingual-e5-large.** Under e5, article language dominated
everything at ARI +0.769 and buried the actual content. BGE-M3 sits at +0.017.
This is the probe's single most valuable result.

**Geography is kept, not centred out.** Language entered through a sampling rule
and parallel articles gave an oracle to confirm its removal took the artefact
rather than the content. Location is constitutive — a local-history museum in
Bavaria *is* about Bavaria — and there is no "same museum, different place" to
validate a removal against.

**Per-language centring uses leave-one-out with shrinkage.** 28 of the 158
languages have exactly one museum; plain centring maps a singleton group onto the
origin, manufacturing a dense fake cluster at the centre of the map.

## The probe

`probe/` holds the go/no-go experiment that ran before any of this: on a
2,000-museum stratified sample, is the embedding space just a restatement of
country and type? It said no, and it is why the pipeline uses BGE-M3 and keeps
geography. Its reports are in `probe/reports/`.

It is **not** part of building the map and does not need to be run. Two of its
conclusions did not survive full scale — the stratified sample understated the
geographic signal by 2.7×, and its stub-quality finding reversed sign — both
documented in `FINDINGS.md`.

```bash
./probe/run_probe.sh    # needs data/raw/museums.parquet from p01_harvest
```
