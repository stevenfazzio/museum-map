# Where this stands, and what the build phase opens with

The probe is finished (see `README.md` for findings, `reports/report.md` for the
full numbers). This file is the handoff: what was decided, what is still open,
and what to do first.

## Settled by the probe

- The map is **not** a restatement of country (ARI +0.076) or type (−0.004).
- **Article language dominated** (ARI +0.769) — an artefact of the "longest
  article across languages" rule, not a fact about museums.
- **Per-language centring removes it** (`probe/debias.py:centered`), validated
  against parallel articles rather than against a clustering metric: cross-lingual
  P@1 goes 0.854 → 0.954 *while* language purity collapses. Use leave-one-out
  with shrinkage — 28 languages have n=1 and plain centring maps them onto the
  origin.
- **With language out, museum type becomes recoverable** (probe 0.274 → 0.542).
  Country survives too and its probe *improves*, so it was real, not a proxy.
- **Geography is a gradient, not a partition**: a steep local effect that dies by
  ~1,000 km, plus a flat national offset that never decays. Deliberately not
  centred out — location is constitutive, and there is no oracle to validate the
  removal against.

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

**Encoder check (do this first, in the background).** Every conclusion rests on
`multilingual-e5-large`. The `--model` flag exists and has never been exercised:

```bash
MODEL=BAAI/bge-m3 ./run_all.sh     # cache is warm; only embed + analyse re-run
```

~30 min. If language dominance is partly an e5 artefact, the centring step about
to be baked into the production pipeline may need different tuning. Cheap
insurance, not more investigation.

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

1. Kick off the BGE-M3 run in the background.
2. Add bounded concurrency to `probe/wiki.py:fetch_leads`, then start the full
   harvest + fetch overnight.
3. While that runs: build the centring + UMAP + toponymy path against the 2,000
   dev fixture, so it is ready when the real corpus lands.
