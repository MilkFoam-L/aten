"""python3 -m unittest discover -s notifier -p 'test_*.py'"""
import os
import unittest
from datetime import datetime
from unittest import mock

import aten_notifier as n
import messages as msg

NOW = datetime(2026, 11, 27, 8, 1, tzinfo=n.TZ)
SIG = {"close": 150.23, "ema50": 141.1, "ret30": 0.123, "vol30": 0.36, "btc_close": 75000, "btc_sma200": 72000}


class EntryExitTests(unittest.TestCase):
    def test_spot_entry_is_specific(self):
        title, body, eid = msg.entry_message("spot", {
            "pair": "SOL/USDT", "direction": "Long", "amount": "3.2145", "open_rate": "150.23",
            "stake_amount": "482.9", "leverage": "1.0", "trade_id": "12",
        }, {"now": NOW, "live": False, "strategy": "AtenMomentum", "risk": 0.035, "signal": SIG,
            "account": {"equity": 4982.0, "open": 3, "max": 10}})
        self.assertEqual(title, "机器人买入 SOL")
        lines = body.splitlines()
        self.assertEqual(lines[0], "【模拟盘·非真实交易】买入 SOL/USDT · 现货")
        self.assertEqual(lines[1], "11/27 08:01 成交：3.2145 个 @ 150.23，金额 482.90 USDT")
        self.assertIn("占权益 9.7%", lines[2])
        self.assertIn("30 日年化波动率 36%", lines[2])
        self.assertIn("30 日涨幅 +12.3%", lines[3])
        self.assertIn("收盘 150.23，EMA50 141.10，高于均线 +6.5%", lines[3])
        self.assertIn("BTC 在 200 日均线上方 +4.2%", lines[3])
        self.assertIn("AtenMomentum 日线动量", lines[3])
        self.assertEqual(lines[4], "账户：权益 4,982.00 USDT，持仓 3/10")
        self.assertEqual(eid, "spot:entry:12")

    def test_futures_exit_on_ema_break(self):
        title, body, eid = msg.exit_message("futures", {
            "pair": "SOL/USDT:USDT", "direction": "Long", "amount": "3.2145", "open_rate": "150.23",
            "close_rate": "158.03", "profit_amount": "24.61", "profit_ratio": "0.051", "exit_reason": "exit_signal",
            "trade_id": "12", "open_date": "2026-11-23 00:01:00+00:00", "close_date": "2026-11-27 00:01:00+00:00",
        }, {"now": NOW, "live": False, "strategy": "AtenMomentum", "stoploss": -0.15,
            "signal": {**SIG, "close": 158.03, "ema50": 159.2, "ret30": 0.02}})
        self.assertEqual(title, "机器人平多 SOL 盈 +5.10%")
        self.assertIn("【模拟盘·非真实交易】平多 SOL/USDT · 永续", body)
        self.assertIn("3.2145 个 @ 158.03（开仓价 150.23，持有 4.0 天）", body)
        self.assertIn("这笔收益 +5.10%，模拟账户盈亏 +24.61 USDT（已扣手续费）", body)
        self.assertIn("信号离场：收盘 158.03 跌破 EMA50 159.20（-0.7%）", body)
        self.assertRegex(eid, r"^[A-Za-z0-9._:-]+$")  # 机器人入口的 event_id 字符集

    def test_stoploss_exit_states_threshold(self):
        _, body, _ = msg.exit_message("spot", {
            "pair": "ETH/USDT", "direction": "Long", "amount": "1", "open_rate": "2000", "close_rate": "1700",
            "profit_amount": "-301", "profit_ratio": "-0.1505", "exit_reason": "stoploss_on_exchange", "trade_id": "3",
        }, {"now": NOW, "stoploss": -0.15})
        self.assertIn("原因：交易所止损单成交（亏损达 -15%）", body)

    def test_reason_wording_follows_sign(self):
        r = msg.entry_reason({**SIG, "close": 70.48, "ema50": 87.6, "btc_close": 60458, "btc_sma200": 72088})
        self.assertIn("低于均线 -19.5%", r)
        self.assertIn("在 200 日均线下方 -16.1%", r)
        self.assertNotIn("高于", r)

    def test_live_mode_tag(self):
        _, body, _ = msg.entry_message("spot", {"pair": "ETH/USDT", "direction": "Long", "amount": "1",
                                                "open_rate": "3000", "stake_amount": "3000", "trade_id": "1"},
                                       {"now": NOW, "live": True})
        self.assertTrue(body.startswith("【实盘】买入"))

    def test_entry_cancel(self):
        title, body, _ = msg.cancel_message("spot", {"type": "entry_cancel", "pair": "BNB/USDT", "direction": "Long",
                                                     "order_rate": "554.04", "reason": "Timeout", "trade_id": "5"},
                                            {"now": NOW})
        self.assertEqual(title, "机器人买入单撤销 BNB")
        self.assertIn("限价单 554.04 未在时限内成交", body)
        self.assertIn("本次不开仓", body)


