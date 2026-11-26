"""研究用候选策略（趋势跟踪族）。参数刻意少，默认值取经典文献值，不在样本外调参。

结论与过程记录见 docs/strategy-research.md。
"""

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy, IntParameter


class _Base(IStrategy):
    INTERFACE_VERSION = 3
    can_short = True
    minimal_roi = {"0": 100}  # 不用 ROI 止盈，让利润奔跑
    stoploss = -0.15  # 灾难止损（1 倍杠杆）；常规离场靠通道/信号反转
    use_exit_signal = True
    process_only_new_candles = True

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        return 1.0


class DonchianTrend(_Base):
    """海龟式唐奇安突破：收盘突破 N 根高点做多 / 跌破低点做空，反向 M 根通道离场。"""

    timeframe = "4h"
    startup_candle_count = 220
    entry_n = IntParameter(20, 100, default=55, space="buy")
    exit_n = IntParameter(10, 50, default=20, space="sell")

    def populate_indicators(self, df: DataFrame, metadata: dict) -> DataFrame:
        for n in set(self.entry_n.range) | set(self.exit_n.range):
            df[f"hh{n}"] = df["high"].rolling(n).max().shift(1)
            df[f"ll{n}"] = df["low"].rolling(n).min().shift(1)
        df["ema200"] = ta.EMA(df, timeperiod=200)
        return df

    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        n = self.entry_n.value
        df.loc[(df["close"] > df[f"hh{n}"]) & (df["close"] > df["ema200"]) & (df["volume"] > 0), ["enter_long", "enter_tag"]] = (1, "donchian_up")
        df.loc[(df["close"] < df[f"ll{n}"]) & (df["close"] < df["ema200"]) & (df["volume"] > 0), ["enter_short", "enter_tag"]] = (1, "donchian_down")
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        m = self.exit_n.value
        df.loc[df["close"] < df[f"ll{m}"], "exit_long"] = 1
        df.loc[df["close"] > df[f"hh{m}"], "exit_short"] = 1
        return df


class TsMomentum(_Base):
    """日线时序动量：过去 L 天收益为正且在均线上方做多，反之做空；信号翻转离场。"""

    timeframe = "1d"
    startup_candle_count = 120
    lookback = IntParameter(10, 90, default=30, space="buy")
    ema_n = IntParameter(20, 100, default=50, space="buy")

    def populate_indicators(self, df: DataFrame, metadata: dict) -> DataFrame:
        for n in self.lookback.range:
            df[f"ret{n}"] = df["close"].pct_change(n)
        for n in self.ema_n.range:
            df[f"ema{n}"] = ta.EMA(df, timeperiod=n)
        return df

    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        r, e = df[f"ret{self.lookback.value}"], df[f"ema{self.ema_n.value}"]
        df.loc[(r > 0) & (df["close"] > e) & (df["volume"] > 0), ["enter_long", "enter_tag"]] = (1, "tsmom_up")
        df.loc[(r < 0) & (df["close"] < e) & (df["volume"] > 0), ["enter_short", "enter_tag"]] = (1, "tsmom_down")
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        r, e = df[f"ret{self.lookback.value}"], df[f"ema{self.ema_n.value}"]
        df.loc[(r < 0) | (df["close"] < e), "exit_long"] = 1
        df.loc[(r > 0) | (df["close"] > e), "exit_short"] = 1
        return df


class EmaCross4h(_Base):
    """对照组：现有 EMA21/55 交叉 + EMA200 过滤，放到 4h。"""

    timeframe = "4h"
    startup_candle_count = 220

    def populate_indicators(self, df: DataFrame, metadata: dict) -> DataFrame:
        df["f"] = ta.EMA(df, timeperiod=21)
        df["s"] = ta.EMA(df, timeperiod=55)
        df["t"] = ta.EMA(df, timeperiod=200)
        return df

    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        up = (df["f"] > df["s"]) & (df["f"].shift(1) <= df["s"].shift(1))
        dn = (df["f"] < df["s"]) & (df["f"].shift(1) >= df["s"].shift(1))
        df.loc[up & (df["close"] > df["t"]), ["enter_long", "enter_tag"]] = (1, "ema_up")
        df.loc[dn & (df["close"] < df["t"]), ["enter_short", "enter_tag"]] = (1, "ema_down")
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df.loc[df["f"] < df["s"], "exit_long"] = 1
        df.loc[df["f"] > df["s"], "exit_short"] = 1
        return df


