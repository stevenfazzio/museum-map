# Where this stands, and what the build phase opens with

The probe is finished (see `README.md` for findings, `reports/report.md` for the
full numbers). This file is the handoff: what was decided, what is still open,
and what to do first.

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

1. **Corpus: the full 55,280**, not the stratified sample. A map should show what
   exists. Keep the 2,000-museum stratified sample as the **dev fixture** so
   iteration stays fast — it is already on disk and every stage reproduces it.
2. **Labelling: toponymy + datamapplot.** Load the `toponymy` skill before
   touching it. Note for whoever picks this up: the 41% post-centring HDBSCAN
   noise fraction is **not** a problem for labelling. Toponymy names *regions of
   the space*, not sets of documents, so unassigned points are still covered by
   the regional label they sit under. Do not design around it.

## Open

**Encoder check — done, and it mattered.** See above: the language dominance
that drove the first round's conclusions was an e5-large artefact. This is the
argument for running the robustness check *before* building on a finding, not
after. Any further encoder swap is a one-flag rerun:

```bash
MODEL=<hf/model-id> ./run_all.sh   # cache is warm; only embed + analyse re-run
```

**The full fetch.** Measured from this run: 6,885 articles took 468 extract
requests plus 145 sitelink requests, at ~3.3 s/request with zero retries and zero
failures. Projected to 55,280 museums at 3.4 articles each:

| | |
|---|---|
| articles | ~190,000 |
| requests | ~10,600 |
| serial, as-is | **~10 hours** |
| with 3–4 workers | **~3 hours** |

It is **latency-bound, not throttle-bound** — `min_interval` is 0.15 s but
observed spacing is 3.3 s, so 3–4 concurrent workers stay well inside polite WMF
rates (~1 req/s aggregate). Worth adding before the big run.

This is an overnight job, not a week of babysitting, and it is **resumable for
free**: every response is cached by request hash, so a crash or a Ctrl-C costs
only the in-flight request. Re-running skips everything already fetched.

Two things to fix before starting it, both learned the hard way here:

- **Do not pipe the run through `tail`.** Progress output is buffered and you go
  blind for hours. Redirect to a log file and watch that.
- **Write the output parquet incrementally**, or at least checkpoint per wiki.
  The fetches survive a crash but the final assembly currently does not.

## First moves

1. Add bounded concurrency to `probe/wiki.py:fetch_leads`, then start the full
   harvest + fetch overnight.
2. While that runs: build the centring + UMAP + toponymy path against the 2,000
   dev fixture, so it is ready when the real corpus lands.
