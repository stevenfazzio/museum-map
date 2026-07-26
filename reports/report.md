# Does country or museum type already explain the embedding space?

> **Short answer: neither — but article *language* does, and that is a confound
> introduced by the sampling rule rather than a fact about museums.**

A go/no-go probe for the museum map: if the embedding of a museum's Wikipedia
lead is mostly a proxy for *where it is* and *what kind of museum it is*, then a
semantic map adds nothing over a choropleth with a type filter.

**Model:** `intfloat/multilingual-e5-large` · **UMAP:** 10D for clustering, 2D for display,
`random_state=42` · **Clustering:** HDBSCAN (`min_cluster_size=15`,
`min_samples=5`)

## Verdict

Headline numbers, full lead (variant a), 1999 museums.

| label | do clusters equal it? (ARI) | do 10 neighbours share it? | chance | lift | linear probe | baseline |
|---|---|---|---|---|---|---|
| **language of the lead** | **+0.769** | **70.8%** | 5.9% | **12x** | 56.7% | 17.5% |
| country | +0.076 | 27.4% | 0.7% | 37x | 15.0% | 2.2% |
| type (all) | -0.004 | 48.4% | 40.9% | 1.2x | 62.5% | 62.5% |

Read the **ARI** and **purity** columns, not the lift column, when comparing rows
against each other. Lift is purity ÷ chance, and chance depends on how many
categories the label has (209 countries vs
104 languages), so country's larger lift only says
country is far from *its own* much lower chance floor — it does not make country
the stronger axis.

**The dominant axis is not country or type — it is the language the article is written in.** HDBSCAN's clusters line up with it at ARI **+0.769**, against **+0.076** for country. The map you would build from these embeddings today is, first and foremost, a map of Wikipedia language editions.

**Country is real but secondary, and partly a language proxy.** Neighbour purity
is 27.4% against 0.7% chance (37x), yet
silhouette is ~0 (-0.007) and ARI only +0.076:
country information is present and distributed, not the shape of the space. Because the
lead is taken from whichever Wikipedia had the longest article, and language tracks
country closely, an unknown part of that 37x is language wearing a country
label.

Stripping locations removes **36%** of the country signal, but only **2%** of the language signal. Place names carry a real share of the geography; they carry almost none of the language effect, which is why (c) barely moves the map.

**The opening sentence carries a large share of both effects.** Removing just the
first sentence (variant b) drops language ARI from +0.769 to
+0.401 and country neighbour purity from 27.4% to
16.4%. Wikipedia's opening line is highly formulaic and
its template differs per language edition, so it encodes both "what language is
this" and "where is this" more strongly than the rest of the lead.

Museum type is close to absent: ARI **-0.004**, and even among the 563 specifically-typed museums the linear probe reaches **27.4%** against a **26.6%** baseline. Neighbourhoods are mildly type-ish (30.2% vs 12.0% chance) but type is nowhere near an organising axis.

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
| raw | 0.854 | 0.949 | 0.890 | 0.81 | 0.421 | 0.611 |
| per-language centered | 0.954 | 0.983 | 0.965 | 0.37 | 0.098 | 0.653 |
| INLP (543/1024 dims removed) | 0.866 | 0.941 | 0.893 | 0.12 | 0.050 | 0.339 |

(chance for language 10-NN is 0.041; for country
0.008)

**Centring works, and better than the clustering numbers suggested.** Per-language
centroid subtraction takes cross-lingual P@1 from 0.854 to
**0.954** (+12%), drops language neighbour purity from
0.421 to 0.098 against a
0.041 floor, and *raises* country purity
(0.611 → 0.653) rather than
destroying it. Same-language crowding falls from 0.81
to 0.37.

**INLP over-corrects.** It suppresses language hardest
(0.050, nearly the 0.041
floor) but strips 543 of 1024 dimensions and
takes country purity down with it
(0.611 → 0.339), for *worse*
retrieval than centring. Its own trace shows why: linear language accuracy
collapses from 0.805 to
0.138 after a single projection and then plateaus —
iterations 2 and 3 remove hundreds more dimensions for no further gain. One
iteration would have been the right stopping point.

### Is this just matching the museum's name?

The same museum's articles tend to repeat its proper name verbatim, so retrieval
could be string matching wearing a semantic costume. Splitting the queries by
whether the museum's Wikidata label appears in both articles:

