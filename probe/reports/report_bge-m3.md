# Does country or museum type already explain the embedding space?

> **Short answer: neither — but article *language* does, and that is a confound
> introduced by the sampling rule rather than a fact about museums.**

A go/no-go probe for the museum map: if the embedding of a museum's Wikipedia
lead is mostly a proxy for *where it is* and *what kind of museum it is*, then a
semantic map adds nothing over a choropleth with a type filter.

**Model:** `BAAI/bge-m3` · **UMAP:** 10D for clustering, 2D for display,
`random_state=42` · **Clustering:** HDBSCAN (`min_cluster_size=15`,
`min_samples=5`)

## Verdict

Headline numbers, full lead (variant a), 1999 museums.

| label | do clusters equal it? (ARI) | do 10 neighbours share it? | chance | lift | linear probe | baseline |
|---|---|---|---|---|---|---|
| **language of the lead** | **+0.017** | **26.1%** | 5.9% | **4x** | 39.4% | 17.5% |
| country | +0.016 | 19.1% | 0.7% | 26x | 17.9% | 2.2% |
| type (all) | +0.001 | 48.7% | 40.9% | 1.2x | 63.5% | 62.5% |

Read the **ARI** and **purity** columns, not the lift column, when comparing rows
against each other. Lift is purity ÷ chance, and chance depends on how many
categories the label has (209 countries vs
104 languages), so country's larger lift only says
country is far from *its own* much lower chance floor — it does not make country
the stronger axis.

**No single metadata field explains the cluster structure.** The best of them, the language the article is written in, reaches only ARI +0.017.

**Country is real but secondary, and partly a language proxy.** Neighbour purity
is 19.1% against 0.7% chance (26x), yet
silhouette is ~0 (-0.018) and ARI only +0.016:
country information is present and distributed, not the shape of the space. Because the
lead is taken from whichever Wikipedia had the longest article, and language tracks
country closely, an unknown part of that 26x is language wearing a country
label.

Stripping locations removes **58%** of the country signal, so most of it rides on explicit place names — addressable by preprocessing.

**The opening sentence carries a large share of both effects.** Removing just the
first sentence (variant b) drops language ARI from +0.017 to
+0.007 and country neighbour purity from 19.1% to
9.1%. Wikipedia's opening line is highly formulaic and
its template differs per language edition, so it encodes both "what language is
this" and "where is this" more strongly than the rest of the lead.

Museum type is close to absent: ARI **+0.001**, and even among the 563 specifically-typed museums the linear probe reaches **51.3%** against a **26.6%** baseline. Neighbourhoods are mildly type-ish (39.9% vs 12.0% chance) but type is nowhere near an organising axis.

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
951 of 1999 museums
(48%), so it halves the sample and
re-introduces exactly the anglophone bias the stratification was built to remove.

## Can language just be subtracted out?

Judging a de-biasing transform by "did language ARI fall" is circular — subtract
the language means and the language clusters loosen by construction. It says
nothing about whether the *museum* survived the surgery.

So this uses a ground truth that owes nothing to any clustering metric.
**1,113 of the 1,999 museums have articles in
two or more languages** — the same institution, described twice, independently.
If a representation is language-neutral, those two articles should find each
other.

- **query**: one article · **pool**: all 6,885 articles, same-language
  distractors included, because their crowding is the effect being measured
- **correct**: any other article about the same museum (necessarily another language)
- **crowding**: of the articles outranking the true match, what share are in the
  query's own language — the direct read on "language is in the way"

| representation | P@1 | R@10 | MRR | crowding | language 10-NN | country 10-NN |
|---|---|---|---|---|---|---|
| raw | 0.941 | 0.984 | 0.958 | 0.71 | 0.150 | 0.665 |
| per-language centered | 0.966 | 0.993 | 0.976 | 0.48 | 0.080 | 0.658 |
| INLP (543/1024 dims removed) | 0.851 | 0.924 | 0.878 | 0.10 | 0.048 | 0.326 |

(chance for language 10-NN is 0.041; for country
0.008)

**Centring works, and better than the clustering numbers suggested.** Per-language
centroid subtraction takes cross-lingual P@1 from 0.941 to
**0.966** (+3%), drops language neighbour purity from
0.150 to 0.080 against a
0.041 floor, and *raises* country purity
(0.665 → 0.658) rather than
destroying it. Same-language crowding falls from 0.71
to 0.48.

