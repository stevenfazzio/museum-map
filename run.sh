#!/usr/bin/env bash
# Build the map.
#
#   ./run.sh fixture     # 2,000 museums, ~10 min — iterate here
#   ./run.sh full        # 49,218 museums, ~2 h of compute
#
# The corpus fetch is NOT run from here. It is a multi-hour network job that
# wants its own log file and its own supervision:
#
#   uv run python -u pipeline/p01_harvest.py   > logs/p01_harvest.log 2>&1
#   uv run python -u pipeline/p02_sitelinks.py > logs/p02_sitelinks.log 2>&1
#   nohup uv run python -u pipeline/p03_leads.py --workers 4 > logs/p03_leads.log 2>&1 &
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

if [ "$CORPUS" = "full" ]; then
  run pipeline/p04_types.py --corpus full
else
  run pipeline/p05_fixture.py
fi

run pipeline/p10_embed.py   --corpus "$CORPUS"
run pipeline/p11_layout.py  --corpus "$CORPUS"
run pipeline/p12_topics.py  --corpus "$CORPUS" --llm-model "$LLM_MODEL" --tag "$TAG"
run pipeline/p13_map.py     --corpus "$CORPUS" --tag "$TAG"
run pipeline/p14_analyze.py --corpus "$CORPUS" --tag "$TAG"

echo
echo "map: reports/map_${CORPUS}_${TAG}.html"