| representation | P@1, name in both | P@1, name absent | gap |
|---|---|---|---|
| raw | 0.877 | 0.843 | +0.034 |
| per-language centered | 0.976 | 0.945 | +0.031 |
| INLP | 0.909 | 0.848 | +0.061 |

The gap is small: even with no shared name string, centred P@1 is
0.945 across 4,171 queries. The
cross-lingual signal is real content, not surface overlap. (Conservative
caveat: "name absent" only checks the *English* label verbatim — a translated or
transliterated form of the name could still be present in both texts.)

![language dissolving](figs/language_dissolve.png)

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
0.421 in this corpus versus
0.708 in the map corpus.
The raw-vs-centred-vs-INLP comparison is internally valid; the absolute purity
values are not interchangeable between sections.

## What survives once language is centred out

Applying the winning transform to the map corpus itself — per-language centring,
centroids estimated within these 1,999 museums — and re-running the whole
analysis.

| label | ARI vs clusters | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|
| language of the lead | +0.769 → **+0.007** | 0.708 → **0.163** | 0.059 | 0.567 → **0.137** | 0.175 |
| country | +0.076 → **+0.006** | 0.274 → **0.156** | 0.007 | 0.150 → **0.178** | 0.022 |
| type (all) | -0.004 → **+0.049** | 0.484 → **0.479** | 0.409 | 0.625 → **0.636** | 0.625 |
| type (specifically-typed, n=563) | +0.005 → **+0.062** | 0.302 → **0.403** | 0.120 | 0.274 → **0.542** | 0.266 |

**Language is gone.** ARI +0.769 → +0.007,
and the linear probe falls to 0.137 — *below* its
own 0.175 majority baseline, i.e. no longer
linearly recoverable at all.

**Country survives, and is confirmed as real rather than a language proxy.** Its
probe accuracy actually *rises*, 0.150 →
0.178 against a
0.022 baseline, because removing the dominant
language direction makes the weaker country direction easier for a linear model
to reach. Its neighbourhood purity drops
(0.274 → 0.156) — that
part *was* language wearing a country label — but ARI stays near zero throughout:
country is present and distributed, never the shape of the space.

**And museum type comes out from under it.** This is the result that changes the
project's answer. Among specifically-typed museums the probe goes
0.274 → **0.542** against a
0.266 baseline — a 2.0x jump, from
indistinguishable-from-guessing to genuinely predictable. Neighbourhood purity
rises 0.302 → 0.403 (chance
0.120), and type becomes the label best aligned with the cluster
structure (type, ARI +0.049). Type was in the embedding the whole
time; language was drowning it.

One honest caveat: HDBSCAN's noise fraction jumps from
7% to 41%. Centring removes the
easy, dominant partition and what remains is a flatter, less clumpy space. The
structure that survives is real but weaker — a map of it will look like gradients,
not islands.

![centered, by type](figs/centered_type_facets.png)

![centered, by language](figs/centered_language_facets.png)

## How to read this

`ARI` compares two *partitions*, so ~31 HDBSCAN clusters
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

![lead lengths](figs/lead_lengths.png)

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
| (a) full lead | 1999 | 31 | 7% | +0.769 | +0.806 | -0.030 | +0.002 | 0.708 | 0.059 | 0.567 | 0.175 |
| (b) first sentence removed | 1530 | 28 | 15% | +0.401 | +0.669 | -0.062 | -0.160 | 0.594 | 0.071 | 0.551 | 0.205 |
| (c) locations stripped | 1992 | 37 | 11% | +0.626 | +0.775 | -0.030 | +0.117 | 0.692 | 0.059 | 0.563 | 0.175 |

**vs country** (209 countries)

| variant | n | clusters | noise | ARI | AMI | silhouette (cosine) | silhouette (2D) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 1999 | 31 | 7% | +0.076 | +0.329 | -0.007 | -0.536 | 0.274 | 0.007 | 0.150 | 0.022 |
| (b) first sentence removed | 1530 | 28 | 15% | +0.063 | +0.249 | -0.071 | -0.613 | 0.164 | 0.008 | 0.130 | 0.027 |
| (c) locations stripped | 1992 | 37 | 11% | +0.073 | +0.297 | -0.068 | -0.555 | 0.175 | 0.007 | 0.141 | 0.022 |

