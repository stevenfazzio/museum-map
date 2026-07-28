# Working in this repo

A semantic map of 49,218 museums built from their Wikipedia leads. Read
`README.md` for what it is and `FINDINGS.md` for what it found.

## Orientation

- `pipeline/` is the project. `museum_map/` is the library it imports.
- `probe/` is a historical experiment. It is not a dependency of anything in
  `pipeline/`; do not extend it, and do not assume its numbers still hold — two
  of its conclusions were overturned at full scale (see `FINDINGS.md`).
- Names are meant literally now. If you find yourself explaining that a directory
  isn't what it sounds like, rename it instead. The one strained name is `full`:
  it is *not* the fullest corpus, it is the museums Wikidata types as museums.
  `full_recovered` is the whole thing and is what ships. `full` is kept only
  because FINDINGS.md's sensitivity comparison is measured against it, and `p08`
  never writes over it.
- Two corpora, two channels. `p01` trusts Wikidata's `P31`; `p07` trusts the
  prose in each wiki's museum category tree, and finds 5,560 museums `p01`
  cannot. `p07` is hours and ~$27, so it is not in `run.sh` — its output
  (`data/interim/gap/in_scope_qids.json`) is stable and only changes as
  Wikidata's typing does.
- The fixture (`--corpus fixture`) is for checking that a stage runs, not for
  measuring anything. Distributional properties transfer; neighbourhood ones
  cannot, because a 4% sample removes 96% of every museum's nearest neighbours.
  See the caveat in `pipeline/p05_fixture.py`.

## Data safety

`data/` is hours of network and GPU time and is gitignored. Treat every file
under it as expensive.

- Write through `museum_map.common.write_parquet`, which writes to a temp file,
  reads it back, checks the row count, then renames. Never `to_parquet` straight
  onto an existing path.
- Before adding a "skip if already computed" check, ask what it is actually
  comparing. Row count is not identity: changing which language represents each
  museum leaves the count identical and every vector wrong. `p10_embed`
  fingerprints the input text, model, and sequence cap for this reason.
- A stage that reads two frames must assert their `qid` order matches before
  using them positionally. Several already do; keep it up.

## Crawling category trees

`COVERAGE.md` was built by walking the museum category tree of 30 wikis. Three
things about that generalise to any traversal of Wikipedia or Wikidata.

- **Contain the walk; do not blocklist the drift.** Only descend into a category
  that is itself museum-named. A blocklist cannot anticipate where a graph goes:
  at depth 12 from `Category:Museums`, a name-based blocklist still let the walk
  reach `National Film Registry films` (749 articles), `Royal Academicians` (594)
  and `Psalms` (188), by way of a museum → its collection → the works in it.
  Containment cut the English crawl from 63,964 articles to 33,216 and lost
  nothing real.
- **A drift term that matches the target vocabulary empties a wiki in silence.**
  `musei` was added to catch `museologia`; it is Italian for *museums*, and it
  pruned the entire Italian tree to 9 articles — a plausible-looking small number,
  not an error. Assert that no drift pattern matches a wiki's own stems, and flag
  any wiki returning fewer articles than the corpus already holds for it.
- **A rate measured on a contained subtree does not transfer to an uncontained
  one.** Connecticut gave 21% of crawled articles surviving as real misses and
  90% precision; globally the same rule ran ~38% and ~65%, because a small clean
  subtree contains none of the dealer galleries, films or video games that a
  global crawl does. This is the same trap as `--corpus fixture`, in a new place.

## Long-running jobs

- **Never pipe a long run through `tail`.** The pipeline buffers and you go blind
  for hours. Redirect to a file in `logs/` and read that.
- Report progress on a **trailing window**, not a cumulative average. A resumed
  run replays thousands of cached responses in the first second, and a cumulative
  rate makes every later ETA wildly optimistic.
- When watching a job for completion, watch for the **artifact appearing or the
  process disappearing** — not for a phrase in the log. A watcher whose pattern
  never matches is indistinguishable from one still waiting.

## Environment traps

These cost real time; all three are commented where they bite.

- **`NUMBA_THREADING_LAYER=workqueue` is required before importing numba** in any
  stage that also loads torch. torch ships its own OpenMP runtime and numba's
  default layer segfaults inside `fast_hdbscan`'s kdtree on the first clustering
  call, every time. `KMP_DUPLICATE_LIB_OK` does not help.
- **`np.ascontiguousarray` anything from a multi-column `.to_numpy()`.** pandas
  returns Fortran order; `fast_hdbscan`'s kdtree only accepts C order.
- **BGE-M3 advertises `max_seq_length` 8192** and sentence-transformers sorts
  batches longest-first, so the first batch OOMs MPS. The cap is 2,048.

## Toponymy

Load the `toponymy` skill before touching `p12_topics.py`. It labels *regions of
the space*, not sets of documents — `Unlabelled` is the unnamed gap between named
places at a given zoom, recomputed per layer, and it is kept in the output on
purpose. 56% unlabelled at the finest layer is a description of a smooth space,
not a defect. `topic_names_[0]` is the finest layer, `[-1]` the coarsest.

Toponymy's default names run 12–15 words and are unusable as map labels; the
brevity instruction in `p12_topics.NAME_INSTRUCTIONS` is load-bearing.

## Conventions

- Python via `uv`, lint and format with `ruff` (line length 100).
- `random_state=42` / `SEED` everywhere, including UMAP.
- Plain `.py` scripts, no notebooks. Visualisations as HTML, not PNG.
- Every stage is independently runnable once its inputs exist; `run.sh` just
  sequences them.
