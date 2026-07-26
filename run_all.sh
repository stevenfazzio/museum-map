#!/usr/bin/env bash
# Full pipeline. Every network response is cached under data/cache, so a second
# run costs nothing and is offline-reproducible. Stages are independent scripts;
# rerun any one of them alone once its inputs exist.
set -euo pipefail

MODEL="${MODEL:-intfloat/multilingual-e5-large}"

run() { echo; echo "=== $* ==="; uv run python -u "$@"; }

run stages/s01_harvest.py
run stages/s02_sample.py
run stages/s03_sitelinks.py
run stages/s04_finalize.py
run stages/s05_leads.py
run stages/s06_variants.py
run stages/s07_embed.py   --model "$MODEL"
run stages/s08_analyze.py --model "$MODEL"
run stages/s08_analyze.py --model "$MODEL" --center
run stages/s10_parallel.py  --model "$MODEL"
run stages/s11_geography.py --model "$MODEL"
run stages/s09_report.py  --model "$MODEL"

echo
echo "report: reports/report.md"