class OtherMessageTests(unittest.TestCase):
    def test_startup_lists_strategy_and_capital(self):
        title, body = msg.startup_message("futures", {
            "strategy": "AtenMomentum", "timeframe": "1d", "capital": 5000, "max_open_trades": 10,
            "stoploss": -0.15, "trading_mode": "futures", "exchange": "okx"}, False)
        self.assertEqual(title, "永续机器人已启动")
        self.assertIn("资金：5,000.00 USDT，最多 10 个持仓，单仓止损 -15%，逐仓 1 倍", body)
        self.assertIn("交易所：OKX", body)
        self.assertIn("BTC 在 200 日均线上方时开多", body)

    def test_daily_bear_market(self):
        title, body = msg.daily_message("2026-11-26", NOW, False, {"close": 60458, "sma": 72088, "bull": False},
                                        [{"pair": "BTC/USDT", "ret": -0.246, "gap": -0.16, "state": "观望", "why": "BTC 熊市过滤"}],
                                        [], [{"label": "现货·模拟盘", "equity": 5000, "pnl": 0, "pnl_ratio": 0, "open": [], "max": 10}],
                                        ["行情数据最新", "现货机器人运行中"])
        self.assertEqual(title, "Aten 每日决策 11-27 · 总权益 5,000.00（+0.00%）")  # 推送当天，不是 K 线日
        self.assertIn("【模拟盘·非真实交易】11/26 日线（北京 11/27 08:00 收盘）决策结果", body)
        self.assertIn("市场：BTC 60,458，200 日均线 72,088（-16.1%）→ 熊市", body)
        self.assertIn("今日操作：无", body)
        self.assertIn("BTC -24.6% / -16.0% → 观望：BTC 熊市过滤", body)
        self.assertIn("现货·模拟盘 5,000.00 USDT，累计 +0.00（+0.00%），持仓 0/10", body)
        self.assertIn("体检：行情数据最新；现货机器人运行中", body)

    def test_classify_matches_strategy(self):
        self.assertEqual(n.classify(False, False, 0.1, 10, 9)[1], "BTC 熊市过滤")
        self.assertEqual(n.classify(False, True, 0.1, 10, 9)[0], "入场")
        self.assertEqual(n.classify(False, True, 0.1, 8, 9)[1], "收盘低于 EMA50")
        self.assertEqual(n.classify(True, False, 0.1, 10, 9)[0], "持有")  # 熊市不影响已有持仓
        self.assertEqual(n.classify(True, True, -0.01, 10, 9)[1], "30 日涨幅转负")


class PushTests(unittest.TestCase):
    def test_push_refuses_plain_http_remote(self):
        with mock.patch.dict(os.environ, {"ATEN_QQ_PUSH_URL": "http://example.com/x", "ATEN_QQ_PUSH_TOKEN": "t" * 40}):
            self.assertFalse(n.push("t", "m"))

    def test_alert_dedupes_within_window(self):
        n._last_alert.clear()
        with mock.patch.object(n, "push", return_value=True) as p:
            self.assertTrue(n.alert("k", "t", "m"))
            self.assertFalse(n.alert("k", "t", "m"))
            self.assertTrue(n.alert("other", "t", "m"))
        self.assertEqual(p.call_count, 2)


if __name__ == "__main__":
    unittest.main()