**INLP over-corrects.** It suppresses language hardest
(0.048, nearly the 0.041
floor) but strips 543 of 1024 dimensions and
takes country purity down with it
(0.665 → 0.326), for *worse*
retrieval than centring. Its own trace shows why: linear language accuracy
collapses from 0.565 to
0.150 after a single projection and then plateaus —
iterations 2 and 3 remove hundreds more dimensions for no further gain. One
iteration would have been the right stopping point.

### Is this just matching the museum's name?

The same museum's articles tend to repeat its proper name verbatim, so retrieval
could be string matching wearing a semantic costume. Splitting the queries by
whether the museum's Wikidata label appears in both articles:

| representation | P@1, name in both | P@1, name absent | gap |
|---|---|---|---|
| raw | 0.950 | 0.937 | +0.013 |
| per-language centered | 0.983 | 0.959 | +0.025 |
| INLP | 0.897 | 0.831 | +0.065 |

The gap is small: even with no shared name string, centred P@1 is
0.959 across 4,171 queries. The
cross-lingual signal is real content, not surface overlap. (Conservative
caveat: "name absent" only checks the *English* label verbatim — a translated or
transliterated form of the name could still be present in both texts.)

![language dissolving](figs/bge-m3_language_dissolve.png)

In the bottom row every language covers the whole cloud — but so does everything
else. INLP does not so much mix the languages as flatten the space into a ball;
that is what removing 543 of 1024
dimensions looks like, and it is why its retrieval is worse than centring's
despite the better language score.

**One caveat on comparing these numbers to the tables above.** This section runs
on a different corpus: 6,885 articles including *several languages
per museum*, where the main analysis uses one article per museum. Same-museum
articles in different languages attract each other, so the language effect is
weaker here by construction — raw language 10-NN purity is
0.150 in this corpus versus
0.261 in the map corpus.
The raw-vs-centred-vs-INLP comparison is internally valid; the absolute purity
values are not interchangeable between sections.

## What survives once language is centred out

Applying the winning transform to the map corpus itself — per-language centring,
centroids estimated within these 1,999 museums — and re-running the whole
analysis.

| label | ARI vs clusters | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|
| language of the lead | +0.017 → **-0.010** | 0.261 → **0.132** | 0.059 | 0.394 → **0.130** | 0.175 |
| country | +0.016 → **+0.007** | 0.191 → **0.140** | 0.007 | 0.179 → **0.139** | 0.022 |
| type (all) | +0.001 → **+0.043** | 0.487 → **0.477** | 0.409 | 0.635 → **0.640** | 0.625 |
| type (specifically-typed, n=563) | +0.032 → **+0.105** | 0.399 → **0.433** | 0.120 | 0.513 → **0.568** | 0.266 |

**Language is gone.** ARI +0.017 → -0.010,
and the linear probe falls to 0.130 — *below* its
own 0.175 majority baseline, i.e. no longer
linearly recoverable at all.

**Country survives, and is confirmed as real rather than a language proxy.** Its
probe accuracy actually *rises*, 0.179 →
0.139 against a
0.022 baseline, because removing the dominant
language direction makes the weaker country direction easier for a linear model
to reach. Its neighbourhood purity drops
(0.191 → 0.140) — that
part *was* language wearing a country label — but ARI stays near zero throughout:
country is present and distributed, never the shape of the space.

**And museum type comes out from under it.** This is the result that changes the
project's answer. Among specifically-typed museums the probe goes
0.513 → **0.568** against a
0.266 baseline — a 1.1x jump, from
indistinguishable-from-guessing to genuinely predictable. Neighbourhood purity
rises 0.399 → 0.433 (chance
0.120), and type becomes the label best aligned with the cluster
structure (type, ARI +0.043). Type was in the embedding the whole
time; language was drowning it.

One honest caveat: HDBSCAN's noise fraction jumps from
41% to 40%. Centring removes the
easy, dominant partition and what remains is a flatter, less clumpy space. The
structure that survives is real but weaker — a map of it will look like gradients,
not islands.

![centered, by type](figs/bge-m3_centered_type_facets.png)

![centered, by language](figs/bge-m3_centered_language_facets.png)

## Geography: the continuous version of the question

Country ARI came out near zero, which reads as "geography is not in the
embedding". That was the wrong instrument rather than the right answer — ARI
compares *partitions*, and geography is a gradient. Measured continuously against
the 1,632 museums that carry `P625` coordinates
(81.6% of the sample), it is emphatically present.

Correlation between log great-circle distance and embedding similarity (negative
= farther apart means less alike): raw **r = -0.125**
(z = -10 against a shuffled-coordinate null), language-centred
**r = -0.119** (z = -118).

### The decay is local, and it stops

