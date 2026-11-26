"""python3 -m unittest notifier/test_aten_notifier.py"""
import unittest

import aten_notifier as n


class FormatTests(unittest.TestCase):
    def test_entry_fill(self):
        title, msg, eid = n.format_event("futures", {
            "type": "entry_fill", "pair": "BTC/USDT:USDT", "direction": "Long", "open_rate": "60123.4",
            "stake_amount": "1876.5", "leverage": "1.0", "enter_tag": "tsmom_up", "trade_id": "7",
        })
        self.assertEqual(title, "开多 BTC/USDT")
        self.assertIn("60,123.40", msg)
        self.assertIn("动量向上", msg)
        self.assertIn("永续·模拟盘", msg)
        self.assertEqual(eid, "futures:entry:7")

    def test_exit_fill_loss_short(self):
        title, msg, eid = n.format_event("futures", {
            "type": "exit_fill", "pair": "SOL/USDT:USDT", "direction": "Short", "open_rate": "150",
            "close_rate": "160", "profit_amount": "-66.7", "profit_ratio": "-0.0667", "exit_reason": "stop_loss",
            "trade_id": "8", "open_date": "2026-11-20 00:00:00+00:00", "close_date": "2026-11-25 12:00:00+00:00",
        })
        self.assertEqual(title, "平空 SOL/USDT 亏 -6.67%")
        self.assertIn("止损", msg)
        self.assertIn("持有 5.5 天", msg)
        self.assertRegex(eid, r"^[A-Za-z0-9._:-]+$")  # 机器人入口的 event_id 字符集

    def test_live_mode_label(self):
        n.STATE.live["spot"] = True
        try:
            _, msg, _ = n.format_event("spot", {"type": "entry_fill", "pair": "ETH/USDT", "direction": "Long",
                                                 "open_rate": "3000", "stake_amount": "100", "trade_id": "1"})
            self.assertIn("现货·实盘", msg)
        finally:
            n.STATE.live.clear()

    def test_ignored_types(self):
        self.assertIsNone(n.format_event("spot", {"type": "entry", "pair": "x"}))
        self.assertIsNone(n.format_event("spot", {"type": "warning", "status": "Dry run is enabled. x"}))

    def test_push_refuses_plain_http_remote(self):
        import os
        os.environ.update(ATEN_QQ_PUSH_URL="http://example.com/x", ATEN_QQ_PUSH_TOKEN="t" * 40)
        try:
            self.assertFalse(n.push("t", "m"))
        finally:
            del os.environ["ATEN_QQ_PUSH_URL"], os.environ["ATEN_QQ_PUSH_TOKEN"]


class DecisionTests(unittest.TestCase):
    def test_bear_market_says_why_flat(self):
        lines = n.decision_lines({"close": 60458, "sma": 72088, "bull": False},
                                 [{"pair": "BTC/USDT", "ret": -0.25, "state": "观望", "why": "BTC 熊市过滤"}])
        self.assertIn("熊市，不开新仓", lines[0])
        self.assertIn("-16.1%", lines[0])
        self.assertIn("空仓等待", lines[1])

    def test_bull_lists_actions_and_watchlist(self):
        rows = [{"pair": "SOL/USDT:USDT", "ret": 0.12, "state": "入场", "why": "动量向上且在 EMA50 上方"},
                {"pair": "ETH/USDT:USDT", "ret": 0.05, "state": "持有", "why": "趋势延续"},
                {"pair": "DOGE/USDT:USDT", "ret": -0.1, "state": "观望", "why": "30 日动量为负"}]
        lines = n.decision_lines({"close": 80000, "sma": 70000, "bull": True}, rows)
        self.assertIn("牛市，允许开多", lines[0])
        self.assertIn("入场 SOL/USDT · 30日 +12.00%", lines[1])
        self.assertIn("持有 ETH/USDT", lines[2])
        self.assertEqual(lines[3], "    观望 1 个：DOGE")


if __name__ == "__main__":
    unittest.main()
