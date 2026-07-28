#!/usr/bin/env bash
# Build the map.
#
#   ./run.sh fixture          # 2,000 museums, ~10 min — iterate here
#   ./run.sh full             # 49,218 museums Wikidata types as museums
#   ./run.sh full_recovered   # 54,778 — the above plus the museums it does not
#                             #          type as museums. This is the real map.
#
# `full` is kept buildable on its own: it is the baseline the sensitivity
# comparison in FINDINGS.md is measured against, so p08 never writes over it.
#
# The corpus fetch is NOT run from here. It is a multi-hour network job that
# wants its own log file and its own supervision:
#
#   uv run python -u pipeline/p01_harvest.py   > logs/p01_harvest.log 2>&1
#   uv run python -u pipeline/p02_sitelinks.py > logs/p02_sitelinks.log 2>&1
#   nohup uv run python -u pipeline/p03_leads.py --workers 4 > logs/p03_leads.log 2>&1 &
#
# For full_recovered, two more — p07 is hours and ~$27, but its output is stable
# and committed downstream, so it rarely needs re-running:
#
#   uv run python -u pipeline/p07_gap.py     > logs/p07_gap.log 2>&1
#   uv run python -u pipeline/p08_recover.py > logs/p08_recover.log 2>&1
#
# Watch the log file directly. Do NOT pipe a long run through `tail` — the whole
# pipeline buffers and you go blind for hours.
#
# Everything is resumable: HTTP responses are cached by request hash, leads are
# written as per-wiki shards, and embeddings checkpoint every 5,000 rows.
set -euo pipefail
cd "$(dirname "$0")"

CORPUS="${1:-fixture}"
LLM_MODEL="${LLM_MODEL:-claude-haiku-4-5-20251001}"
TAG="${TAG:-short}"

run() { echo; echo "=== $* ==="; uv run python -u "$@"; }

case "$CORPUS" in
  full)           run pipeline/p04_types.py --corpus full ;;
  full_recovered) ;;  # types.parquet is written by p08, alongside the union
  *)              run pipeline/p05_fixture.py ;;
esac

# p09 is the only network stage in here — ~10 min cold for the full corpus, then
# seconds, because every response is cached by request hash. It runs first so a
# WDQS outage fails the build in the first minute rather than after two hours of
# embedding and clustering. Nothing downstream depends on it: p13 renders a
# correct map without facts.parquet and says so.
run pipeline/p09_facts.py   --corpus "$CORPUS"

run pipeline/p10_embed.py   --corpus "$CORPUS"
run pipeline/p11_layout.py  --corpus "$CORPUS"
run pipeline/p12_topics.py  --corpus "$CORPUS" --llm-model "$LLM_MODEL" --tag "$TAG"
run pipeline/p13_map.py     --corpus "$CORPUS" --tag "$TAG"
run pipeline/p14_analyze.py --corpus "$CORPUS" --tag "$TAG"

echo
echo "map: reports/map_${CORPUS}_${TAG}.html"
