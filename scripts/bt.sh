#!/usr/bin/env bash
# 研究用回测：scripts/bt.sh <timerange> <策略...>   例：scripts/bt.sh 20220101-20240701 DonchianTrend TsMomentum
# 费用按 0.06%/边（Binance 合约 taker 0.05% + 滑点）。每个策略单独跑（周期不同，不能用 --strategy-list）。
set -euo pipefail
cd "$(dirname "$0")/.."
range=$1; shift
for s in "$@"; do
  echo "######## $s $range"
  docker compose run --rm --entrypoint freqtrade futures backtesting \
    --config /freqtrade/user_data/config.base.json \
    --config /freqtrade/user_data/config.futures.json \
    --config /freqtrade/user_data/config.research.json \
    --timerange "$range" --fee 0.0006 --export none --cache none \
    --strategy "$s" ${BT_EXTRA:-} 2>&1
done