**vs type** (16 types, incl. the generic bucket)

| variant | n | clusters | noise | ARI | AMI | silhouette (cosine) | silhouette (2D) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 1999 | 31 | 7% | -0.004 | +0.031 | -0.039 | -0.275 | 0.484 | 0.409 | 0.625 | 0.625 |
| (b) first sentence removed | 1530 | 28 | 15% | +0.002 | +0.025 | -0.041 | -0.183 | 0.448 | 0.389 | 0.608 | 0.608 |
| (c) locations stripped | 1992 | 37 | 11% | -0.003 | +0.024 | -0.045 | -0.239 | 0.486 | 0.410 | 0.627 | 0.626 |

**vs type, specifically-typed museums only** (generic `museum` and `other` dropped — with 62% of the sample in one bucket the table above is a majority-class artefact)

| variant | n | types | ARI | AMI | silhouette (cosine) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 563 | 14 | +0.005 | +0.064 | -0.001 | 0.302 | 0.120 | 0.274 | 0.266 |
| (b) first sentence removed | 454 | 14 | +0.008 | +0.046 | -0.008 | 0.257 | 0.117 | 0.258 | 0.256 |
| (c) locations stripped | 560 | 14 | +0.009 | +0.044 | -0.002 | 0.297 | 0.120 | 0.282 | 0.268 |

## Results — common subset (identical museums in all three variants)

Restricting all three to the same museums makes the numbers directly comparable,
at the cost of skewing long: dropping the single-sentence leads removes the
shortest stubs.

**vs language of the lead** (82 languages)

| variant | n | clusters | noise | ARI | AMI | silhouette (cosine) | silhouette (2D) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 1524 | 20 | 9% | +0.761 | +0.798 | -0.033 | +0.118 | 0.700 | 0.072 | 0.584 | 0.205 |
| (b) first sentence removed | 1524 | 24 | 10% | +0.422 | +0.670 | -0.063 | -0.170 | 0.593 | 0.072 | 0.552 | 0.205 |
| (c) locations stripped | 1524 | 22 | 4% | +0.818 | +0.828 | -0.033 | +0.225 | 0.689 | 0.072 | 0.577 | 0.205 |

**vs country** (204 countries)

| variant | n | clusters | noise | ARI | AMI | silhouette (cosine) | silhouette (2D) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 1524 | 20 | 9% | +0.064 | +0.302 | -0.019 | -0.573 | 0.253 | 0.008 | 0.139 | 0.027 |
| (b) first sentence removed | 1524 | 24 | 10% | +0.064 | +0.247 | -0.072 | -0.609 | 0.161 | 0.008 | 0.118 | 0.027 |
| (c) locations stripped | 1524 | 22 | 4% | +0.062 | +0.283 | -0.083 | -0.633 | 0.157 | 0.008 | 0.120 | 0.027 |

**vs type** (16 types, incl. the generic bucket)

| variant | n | clusters | noise | ARI | AMI | silhouette (cosine) | silhouette (2D) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 1524 | 20 | 9% | -0.006 | +0.023 | -0.041 | -0.244 | 0.452 | 0.390 | 0.609 | 0.609 |
| (b) first sentence removed | 1524 | 24 | 10% | +0.006 | +0.023 | -0.042 | -0.211 | 0.449 | 0.390 | 0.609 | 0.609 |
| (c) locations stripped | 1524 | 22 | 4% | -0.003 | +0.022 | -0.047 | -0.221 | 0.451 | 0.390 | 0.609 | 0.609 |

**vs type, specifically-typed museums only** (generic `museum` and `other` dropped — with 62% of the sample in one bucket the table above is a majority-class artefact)

| variant | n | types | ARI | AMI | silhouette (cosine) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 451 | 14 | +0.006 | +0.047 | -0.001 | 0.297 | 0.117 | 0.262 | 0.257 |
| (b) first sentence removed | 451 | 14 | +0.009 | +0.044 | -0.008 | 0.259 | 0.117 | 0.259 | 0.257 |
| (c) locations stripped | 451 | 14 | +0.009 | +0.042 | -0.003 | 0.290 | 0.117 | 0.264 | 0.257 |

## Results — common subset, shortest length quartile dropped

Cut at 274 characters.

**vs language of the lead** (81 languages)

