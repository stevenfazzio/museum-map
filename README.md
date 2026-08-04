# museum-map

A semantic map of every museum in the world that has a Wikipedia article —
**54,778 museums in 158 languages**, placed by what their article says about
them, with regions named at five zoom levels.

**[Open the map](https://stevenfazzio.com/museum-map/)** (9 MB, desktop).

Museums that sit near each other are about similar things, so the map is a way to
find museums like one you already know, and to see what kinds of museum exist at
all. Its 1,167 region names are the vocabulary for that: *Sardinian Nuragic
Bronze Age Sites*, *Historic One-Room Schoolhouses*, *Wine, Beer and Chocolate
Heritage*, *Japanese Prefectural Art and History*. Pick any point to see what it
is and open its article.

The reason it can do that is in [`FINDINGS.md`](FINDINGS.md). The short version:
**67.8% of these museums carry no useful museum type in Wikidata — just the
generic "museum", or nothing in the common types at all — and 19,277 of them
still land in a named subject region** at the 22-region layer. You cannot filter
your way to those museums in Wikidata, because the structured data does not know
what they are about. The text does.

Getting to "every" took two channels. Wikidata types 49,218 of them as museums.
It types another **5,560 as houses and buildings** — 24% of US museums, because
an NRHP listing gets `instance of: house` and nobody adds the museum claim — and
those are recovered from the wikis' own museum category trees. See
[`COVERAGE.md`](COVERAGE.md).

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
./run.sh full             # 49,218, the Wikidata-typed corpus on its own
```

The two extra corpus stages, needed once for `full_recovered`:

```bash
uv run python -u pipeline/p07_gap.py     > logs/p07_gap.log 2>&1
uv run python -u pipeline/p08_recover.py > logs/p08_recover.log 2>&1
```

datamapplot is pinned to a commit rather than a release, because the last one
(0.7.3) predates both the touch tap-to-inspect card and the scroll zoom speed
the map sets; `pyproject.toml` says which commit and why.

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
| `run.sh full_recovered` (p09–p14) | ~2 h | ~$8 |
| `p06_summaries` tooltips | ~30 min | ~$10 |
| | **~13 h** | **~$45** |

`p07` is the expensive one and rarely needs re-running: its output
(`data/interim/gap/in_scope_qids.json`) changes only as Wikidata's typing does.
Its 8 hours are ~62,700 HTTP requests at the 2.5/s that WMF tolerates without
rate-limiting — network-bound, not compute-bound. Skip it and build `full`
instead if you only want the map, and accept that it is missing 24% of US
museums.

Output is a single self-contained `reports/map_<corpus>_<tag>.html` — pan, zoom,
search, and pick a point to see what it is and open its Wikipedia article. The map
is `reports/map_full_recovered_short.html`, published at
[stevenfazzio.com/museum-map](https://stevenfazzio.com/museum-map/).

`reports/` is gitignored, so the published copy lives on an orphan `gh-pages`
branch holding nothing but that file as `index.html`. Building it with plumbing
keeps the 13 MB blob out of `main`'s history and out of the working tree, and
replacing the branch rather than committing onto it keeps the site one commit
deep however many times it is rebuilt:

```bash
BLOB=$(git hash-object -w reports/map_full_recovered_short.html)
EMPTY=$(printf '' | git hash-object -w --stdin)
TREE=$(printf '100644 blob %s\tindex.html\n100644 blob %s\t.nojekyll\n' "$BLOB" "$EMPTY" | git mktree)
git branch -f gh-pages "$(git commit-tree "$TREE" -m 'Publish the map')"
git push -f origin gh-pages
```

`.nojekyll` stops Pages running the file through Jekyll. Pages serves it gzipped
at 9.3 MB.

**Best on desktop.** Tapping a point opens a card carrying the summary, the
Wikidata facts and a button through to the article, so a phone is no longer shut
out of the thing the map is for. It is still not a phone-first page: datamapplot
emits no viewport meta tag, so a phone lays the document out at desktop width and
scales it down, which leaves the controls small until you pinch. That is the open
half of
[datamapplot#200](https://github.com/TutteInstitute/datamapplot/issues/200).

Point size is how many wikis and sister projects link a museum, log-scaled over a
3x range — a rough proxy for how well known it is, and the only field in the
corpus whose coverage is not skewed by which country a museum is in.

The palette control recolours by country, article language, founding era,
declared Wikidata type or prominence, and opens on region. Sparse fields are
bucketed with an explicit *not recorded* colour rather than ramped, because
Wikidata coverage tracks how thorough a country's editors have been and a
continuous scale would draw that as if it were geography. See `p09_facts.py`.

The nearby control takes a city and a radius and filters to the museums inside
it. Points are placed by subject rather than by location, so the result scatters
across the whole map, and that shape is what a city's museums are about. It
intersects with the search box, so a radius around Kyoto plus a search for *art*
narrows to both. Each city carries the state or région containing it, which is
what tells Portland, Oregon from Portland, Maine, and typing a region or country
name reaches the cities inside it. 12.8% of museums have no coordinate in
Wikidata and can never appear in a radius result; the control says so under the
count.

## Layout

| | |
|---|---|
| `museum_map/` | shared library: paths, cached/throttled HTTP, text processing, the centring transform, the nearby control |
| `pipeline/` | **the project.** p01–p08 build the corpus, p09–p14 build and analyse the map |
| `FINDINGS.md` | what the finished map shows |
| `COVERAGE.md` | which museums the corpus misses, and why |
| `reports/` | generated maps (gitignored — regenerable, and the full one is ~13 MB) |
| `data/` | everything fetched and computed (gitignored) |

### The pipeline

| stage | does | writes |
|---|---|---|
| `p01_harvest` | every museum Wikidata *types* as one, with ≥1 sitelink | `data/raw/museums.parquet` |
| `p02_sitelinks` | resolve real Wikipedia articles for all 55,280 | `data/interim/full/sitelinks.parquet` |
| `p03_leads` | fetch every article's lead, pick one per museum | `data/interim/full/leads{,_all}.parquet` |
| `p04_types` | one museum type per museum, from its P31s | `data/interim/full/types.parquet` |
| `p05_fixture` | 2,000-museum sample for fast iteration | `data/interim/fixture_leads.parquet` |
| `p06_summaries` | one-sentence English summary of each lead | `map_<corpus>/summaries.parquet` |
| `p07_gap` | museums Wikidata does not type as museums | `data/interim/gap/in_scope_qids.json` |
| `p08_recover` | fetch those, union into a corpus | `data/interim/full_recovered/leads.parquet` |
| `p09_facts` | the Wikidata fields the hover card can use, and the settlements behind the nearby control | `map_<corpus>/{facts,places}.parquet` |
| `p10_embed` | BGE-M3, sequence capped at 2,048 tokens | `data/processed/map_<corpus>/emb.npy` |
| `p11_layout` | per-language centring → UMAP 2D | `coords.parquet` |
| `p12_topics` | Toponymy region names, all layers | `topics_<tag>.parquet` |
| `p13_map` | datamapplot interactive HTML | `reports/map_<corpus>_<tag>.html` |
| `p14_analyze` | how the map is organised: ARI, purity, radius by type | `analysis_<tag>.json` |

Every map stage takes `--corpus fixture|full|full_recovered` and is otherwise
identical between them, so nothing validated on the fixture can silently diverge
on the real run. `full` is not only a baseline: `p07` and `p08` read its leads as
their input, so it is a real intermediate stage on the way to `full_recovered`.

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

**BGE-M3, not multilingual-e5-large.** The single most consequential choice here.
Under e5, article language dominated everything at ARI +0.769 and buried the
actual content; BGE-M3 sits at +0.017. A map built on the wrong encoder would
have grouped museums by what language described them.

**Geography is kept, not centred out.** Language entered through a sampling rule
and parallel articles gave an oracle to confirm its removal took the artefact
rather than the content. Location is constitutive — a local-history museum in
Bavaria *is* about Bavaria — and there is no "same museum, different place" to
validate a removal against.

**Per-language centring uses leave-one-out with shrinkage.** 28 of the 158
languages have exactly one museum; plain centring maps a singleton group onto the
origin, manufacturing a dense fake cluster at the centre of the map.
