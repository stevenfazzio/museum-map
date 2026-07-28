# Coverage — the museums the map does not contain

`FINDINGS.md` asks whether the map is a real thing. This asks a prior question:
**is the corpus the set of museums it claims to be?**

The corpus is whatever `wdt:P31/wdt:P279* wd:Q33506` returns. That is a claim
about Wikidata's typing, not about the world, and the README's "every museum in
the world that has a Wikipedia article" quietly assumes the two agree.

They do not, by about an eighth.

Data: `data/interim/gap/`. The list itself is `missing_museums.csv`.

## The headline

**5,560 museums have a Wikipedia article, sit in that wiki's museum category
tree, and are absent from the corpus** — 11.3% of the 49,218 on the map.

| | count | % of mapped |
|---|---|---|
| **in scope — strict `museum`, contamination removed** | **5,560** | **11.3%** |
| strict `museum`, majority across wikis | 5,862 | 11.9% |
| any language's article says museum | 6,353 | 12.9% |
| including `partly` (houses a museum) | 12,332 | 25.1% |
| `adjacent` (dealer gallery, aquarium, planetarium) | 2,268 | — |

The in-scope set is the strict set minus 232 preserved watercraft and 70 art
galleries, identified by `P31`. Some genuine museum ships are lost that way —
`HMS Djärv` really is a *museifartyg* at Marinmuseum — so the exclusions are
marked in the `scope` column of `missing_museums.csv` rather than deleted, and
the decision is reversible.

The strict/any estimators differ by 8% because 79% of candidates appear in only
one wiki, so the aggregation rule only moves a fifth of the data.

`adjacent` is excluded rather than folded in because `art gallery` (Q1007870),
`public aquarium` (Q2281788) and `planetarium` (Q148319) are **not** in the
Q33506 closure. The map never intended to include them; counting them as missing
would measure a different corpus than the one that exists.

**These museums have not been added to the map.** See *Integration* below.

## Why they are missing

Wikidata types them as buildings. Of the 5,560, **29% carry a `P31` of house,
building, palace, historic house, or architectural structure** and no museum
claim at all:

| what Wikidata calls them | n |
|---|---|
| house (Q3947) | 592 |
| building (Q41176) | 538 |
| architectural structure (Q811979) | 152 |
| museum building (Q24699794) | 123 |
| archaeological site (Q839954) | 114 |
| nonprofit organization (Q163740) | 97 |
| organization (Q43229) | 96 |
| historic site (Q1081138) | 71 |