| variant | n | clusters | noise | ARI | AMI | silhouette (cosine) | silhouette (2D) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 1299 | 20 | 12% | +0.748 | +0.784 | -0.029 | +0.109 | 0.680 | 0.071 | 0.560 | 0.205 |
| (b) first sentence removed | 1299 | 24 | 16% | +0.439 | +0.674 | -0.059 | -0.067 | 0.587 | 0.071 | 0.534 | 0.205 |
| (c) locations stripped | 1299 | 24 | 7% | +0.848 | +0.826 | -0.033 | +0.171 | 0.671 | 0.071 | 0.558 | 0.205 |

**vs country** (201 countries)

| variant | n | clusters | noise | ARI | AMI | silhouette (cosine) | silhouette (2D) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 1299 | 20 | 12% | +0.063 | +0.276 | -0.028 | -0.612 | 0.227 | 0.008 | 0.114 | 0.032 |
| (b) first sentence removed | 1299 | 24 | 16% | +0.060 | +0.238 | -0.076 | -0.635 | 0.151 | 0.008 | 0.096 | 0.032 |
| (c) locations stripped | 1299 | 24 | 7% | +0.064 | +0.263 | -0.094 | -0.658 | 0.141 | 0.008 | 0.101 | 0.032 |

**vs type** (16 types, incl. the generic bucket)

| variant | n | clusters | noise | ARI | AMI | silhouette (cosine) | silhouette (2D) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 1299 | 20 | 12% | -0.003 | +0.023 | -0.040 | -0.247 | 0.435 | 0.376 | 0.597 | 0.597 |
| (b) first sentence removed | 1299 | 24 | 16% | +0.002 | +0.019 | -0.038 | -0.230 | 0.437 | 0.376 | 0.597 | 0.597 |
| (c) locations stripped | 1299 | 24 | 7% | -0.004 | +0.021 | -0.044 | -0.233 | 0.432 | 0.376 | 0.597 | 0.597 |

**vs type, specifically-typed museums only** (generic `museum` and `other` dropped — with 62% of the sample in one bucket the table above is a majority-class artefact)

| variant | n | types | ARI | AMI | silhouette (cosine) | 10-NN purity | chance | linear probe | baseline |
|---|---|---|---|---|---|---|---|---|---|
| (a) full lead | 406 | 14 | +0.009 | +0.040 | -0.000 | 0.299 | 0.120 | 0.266 | 0.261 |
| (b) first sentence removed | 406 | 14 | +0.007 | +0.030 | -0.006 | 0.267 | 0.120 | 0.261 | 0.261 |
| (c) locations stripped | 406 | 14 | +0.014 | +0.041 | -0.002 | 0.296 | 0.120 | 0.266 | 0.261 |

## Figures

Each variant gets a small-multiple grid (all points grey, one category
highlighted) and the single-panel coloured scatter.

### (a) full lead

**By article language** — the dominant axis

![a_full language facets](figs/a_full_language_facets.png)

![a_full language scatter](figs/a_full_language_scatter.png)

**By country**

![a_full country facets](figs/a_full_country_facets.png)

![a_full country scatter](figs/a_full_country_scatter.png)

**By type**

![a_full type facets](figs/a_full_type_facets.png)

![a_full type scatter](figs/a_full_type_scatter.png)

### (b) first sentence removed

**By article language** — the dominant axis

![b_nofirst language facets](figs/b_nofirst_language_facets.png)

![b_nofirst language scatter](figs/b_nofirst_language_scatter.png)

**By country**

![b_nofirst country facets](figs/b_nofirst_country_facets.png)

![b_nofirst country scatter](figs/b_nofirst_country_scatter.png)

**By type**

![b_nofirst type facets](figs/b_nofirst_type_facets.png)

![b_nofirst type scatter](figs/b_nofirst_type_scatter.png)

### (c) locations stripped

**By article language** — the dominant axis

![c_noloc language facets](figs/c_noloc_language_facets.png)

![c_noloc language scatter](figs/c_noloc_language_scatter.png)

**By country**

![c_noloc country facets](figs/c_noloc_country_facets.png)

![c_noloc country scatter](figs/c_noloc_country_scatter.png)

**By type**

![c_noloc type facets](figs/c_noloc_type_facets.png)

![c_noloc type scatter](figs/c_noloc_type_scatter.png)

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
