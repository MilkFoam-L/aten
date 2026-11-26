"""从 bt.sh 的输出里抽关键指标：python3 scripts/bt-summary.py < out.txt"""
import re
import sys

KEYS = ["Total/Daily Avg Trades", "Total profit %", "CAGR %", "Sharpe (closed trades)", "Profit factor",
        "Max % of account underwater", "Market change", "Win  Draw  Loss  Win%"]
cur = None
pairs = {}
for line in sys.stdin:
    if line.startswith("######## "):
        cur = line[9:].strip()
        print(f"\n== {cur}")
        pairs[cur] = [0, 0]
        continue
    cells = [c.strip() for c in line.split("│")]
    if len(cells) > 3 and cells[1] in KEYS:
        print(f"  {cells[1]:32} {cells[2]}")
    # 每币种表：│ BTC/USDT:USDT │ trades │ avg% │ tot USDT │ tot% │ ...
    if len(cells) > 6 and re.match(r"^[A-Z0-9]+/USDT:USDT$", cells[1] or "") and cur:
        try:
            v = float(cells[5])
        except ValueError:
            continue
        pairs[cur][0 if v > 0 else 1] += 1
for k, (w, l) in pairs.items():
    print(f"{k}: 盈利币种/亏损币种（含各表重复计数，取比例） {w}/{l}")