The canonical case is
[Boothe Memorial Park and Museum](https://www.wikidata.org/wiki/Q4943925). Its
only `P31` is `house`. Its English lead opens "Boothe Memorial Park and Museum
sits on a 32-acre site in the Putney section of Stratford, Connecticut." The text
says museum; the structured data says house; `p01_harvest` reads the structured
data, so the museum never entered `museums.parquet`, never had a lead fetched,
and has no point on the map to find.

This is the same asymmetry `FINDINGS.md` is built on — the text knows what these
places are and the metadata does not — one stage earlier. The headline finding
concerns museums Wikidata *under-types*; this concerns museums it does not type
as museums at all, and `p01` is the one place that trusts `P31` completely.

## Where they are

| country | in map | missing | gap |
|---|---|---|---|
| **United States** | 5,494 | 1,752 | **24%** |
| **Australia** | 465 | 128 | **22%** |
| **Canada** | 760 | 142 | **16%** |
| Portugal | 554 | 84 | 13% |
| People's Republic of China | 1,306 | 166 | 11% |
| Germany | 4,613 | 388 | 8% |
| France | 2,418 | 177 | 7% |
| Spain | 1,957 | 141 | 7% |
| Sweden | 1,357 | 104 | 7% |
| United Kingdom | 2,660 | 137 | 5% |
| Russia | 1,777 | 93 | 5% |
| **Italy** | 4,740 | 105 | **2%** |
| **Japan** | 3,880 | 78 | **2%** |

**The gap is not uniform and it is not where I predicted.** It concentrates in
the anglophone settler-colonial countries and is near-absent in Italy and Japan.
The likely mechanism is heritage-designation registers: a US historic house
museum is listed on the National Register of Historic Places, acquires
`instance of: house` plus a heritage designation, and no editor adds the museum
claim. Italian and Japanese museums are typed as museums.

This under-represents the United States by a quarter, which is the corpus's
largest known bias. Rather than leave it as a caveat, the map was rebuilt as
`full_recovered` (54,778 museums) and every metric recomputed. Nothing moves:
country ARI stays at +0.002 at the finest layer, every delta within +/-0.002, and
10-NN country purity falls slightly once the chance baseline is controlled for.
The recovered museums arrive as subject regions rather than geographic ones.
See FINDINGS.md.

## Method

Read-only against `data/`. Everything network goes through
`museum_map.common.request_json`, so it is cached and a rerun is nearly free.
Scripts in `data/interim/gap/scripts/`.

**Scope: the top 30 wikis by corpus coverage**, which reach 96.2% of the 49,218.
The tail is 263 wikis contributing under 4% combined — below the measurement's
own error bar. 183 was never the right target.

**Per-wiki config is derived from Wikidata, not hand-written.** `Q33506` has
labels in 192 languages; its `P910` category `Q7139164` has sitelinks on 196
wikis, which give the root category (`Category:Museums`, `Kategorie:Museum`,
`Categoria:Musei`, `Category:博物館`, `تصنيف:متاحف`). Stems come from those
labels plus the major museum subclasses — Japanese needs both 博物館 and 美術館,
which share no characters — plus the root category title, which supplies the
plural. Arabic proves that last point: the label is متحف but the category is
متاحف, a broken plural containing none of the singular.

**Containment is the load-bearing rule.** Only descend into a category that is
itself museum-named. Without it, depth-12 traversal from `Category:Museums` walks
museum → its collection → the works in it → `National Register of Historic
Places` → `United States National Film Registry films` (749 articles), `Royal
Academicians` (594), `Psalms` (188). Blocklisting drift by name cannot anticipate
that a museum category eventually reaches the Psalms; requiring every step to
stay museum-named can. Containment cut the English crawl from 63,964 articles to
33,216 and left every genuine branch.

**Classification is one Haiku pass in every language**, with four labels:
`museum` / `partly` / `adjacent` / `not`. It replaced two hand-written regexes.
Those reached 90% precision but only 39–67% recall, because the hard cases are
judgement calls rather than lexical variants — a castle housing a museum, a
heritage railway, a coin cabinet. Two lighthouse leads are near-identical whether
or not one is a museum. Wikidata's short description is passed alongside the
lead; it is free, exists in every language, and sometimes carries the answer
outright (`Dizzy Dean Museum` → "Museum in Jackson, Mississippi").

**Aggregation is by QID, not by article.** A missing museum often has articles in
several trees. The duplication yields cross-wiki agreement free.

Cost: 184,782 articles crawled across 30 wikis, 48,333 classified, ~$27 in Haiku.

## Validation

Against hand-scored English samples, read individually:

| test | result |
|---|---|
| museums the regex missed, recovered | **7/7** |
| items judged clearly not museums, called `museum` | **0/18** |
| non-English sample (22, languages I read) | ~15 right, 2 wrong, 5 borderline |

Eight wikis — ru, uk, bg, ar, arz, he, hy, ka — have **no human validation**.
Their labels are purely classifier-derived. Given the geography they contribute
little, but the number is not the same kind of number as the English one.

## Corrections

Errors made and caught during this work, in the order they were made.

**A ratio from a contained subtree does not transfer to an uncontained one.**
Connecticut's subtree gave 21% of crawled articles surviving as genuine misses,
which extrapolated to ~12,000 globally. Wrong twice over: the global crawl was
contaminated by drift the CT subtree was too shallow to reach, and CT is unusually
dense in the failure mode. The measured answer is half that.

**A precision estimate has the same problem.** Hand-scoring 40 Connecticut items
gave 90% precision. On the global English set the same rule ran ~65%, because
Connecticut contains no commercial dealer galleries, no *Night at the Museum*, no
*Museum Madness* video game, and no Sheffield Museums Trust.

**A drift term that collides with the target vocabulary empties a wiki
silently.** `musei` was added to catch `museologia`; it is Italian for *museums*,
and pruned the entire Italian tree to 9 articles. There is now a guard that fails
loudly when any drift pattern matches a wiki's own museum stems, and a yield check
that flags a wiki returning fewer articles than the corpus already has for it.

**Two `P31` values supplied from memory were wrong.** `Q1091803` is the natural
number 335, not open-air museum; `Q184876` is "frame of reference", not
planetarium. They put `335`, `trecentotrentacinque`, 三百三十五 and
`bezugssystem` into 28 of the 30 derived configs. Printing the config for
inspection is what caught it. Every QID in the scripts is now looked up.

**Latin-script assumptions break on non-Latin wikis.** 50 titles per `pageprops`
GET is fine until Cyrillic, Arabic and Georgian percent-encode to 6–9 bytes per
character; ru, uk, bg, ar, arz, he, hy and ka all died on `414 URI Too Long`
while every Latin-script wiki passed. Fixed by switching to POST.

**"The recovered museums will skew short-lead" is false.** It was inferred from
their median sitelink count of 2, and used to argue the lead-vs-full-text
question should be settled first. Their median lead is 465 characters against the
corpus's 394 — longer at every percentile.

**"Smaller editing communities type museums worse" is false.** It was the stated
reason for treating English and German as the optimistic end. Italy sits at 2%,
Japan 2%, Poland 4%, Russia 5%, against 24% for the United States. The gap tracks
heritage-register practice, not community size.

**"Non-English precision is materially worse" was an artifact of my own sample.**
It came from hand-scoring a printout truncated to 140 characters when the
classifier read 700. `HMS Djärv` "är nu **museifartyg på Marinmuseum**", `U-10`
"est dorénavant **navire-musée**", the Scharkent mosque "wird **als Museum
genutzt**" — three of six alleged false positives were correct, judged on
evidence I had not read. Non-English precision is comparable to English.

**Cross-wiki disagreement is mostly not classifier error.** 896 QIDs are called
`museum` by one wiki and `not` by another. `Abbāsi House` is `museum` in English
("is a large historic house museum in Kashan") and `not` in Russian, Ukrainian,
Armenian and Persian — because each wiki was judged on *its own article's text*,
and those articles say different things. This is the same perspective effect the
README documents for the Seoul Museum of Art. It argues against majority vote as
the estimator; both are reported above.

## Integration

**Done.** The 5,560 are in the map: `--corpus full_recovered`, 54,778 museums,
`reports/map_full_recovered_short.html`. Two stages build them — `p07_gap`
(crawl and classify, hours and ~$27) and `p08_recover` (fetch and union) — so the
corpus is reproducible from a clean clone rather than resting on a one-off
analysis.

Integration waited on the sensitivity experiment rather than on nerve. Adding
these museums is not additive: `p11` UMAP, `p12` Toponymy and `p13` are full
recomputes, every point moves, and the region names change. Doing that before
knowing whether the conclusions survived would have meant rebuilding the
artifact FINDINGS.md describes without knowing whether FINDINGS.md would still
be true. It is (see FINDINGS.md), so the rebuild was safe to do.

`full` is deliberately still buildable on its own. It is the baseline the
comparison is measured against; `p08` never writes over it.

The reason to defer is that adding these museums is not additive. `p10` is
per-row fingerprinted so only new rows embed, but `p11` UMAP, `p12` Toponymy and
`p13` are full recomputes: every existing point moves and the region names
change. A 11.3% corpus change concentrated in one country and one museum type
will move the map, not extend it — and `FINDINGS.md`'s numbers would stop
matching the map they describe.

The recovered museums are thinner in *metadata* — 79% have coordinates, 83% an
English label, median sitelink count 2 — but not in prose. Their median lead is
**465 characters against the corpus's 394**, and only 15.3% fall under 200
characters against 23.9%. Few sitelinks does not mean a short article, which was
a prediction worth recording as wrong.

When it happens, the shape is a new stage rather than a change to `p01`:
`p01_harvest` stays a faithful Wikidata query, a recovery stage reads
`in_scope_qids.json`, and the corpus becomes their union with a `source` column.
That keeps the old corpus reproducible and lets both maps be compared.

## What is still open

- **The `partly` boundary is a real choice, not a rounding detail.** It is 6,470
  museums — larger than the strict count. A castle with a museum wing and a
  historic house museum are not obviously different in kind, and the corpus
  already contains heritage railways.
- **Museums whose only article is outside the top 30 wikis** are unmeasured.
- **Whether the excluded vessels should come back.** 232 preserved watercraft are
  out of scope, but some are genuine museum ships with an explicit claim in their
  lead. A `P31`-based rule cannot tell those apart; the text can.
- **The category tree is a second recall channel, not a replacement definition.**
  It finds museums Wikidata mistypes. It cannot find museums with no Wikipedia
  article at all, which is a different and larger question.
