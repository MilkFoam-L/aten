"""逐日盯市（mark-to-market）权益曲线 → 夏普 / 最大回撤 / 分段收益。

在 freqtrade 容器里运行（需要 pandas 和本地数据）：
  docker compose run --rm --entrypoint python futures /freqtrade/user_data/../scripts/mtm_sharpe.py <结果zip或json>
Freqtrade 的 "Sharpe (closed trades)" 只在平仓日计入盈亏，对持仓数周的趋势策略系统性偏低，这里按日线收盘价逐日估值。
"""
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path("/freqtrade/user_data/data/binance")


def load_trades(path: str) -> tuple[list[dict], float]:
    p = Path(path)
    if p.suffix == ".zip":
        with zipfile.ZipFile(p) as z:
            name = next(n for n in z.namelist() if n.endswith(".json") and "_config" not in n and "_market" not in n)
            data = json.loads(z.read(name))
    else:
        data = json.loads(p.read_text())
    strat = next(iter(data["strategy"].values()))
    return strat["trades"], float(strat["starting_balance"])


def closes(pair: str) -> pd.Series:
    name = pair.replace("/", "_").replace(":", "_")
    f = DATA / "futures" / f"{name}-1d-futures.feather" if ":" in pair else DATA / f"{name}-1d.feather"
    df = pd.read_feather(f)
    return df.set_index(pd.to_datetime(df["date"], utc=True).dt.normalize())["close"]


def main() -> None:
    trades, start = load_trades(sys.argv[1])
    t0 = pd.Timestamp(min(t["open_date"] for t in trades)).normalize()
    t1 = pd.Timestamp(max(t["close_date"] for t in trades)).normalize()
    days = pd.date_range(t0, t1, freq="D", tz="UTC")
    pnl = pd.Series(0.0, index=days)  # 每日权益变化
    cache: dict[str, pd.Series] = {}
    for t in trades:
        c = cache.setdefault(t["pair"], closes(t["pair"]))
        o, x = pd.Timestamp(t["open_date"]), pd.Timestamp(t["close_date"])
        side = -1 if t.get("is_short") else 1
        qty = t["amount"]
        # 开仓日到平仓前一日按收盘价估值，平仓日补齐到实际已实现盈亏（含手续费、资金费）
        marks = c[(c.index >= o.normalize()) & (c.index < x.normalize())]
        prev = t["open_rate"]
        for d, px in marks.items():
            if d >= o.normalize():
                pnl[d] += side * qty * (px - prev)
                prev = px
        realized_so_far = side * qty * (prev - t["open_rate"])
        pnl[x.normalize()] += t["profit_abs"] - realized_so_far
    equity = start + pnl.cumsum()
    ret = equity.pct_change().dropna()
    sharpe = ret.mean() / ret.std() * np.sqrt(365)
    dd = (equity / equity.cummax() - 1).min()
    years = (days[-1] - days[0]).days / 365
    cagr = (equity.iloc[-1] / start) ** (1 / years) - 1
    print(f"区间 {days[0].date()} ~ {days[-1].date()}  期末权益 {equity.iloc[-1]:.0f}")
    print(f"逐日盯市夏普 {sharpe:.2f}  年化 {cagr:.1%}  最大回撤 {dd:.1%}  Calmar {cagr / -dd:.2f}")
    yearly = equity.resample("YE").last().pct_change()
    yearly.iloc[0] = equity.resample("YE").last().iloc[0] / start - 1
    print("分年收益：" + "  ".join(f"{d.year}:{v:+.1%}" for d, v in yearly.items()))


if __name__ == "__main__":
    main()
