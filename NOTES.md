# Where this stands, and what is still open

The probe is finished (see `README.md` for findings, `reports/report.md` for the
full numbers). The **build** is the current phase: the corpus is fetched and the
map pipeline runs end to end. This file is the handoff.

## Settled by the probe

Run with **two encoders**; the second one changed the story.

- The map is **not** a restatement of country (ARI +0.076 e5 / +0.016 BGE-M3) or
  of type (−0.004 / −0.003).
- **Museum type is real and recoverable** — probe 0.54–0.57 vs a 0.266 baseline
  after centring, and already 0.513 in BGE-M3's *raw* space. The project has a
  subject.
- **Geography is a gradient, not a partition**: steep local decay dying by
  ~1,000 km, plus a flat national offset that never decays. Both encoders agree
  to within noise (Mantel r −0.116 / −0.119). Deliberately not centred out —
  location is constitutive and there is no oracle to validate its removal.
- **The language confound is encoder-specific.** e5-large put language at ARI
  +0.769 and buried everything under it; BGE-M3 sits at +0.017 with raw
  cross-lingual P@1 of 0.941. **Use BGE-M3.** Per-language centring
  (`probe/debias.py:centered`) still adds a little (P@1 0.941 → 0.966) but is no
  longer load-bearing. Use leave-one-out with shrinkage regardless — 28 languages
  have n=1, and plain centring maps those onto the origin.

Reports for both encoders are in `reports/` (`report.md` = e5,
`report_bge-m3.md` = BGE-M3); figures are prefixed per non-default model.

## Settled in discussion

1. **Corpus: the full 55,280**, not the stratified sample. Keep the 2,000-museum
   stratified sample as the **dev fixture** so iteration stays fast.
2. **Labelling: toponymy + datamapplot.** Load the `toponymy` skill before
   touching it. The 41% HDBSCAN noise fraction is **not** a problem for
   labelling: toponymy names *regions of the space*, not sets of documents, so
   unassigned points are still covered by the regional label they sit under. Do
   not design around it.
3. **Deliverable: interactive map + written findings.** Not an explorer app.
4. **Naming LLM: Claude via the Anthropic API**, Haiku by default. Override with
   `LLM_MODEL=... ./run_map.sh full`.

## What the build added

Two scripts, two corpora, one code path:

```bash
# fetch (network, hours) — run detached, watch the log, never pipe through tail
uv run python -u build/b01_sitelinks.py --workers 3 > logs/b01_sitelinks.log 2>&1
nohup uv run python -u build/b02_leads.py --workers 4 > logs/b02_leads.log 2>&1 &

# map (compute) — identical code for both corpora
./run_map.sh fixture     # 2,000 museums, ~10 min
./run_map.sh full        # 49,218 museums, ~3 h
uv run python -u build/b14_analyze.py --corpus full --tag short
```

| stage | does | writes |
|---|---|---|
| `b01_sitelinks` | real Wikipedia articles for all 55,280 | `data/interim/full/sitelinks.parquet` |
| `b02_leads` | leads for every article, per-wiki shards | `data/interim/full/leads{,_all}.parquet` |
| `b03_types` | one museum type per museum | `data/interim/full/types.parquet` |
| `b10_embed` | BGE-M3, variant (a) only | `data/processed/map_<corpus>/emb.npy` |
| `b11_layout` | per-language LOO centring → UMAP 2D | `coords.parquet`, `emb_centered.npy` |
| `b12_topics` | toponymy region names, all layers | `topics_<tag>.parquet`, `topic_names_<tag>.json` |
| `b13_map` | datamapplot interactive HTML | `reports/map_<corpus>_<tag>.html` |
| `b14_analyze` | re-runs the probe's metrics on the built map | `analysis_<tag>.json` |

**Only variant (a).** The probe's (b) nofirst and (c) noloc existed to answer "is
this just geography?", and that is settled — geography stays.

## What the fetch actually cost

Measured, not projected:

| | |
|---|---|
| museums with ≥1 Wikipedia article | **49,243 of 55,280** (`sitelink_count` counts Commons too) |
| articles | 145,712 |
| extract requests | 6,493 (+1,106 sitelink) |
| wall clock, 4 workers | **~95 min** |
| permanent failures | **0** — 293/293 shards complete, none partial |
| steady-state rate | 0.88 req/s (the big wikis finish first; the tail is slower) |

197 languages in the selected leads; English is only 19.2%.

## Traps worth knowing

- **`NUMBA_THREADING_LAYER=workqueue` is required.** torch ships its own OpenMP
  runtime; once loaded, numba's default OpenMP layer segfaults inside
  `fast_hdbscan`'s kdtree on the first clustering call, every time.
  `KMP_DUPLICATE_LIB_OK` does not fix it. Set before importing numba.
- **datamapplot: `hover_text_html_template` replaces `hover_text`,** so
  `search_field="hover_text"` searches rendered HTML and matches almost nothing.
  Pass an explicit search column in `extra_point_data` instead.
- **pandas hands back Fortran-ordered arrays** from a multi-column `.to_numpy()`;
  `fast_hdbscan`'s kdtree only accepts C-ordered. `np.ascontiguousarray`.
- **Toponymy's default names run 12–15 words** and are unusable as map labels.
  `b12_topics.NAME_INSTRUCTIONS` brings the median to 5.
- **Do not pipe a long run through `tail`** — the pipeline buffers and you go
  blind. Redirect to a log file. (Learned twice.)
- **The local↔universal score is great-circle km to the 10 nearest *embedding*
  neighbours** — not cosine distance to them, which measures embedding density
  and is a different quantity entirely.

## Open

**The stub tail is the real quality question.** 12% of leads are under 150
characters and 30.6% under 300; the median is 491, against the fixture's 527, so
the dev fixture flatters the corpus. On the fixture, sub-150-character museums
are 48.4% unlabelled versus 38.2% for the longest, and sit at a 3,364 km
neighbourhood radius — the *most* internationally dispersed bucket, because a
one-line stub is generic and its nearest neighbours are other generic stubs
anywhere on earth. Whether that stays a describable feature of the map or becomes
a reason to filter is the open call. "A map should show what exists" argues for
keeping them.

**Not verified interactively:** hover tooltips and click-through on the rendered
map. Synthetic pointer events do not reach the WebGL canvas, so these were only
verified as far as the data going in. The DOM search box was verified and works.