| distance (km) | pairs | similarity above global mean | same-country only | pairs |
|---|---|---|---|---|
| 0–1 | 227 | **+0.222** | +0.226 | 195 |
| 1–3 | 270 | **+0.179** | +0.178 | 243 |
| 3–10 | 367 | **+0.159** | +0.163 | 343 |
| 10–32 | 517 | **+0.091** | +0.097 | 444 |
| 32–100 | 2,029 | **+0.065** | +0.073 | 1,249 |
| 100–316 | 12,289 | **+0.040** | +0.061 | 3,337 |
| 316–1,000 | 80,344 | **+0.018** | +0.059 | 3,120 |
| 1,000–3,162 | 277,866 | **+0.007** | +0.065 | 1,110 |
| 3,162–10,000 | 650,644 | **-0.005** | +0.060 | 227 |
| 10,000–20,100 | 306,343 | **-0.004** | — | 17 |

![distance decay](figs/bge-m3_distance_decay.png)

Two separable effects fall out of that table, and they are not the same thing:

1. **A steep local effect that dies by ~1,000 km.** Museums within a kilometre of
   each other sit **+0.222**
   above the global mean; by 316–1,000 km it is down to
   +0.018, and beyond
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
2,619 km against a
6,589 km random-pair baseline
(0.40x).

![neighbourhood radius by type](figs/bge-m3_radius_by_type.png)

The ordering is not something the method was told: most locally rooted are
**local museum** (1,624 km), **ethnographic museum** (1,781 km), **archaeological museum** (1,829 km); most internationally legible are **railway museum** (4,022 km), **military museum** (3,990 km), **natural history museum** (3,393 km). Local-history and open-air
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
3,120–3,337 same-country
pairs in the mid-distance bins and very few past 3,000 km, so the flat national
effect is measured on thin data at the long end. Reading it as "roughly constant"
is safe; reading exact values per bin is not.

## How to read this

`ARI` compares two *partitions*, so ~32 HDBSCAN clusters
against 209 countries is penalised for cardinality
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

1999 museums, stratified by country with allocation
proportional to `sqrt(n_country)` — the raw Wikidata distribution is Italy 8.9k /
Germany 8.5k / US 7.0k, which a uniform draw would reproduce.

Lead text is the **longest** available article across all Wikipedia languages,
not English by default. Selected-language mix: `en` 335, `es` 209, `de` 146, `fr` 139, `ar` 86, `ru` 85, `nl` 65, `pt` 49, `sv` 46, `it` 39, `cs` 33, `uk` 32.

Note that "longest in characters" is not script-neutral — the same content is far
shorter in Japanese or Chinese than in German — so CJK articles are
systematically under-selected.

### Lead length

| stat | chars |
|---|---|
| mean | 713 |
| p10 | 153 |
| p25 | 274 |
| median | 527 |
| p75 | 936 |
| p90 | 1501 |
| max | 8251 |

![lead lengths](figs/bge-m3_lead_lengths.png)

### Location stripping (variant c)

Gazetteer built per museum from every label and alias, in every language, of its
country and its full `P131` containment chain, plus demonyms (`P1549`); combined
with spaCy `xx_ent_wiki_sm` LOC spans.

- mean characters removed: **16.8%** (median 13.3%)
- leads where the museum's own name was also removed: **26.9%**

That last number matters: multilingual NER tags institution names as `LOC`
("Louvre" → LOC), so variant (c) is in practice *geography and much of the
institution's proper name* removed, which makes it a stricter test than intended.

## Results — each variant on its own usable rows

The faithful per-variant read. Variant (b) has a smaller `n` because
23% of leads are a single sentence, leaving nothing behind once it
is removed.

**vs language of the lead** (104 languages)

| variant | n | clusters | noise | ARI | AMI | silhouette (cosine) | silhouette (2D) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 1999 | 32 | 41% | +0.017 | +0.191 | -0.123 | -0.695 | 0.261 | 0.059 | 0.394 | 0.175 |
| (b) first sentence removed | 1530 | 23 | 38% | +0.007 | +0.085 | -0.122 | -0.733 | 0.210 | 0.071 | 0.353 | 0.205 |
| (c) locations stripped | 1992 | 28 | 31% | +0.038 | +0.196 | -0.095 | -0.668 | 0.324 | 0.059 | 0.437 | 0.175 |

**vs country** (209 countries)

