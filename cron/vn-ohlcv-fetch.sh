#!/usr/bin/env bash
# vn-ohlcv-data-fetcher — Cron job wrapper
# Runs daily at 16:00 SGT (Mon-Fri) to populate aggregated_data table
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JHUB="$SCRIPT_DIR"
VENV="$JHUB/venv"
PYTHON="$VENV/bin/python3"
SCRIPT="$SCRIPT_DIR/../.hermes/scripts/vn-ohlcv-fetch.py"
LOG="$SCRIPT_DIR/../logs/vn-ohlcv-fetch.log"

# Ensure log dir exists
mkdir -p "$SCRIPT_DIR/../logs"

# Activate venv and run
source "$VENV/bin/activate"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') vn-ohlcv-fetch cron start ==="
$PYTHON "$SCRIPT" --all --days 14 --batch-size 10 --concurrency 3 2>&1 | tee -a "$LOG"
EXIT_CODE=${PIPESTATUS[0]}
echo "=== $(date '+%Y-%m-%d %H:%M:%S') Exit code: $EXIT_CODE ==="

exit $EXIT_CODE
