#!/usr/bin/env bash
# 导出逐笔成交并算逐日盯市指标：scripts/bt-export.sh <timerange> <策略>
set -euo pipefail
cd "$(dirname "$0")/.."
range=$1 s=$2
docker compose run --rm --entrypoint freqtrade futures backtesting \
  --config /freqtrade/user_data/config.base.json --config /freqtrade/user_data/config.futures.json \
  --config /freqtrade/user_data/config.research.json \
  --timerange "$range" --fee 0.0006 --cache none --strategy "$s" ${BT_EXTRA:-} \
  --export trades --backtest-directory /freqtrade/user_data/backtest_results >/dev/null 2>&1
last=$(python3 -c "import json;print(json.load(open('user_data/backtest_results/.last_result.json'))['latest_backtest'])")
docker compose run --rm -v "$PWD/scripts:/scripts:ro" --entrypoint python futures /scripts/mtm_sharpe.py "/freqtrade/user_data/backtest_results/$last" 2>&1 | grep -v Warning