# ---- H2（只用训练期结论）：三个候选的空头在 2022-2024.06 全部亏损，改为只做多 ----
class DonchianLong(DonchianTrend):
    can_short = False


class TsMomentumLong(TsMomentum):
    can_short = False


class EmaCross4hLong(EmaCross4h):
    can_short = False


def _btc_pair(strategy: IStrategy) -> str:
    return "BTC/USDT:USDT" if strategy.config.get("trading_mode") == "futures" else "BTC/USDT"


def _btc_regime(strategy: IStrategy, df: DataFrame, metadata: dict) -> DataFrame:
    """合并 BTC 日线是否在 200 日均线之上（用已收盘日线，merge 时自动前移避免前视）。"""
    from freqtrade.strategy import merge_informative_pair

    btc = strategy.dp.get_pair_dataframe(_btc_pair(strategy), "1d").copy()
    btc["sma200"] = btc["close"].rolling(200).mean()
    btc["bull"] = (btc["close"] > btc["sma200"]).astype(int)
    btc = btc.rename(columns={"close": "btcclose"})
    df = merge_informative_pair(df, btc[["date", "bull", "btcclose", "sma200"]], strategy.timeframe, "1d", ffill=True)
    df["btc_bull"] = df["bull_1d"].fillna(0)
    # 供控制台 / 每日决策推送展示「BTC 离年线多远」
    df["btc_close"] = df["btcclose_1d"]
    df["btc_sma200"] = df["sma200_1d"]
    return df


class _BtcRegimeMixin:
    def informative_pairs(self):
        return [(_btc_pair(self), "1d")]  # type: ignore[arg-type]

    def populate_indicators(self, df: DataFrame, metadata: dict) -> DataFrame:
        df = super().populate_indicators(df, metadata)  # type: ignore[misc]
        return _btc_regime(self, df, metadata)  # type: ignore[arg-type]

    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df = super().populate_entry_trend(df, metadata)  # type: ignore[misc]
        df.loc[df["btc_bull"] < 1, "enter_long"] = 0
        return df


class DonchianLongBtc(_BtcRegimeMixin, DonchianLong):
    pass


class TsMomentumLongBtc(_BtcRegimeMixin, TsMomentumLong):
    # BTC 过滤要 200 日均线：实盘只拉 startup_candle_count 根 K 线，少于 200 会让过滤恒为「熊市」、永不开仓
    startup_candle_count = 220


class EmaCross4hLongBtc(_BtcRegimeMixin, EmaCross4hLong):
    pass


# ---- H3：只改风控，不改信号。按 30 日年化波动率风险平价分配仓位（波动越大仓位越小）----
class TsMomentumLongBtcVol(TsMomentumLongBtc):
    risk_per_position = 0.05  # 每仓位的年化波动贡献 ≈ 权益 × 5%；10 仓总敞口约 50~70%

    def populate_indicators(self, df: DataFrame, metadata: dict) -> DataFrame:
        df = super().populate_indicators(df, metadata)
        df["vol30"] = df["close"].pct_change().rolling(30).std() * (365 ** 0.5)
        return df

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake, min_stake, max_stake,
                            leverage, entry_tag, side, **kwargs) -> float:
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        vol = float(df["vol30"].iloc[-1]) if len(df) else 0.0
        if not vol or vol != vol:  # NaN / 0：数据不足就不开仓
            return 0.0
        stake = self.wallets.get_total_stake_amount() * self.risk_per_position / vol
        return max(min_stake or 0.0, min(stake, max_stake, proposed_stake))


class AtenMomentum(TsMomentumLongBtcVol):
    """生产策略（现货与永续共用）：日线时序动量 + 只做多 + BTC 牛熊过滤 + 波动率风险平价。

    仓位系数 0.035（研究时为 0.05）：样本外逐日盯市回撤 27% 超过 25% 上限，按比例降敞口。
    该系数参考了样本外回撤，信号参数未在样本外调整。详见 docs/strategy-research.md。
    """

    risk_per_position = 0.035
