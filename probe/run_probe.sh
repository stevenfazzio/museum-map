#!/usr/bin/env bash
# Reproduces the go/no-go probe on a 2,000-museum stratified sample.
#
# This is HISTORICAL. It is not part of building the map — see ../run.sh for
# that. It is kept because two decisions the pipeline still encodes rest on it:
# use BGE-M3 rather than e5-large, and do not centre geography out. Its reports
# are in probe/reports/.
#
#   ./probe/run_probe.sh                          # BGE-M3 (the chosen encoder)
#   MODEL=intfloat/multilingual-e5-large ./probe/run_probe.sh
#
# Needs data/raw/museums.parquet, which the pipeline's harvest produces:
#   uv run python -u pipeline/p01_harvest.py
#
# Every network response is cached under data/cache keyed by a hash of the full
# request, so a second run costs nothing and reproduces offline.
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${MODEL:-BAAI/bge-m3}"

run() { echo; echo "=== $* ==="; uv run python -u "$@"; }

run probe/s02_sample.py
run probe/s03_sitelinks.py
run probe/s04_finalize.py
run probe/s05_leads.py
run probe/s06_variants.py
run probe/s07_embed.py     --model "$MODEL"
run probe/s08_analyze.py   --model "$MODEL"
run probe/s08_analyze.py   --model "$MODEL" --center
run probe/s10_parallel.py  --model "$MODEL"
run probe/s11_geography.py --model "$MODEL"
run probe/s09_report.py    --model "$MODEL"

echo
echo "report: probe/reports/"