| variant | n | clusters | noise | ARI | AMI | silhouette (cosine) | silhouette (2D) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 1999 | 32 | 41% | +0.016 | +0.239 | -0.018 | -0.487 | 0.191 | 0.007 | 0.179 | 0.022 |
| (b) first sentence removed | 1530 | 23 | 38% | +0.009 | +0.121 | -0.089 | -0.681 | 0.091 | 0.008 | 0.128 | 0.027 |
| (c) locations stripped | 1992 | 28 | 31% | +0.011 | +0.132 | -0.110 | -0.604 | 0.079 | 0.007 | 0.136 | 0.022 |

**vs type** (16 types, incl. the generic bucket)

| variant | n | clusters | noise | ARI | AMI | silhouette (cosine) | silhouette (2D) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 1999 | 32 | 41% | +0.001 | +0.086 | -0.043 | -0.345 | 0.487 | 0.409 | 0.635 | 0.625 |
| (b) first sentence removed | 1530 | 23 | 38% | -0.007 | +0.062 | -0.043 | -0.286 | 0.460 | 0.389 | 0.610 | 0.608 |
| (c) locations stripped | 1992 | 28 | 31% | +0.017 | +0.104 | -0.055 | -0.278 | 0.493 | 0.410 | 0.639 | 0.626 |

**vs type, specifically-typed museums only** (generic `museum` and `other` dropped — with 62% of the sample in one bucket the table above is a majority-class artefact)

| variant | n | types | ARI | AMI | silhouette (cosine) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 563 | 14 | +0.032 | +0.209 | +0.009 | 0.399 | 0.120 | 0.513 | 0.266 |
| (b) first sentence removed | 454 | 14 | +0.038 | +0.160 | -0.002 | 0.316 | 0.117 | 0.390 | 0.256 |
| (c) locations stripped | 560 | 14 | +0.100 | +0.257 | +0.002 | 0.376 | 0.120 | 0.500 | 0.268 |

## Results — common subset (identical museums in all three variants)

Restricting all three to the same museums makes the numbers directly comparable,
at the cost of skewing long: dropping the single-sentence leads removes the
shortest stubs.

**vs language of the lead** (82 languages)

| variant | n | clusters | noise | ARI | AMI | silhouette (cosine) | silhouette (2D) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 1524 | 23 | 39% | +0.001 | +0.126 | -0.119 | -0.696 | 0.240 | 0.072 | 0.375 | 0.205 |
| (b) first sentence removed | 1524 | 24 | 36% | -0.001 | +0.078 | -0.122 | -0.727 | 0.210 | 0.072 | 0.354 | 0.205 |
| (c) locations stripped | 1524 | 23 | 36% | +0.022 | +0.157 | -0.096 | -0.630 | 0.321 | 0.072 | 0.435 | 0.205 |

**vs country** (204 countries)

| variant | n | clusters | noise | ARI | AMI | silhouette (cosine) | silhouette (2D) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 1524 | 23 | 39% | +0.017 | +0.224 | -0.022 | -0.495 | 0.176 | 0.008 | 0.184 | 0.027 |
| (b) first sentence removed | 1524 | 24 | 36% | +0.009 | +0.117 | -0.089 | -0.668 | 0.091 | 0.008 | 0.124 | 0.027 |
| (c) locations stripped | 1524 | 23 | 36% | +0.009 | +0.116 | -0.122 | -0.655 | 0.074 | 0.008 | 0.130 | 0.027 |

**vs type** (16 types, incl. the generic bucket)

| variant | n | clusters | noise | ARI | AMI | silhouette (cosine) | silhouette (2D) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 1524 | 23 | 39% | +0.012 | +0.087 | -0.044 | -0.323 | 0.456 | 0.390 | 0.610 | 0.609 |
| (b) first sentence removed | 1524 | 24 | 36% | +0.004 | +0.068 | -0.043 | -0.288 | 0.461 | 0.390 | 0.610 | 0.609 |
| (c) locations stripped | 1524 | 23 | 36% | +0.029 | +0.104 | -0.058 | -0.288 | 0.455 | 0.390 | 0.614 | 0.609 |

**vs type, specifically-typed museums only** (generic `museum` and `other` dropped — with 62% of the sample in one bucket the table above is a majority-class artefact)

| variant | n | types | ARI | AMI | silhouette (cosine) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 451 | 14 | +0.080 | +0.222 | +0.009 | 0.385 | 0.117 | 0.488 | 0.257 |
| (b) first sentence removed | 451 | 14 | +0.066 | +0.168 | -0.002 | 0.316 | 0.117 | 0.417 | 0.257 |
| (c) locations stripped | 451 | 14 | +0.105 | +0.268 | +0.001 | 0.367 | 0.117 | 0.481 | 0.257 |

## Results — common subset, shortest length quartile dropped

