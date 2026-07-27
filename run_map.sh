#!/usr/bin/env bash
# The map build. Separate from run_all.sh, which reproduces the go/no-go probe on
# the 2,000-museum sample and should keep doing exactly that.
#
#   ./run_map.sh fixture     # 2,000 museums, ~10 min, iterate here
#   ./run_map.sh full        # 55,280 museums, hours — see the note below
#
# The fetch stages (b01/b02) are NOT run from here. They are a multi-hour network
# job that wants its own log file and its own supervision:
#
#   uv run python -u build/b01_sitelinks.py --workers 3 > logs/b01_sitelinks.log 2>&1
#   nohup uv run python -u build/b02_leads.py --workers 4 > logs/b02_leads.log 2>&1 &
#
# Watch the log file directly. Do not pipe either one through `tail` — the whole
# pipeline buffers and you go blind for hours.
set -euo pipefail

CORPUS="${1:-fixture}"
LLM_MODEL="${LLM_MODEL:-claude-haiku-4-5-20251001}"
TAG="${TAG:-short}"

run() { echo; echo "=== $* ==="; uv run python -u "$@"; }

if [ "$CORPUS" = "full" ]; then
  run build/b03_types.py --corpus full
fi

run build/b10_embed.py  --corpus "$CORPUS"
run build/b11_layout.py --corpus "$CORPUS"
run build/b12_topics.py --corpus "$CORPUS" --llm-model "$LLM_MODEL" --tag "$TAG"
run build/b13_map.py    --corpus "$CORPUS" --tag "$TAG"

echo
echo "map: reports/map_${CORPUS}_${TAG}.html"