Cut at 274 characters.

**vs language of the lead** (81 languages)

| variant | n | clusters | noise | ARI | AMI | silhouette (cosine) | silhouette (2D) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 1299 | 20 | 38% | +0.021 | +0.141 | -0.115 | -0.682 | 0.230 | 0.071 | 0.362 | 0.205 |
| (b) first sentence removed | 1299 | 18 | 45% | +0.001 | +0.100 | -0.121 | -0.689 | 0.210 | 0.071 | 0.349 | 0.205 |
| (c) locations stripped | 1299 | 2 | 4% | +0.004 | +0.007 | -0.101 | -0.634 | 0.311 | 0.071 | 0.418 | 0.205 |

**vs country** (201 countries)

| variant | n | clusters | noise | ARI | AMI | silhouette (cosine) | silhouette (2D) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 1299 | 20 | 38% | +0.025 | +0.253 | -0.031 | -0.509 | 0.168 | 0.008 | 0.156 | 0.032 |
| (b) first sentence removed | 1299 | 18 | 45% | +0.009 | +0.133 | -0.087 | -0.641 | 0.099 | 0.008 | 0.116 | 0.032 |
| (c) locations stripped | 1299 | 2 | 4% | -0.000 | +0.000 | -0.144 | -0.645 | 0.073 | 0.008 | 0.107 | 0.032 |

**vs type** (16 types, incl. the generic bucket)

| variant | n | clusters | noise | ARI | AMI | silhouette (cosine) | silhouette (2D) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 1299 | 20 | 38% | +0.010 | +0.089 | -0.044 | -0.314 | 0.442 | 0.376 | 0.604 | 0.597 |
| (b) first sentence removed | 1299 | 18 | 45% | -0.001 | +0.062 | -0.045 | -0.303 | 0.439 | 0.376 | 0.599 | 0.597 |
| (c) locations stripped | 1299 | 2 | 4% | -0.008 | +0.014 | -0.058 | -0.296 | 0.427 | 0.376 | 0.604 | 0.597 |

**vs type, specifically-typed museums only** (generic `museum` and `other` dropped — with 62% of the sample in one bucket the table above is a majority-class artefact)

| variant | n | types | ARI | AMI | silhouette (cosine) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 406 | 14 | +0.117 | +0.228 | +0.009 | 0.387 | 0.120 | 0.488 | 0.261 |
| (b) first sentence removed | 406 | 14 | +0.037 | +0.166 | -0.002 | 0.332 | 0.120 | 0.406 | 0.261 |
| (c) locations stripped | 406 | 14 | +0.007 | +0.030 | +0.003 | 0.374 | 0.120 | 0.448 | 0.261 |

## Figures

Each variant gets a small-multiple grid (all points grey, one category
highlighted) and the single-panel coloured scatter.

### (a) full lead

**By article language** — the dominant axis

![a_full language facets](figs/bge-m3_a_full_language_facets.png)

![a_full language scatter](figs/bge-m3_a_full_language_scatter.png)

**By country**

![a_full country facets](figs/bge-m3_a_full_country_facets.png)

![a_full country scatter](figs/bge-m3_a_full_country_scatter.png)

**By type**

![a_full type facets](figs/bge-m3_a_full_type_facets.png)

![a_full type scatter](figs/bge-m3_a_full_type_scatter.png)

### (b) first sentence removed

**By article language** — the dominant axis

![b_nofirst language facets](figs/bge-m3_b_nofirst_language_facets.png)

![b_nofirst language scatter](figs/bge-m3_b_nofirst_language_scatter.png)

**By country**

![b_nofirst country facets](figs/bge-m3_b_nofirst_country_facets.png)

![b_nofirst country scatter](figs/bge-m3_b_nofirst_country_scatter.png)

**By type**

![b_nofirst type facets](figs/bge-m3_b_nofirst_type_facets.png)

![b_nofirst type scatter](figs/bge-m3_b_nofirst_type_scatter.png)

### (c) locations stripped

**By article language** — the dominant axis

![c_noloc language facets](figs/bge-m3_c_noloc_language_facets.png)

![c_noloc language scatter](figs/bge-m3_c_noloc_language_scatter.png)

**By country**

![c_noloc country facets](figs/bge-m3_c_noloc_country_facets.png)

![c_noloc country scatter](figs/bge-m3_c_noloc_country_scatter.png)

**By type**

![c_noloc type facets](figs/bge-m3_c_noloc_type_facets.png)

![c_noloc type scatter](figs/bge-m3_c_noloc_type_scatter.png)

## Caveats

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
