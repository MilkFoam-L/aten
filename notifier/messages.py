"""推送文案（纯函数，便于测试）。格式对齐 Quanti 的成交推送：

    【模拟盘·非真实交易】买入 SOL/USDT · 现货
    11/26 08:01 成交：3.2145 个 @ 150.23，金额 482.90 USDT
    仓位：占权益 9.7%（按 30 日年化波动率 36% 风险平价：3.5% ÷ 36%）
    原因：30 日涨幅 +12.3%，收盘高于 EMA50 +6.5%；BTC 在 200 日均线上方 +4.2% · AtenMomentum 日线动量

每条都写清「做了什么、按什么规则、数值是多少」，不写「信号向上」这类笼统词。
"""

from __future__ import annotations

from datetime import datetime

BOT_LABEL = {"spot": "现货", "futures": "永续"}
STRATEGY_LABEL = {
    "AtenMomentum": "AtenMomentum 日线动量",
}
# 与 user_data/strategies/research.py 中 AtenMomentum.risk_per_position 保持一致（API 不暴露该属性）
STRATEGY_RISK = {"AtenMomentum": 0.035}
STRATEGY_RULES = {
    "AtenMomentum": "30 日涨幅 > 0 且收盘在 EMA50 上方、BTC 在 200 日均线上方时开多；"
                    "涨幅转负或跌破 EMA50 时平仓；只做多，按波动率分配仓位",
}


def num(v, d: int = 2) -> str:
    try:
        return f"{float(v):,.{d}f}"
    except (TypeError, ValueError):
        return "—"


def price(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    return num(f, 2 if f >= 100 else 4 if f >= 1 else 6)


def qty(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{f:,.6f}".rstrip("0").rstrip(".") if f < 1000 else num(f, 2)


def pct(ratio, d: int = 2) -> str:
    try:
        return f"{float(ratio) * 100:+.{d}f}%"
    except (TypeError, ValueError):
        return "—"


def coin(pair: str) -> str:
    return pair.split("/")[0]


def pair_label(pair: str) -> str:
    return pair.split(":")[0]


def mode_tag(live: bool) -> str:
    return "【实盘】" if live else "【模拟盘·非真实交易】"


def strategy_label(name: str | None) -> str:
    return STRATEGY_LABEL.get(name or "", name or "未知策略")


def open_word(bot: str, short: bool) -> str:
    if bot == "spot":
        return "买入"
    return "开空" if short else "开多"


def close_word(bot: str, short: bool) -> str:
    if bot == "spot":
        return "卖出"
    return "平空" if short else "平多"


def hold_text(open_date: str | None, close_date: str | None) -> str:
    try:
        h = (datetime.fromisoformat(str(close_date)) - datetime.fromisoformat(str(open_date))).total_seconds() / 3600
    except (TypeError, ValueError):
        return ""
    return f"{h / 24:.1f} 天" if h >= 48 else f"{h:.0f} 小时"


def hold_ms(open_ms, close_ms) -> str:
    try:
        h = (float(close_ms) - float(open_ms)) / 3_600_000
    except (TypeError, ValueError):
        return ""
    return f"{h / 24:.1f} 天" if h >= 48 else f"{h:.0f} 小时"


def _vs(value: float, ref: float, above: str, below: str) -> str:
    gap = value / ref - 1
    return f"{above if gap >= 0 else below} {pct(gap, 1)}"


def entry_reason(sig: dict | None) -> str:
    """开仓时那根已收盘日线的数值 → 原因。措辞按实际正负，不预设「高于」。sig 缺失时只写策略名。"""
    if not sig or sig.get("ret30") is None:
        return ""
    parts = [f"30 日涨幅 {pct(sig['ret30'], 1)}"]
    if sig.get("ema50"):
        parts.append(f"收盘 {price(sig['close'])}，EMA50 {price(sig['ema50'])}，"
                     + _vs(sig["close"], sig["ema50"], "高于均线", "低于均线"))
    text = "；".join(parts)
    if sig.get("btc_sma200"):
        text += "；BTC " + _vs(sig["btc_close"], sig["btc_sma200"], "在 200 日均线上方", "在 200 日均线下方")
    return text


def exit_reason(reason: str | None, sig: dict | None, stoploss: float | None) -> str:
    if reason == "exit_signal" and sig and sig.get("ret30") is not None:
        if sig["ret30"] < 0:
            return f"信号离场：30 日涨幅转负 {pct(sig['ret30'], 1)}"
        if sig.get("ema50") and sig["close"] < sig["ema50"]:
            return (f"信号离场：收盘 {price(sig['close'])} 跌破 EMA50 {price(sig['ema50'])}"
                    f"（{pct(sig['close'] / sig['ema50'] - 1, 1)}）")
        return "信号离场"
    stop = f"（亏损达 {pct(stoploss, 0)}）" if stoploss else ""
    return {
        "exit_signal": "信号离场",
        "stop_loss": f"触发止损{stop}",
        "stoploss_on_exchange": f"交易所止损单成交{stop}",
        "trailing_stop_loss": "触发移动止损",
        "roi": "达到止盈目标",
        "force_exit": "控制台手动平仓",
        "emergency_exit": "紧急平仓",
        "liquidation": "被交易所强制平仓",
    }.get(reason or "", reason or "未知原因")


def sizing_text(stake: float, equity: float, sig: dict | None, risk: float | None) -> str:
    share = stake / equity if equity else 0
    text = f"占权益 {share:.1%}"
    vol = (sig or {}).get("vol30")
    if vol and risk:
        target = risk / vol
        text += f"（按 30 日年化波动率 {vol:.0%} 风险平价：{risk:.1%} ÷ {vol:.0%} = {target:.1%}"
        text += "，受可用资金上限约束）" if share < target - 0.005 else "）"
    return text


def account_line(acct: dict | None) -> str:
    if not acct:
        return ""
    return f"账户：权益 {num(acct.get('equity'))} USDT，持仓 {acct.get('open', 0)}/{acct.get('max', '—')}"


def entry_message(bot: str, m: dict, ctx: dict) -> tuple[str, str, str]:
    short = str(m.get("direction", "")).lower() == "short"
    word = open_word(bot, short)
    lev = float(m.get("leverage") or 1)
    stake = float(m.get("stake_amount") or 0)
    acct = ctx.get("account") or {}
    sig = ctx.get("signal")
    lines = [
        f"{mode_tag(ctx.get('live', False))}{word} {pair_label(m['pair'])} · {BOT_LABEL.get(bot, bot)}",
        f"{ctx['now']:%m/%d %H:%M} 成交：{qty(m.get('amount'))} 个 @ {price(m.get('open_rate'))}，"
        f"金额 {num(stake)} USDT" + (f"（{lev:g} 倍杠杆）" if bot != "spot" else ""),
    ]
    if acct.get("equity"):
        lines.append("仓位：" + sizing_text(stake, float(acct["equity"]), sig, ctx.get("risk")))
    reason = entry_reason(sig)
    lines.append("原因：" + " · ".join(x for x in (reason, strategy_label(ctx.get("strategy"))) if x))
    if acct:
        lines.append(account_line(acct))
    return f"机器人{word} {coin(m['pair'])}", "\n".join(lines), f"{bot}:entry:{m.get('trade_id')}"


def exit_message(bot: str, m: dict, ctx: dict) -> tuple[str, str, str]:
    short = str(m.get("direction", "")).lower() == "short"
    word = close_word(bot, short)
    profit = float(m.get("profit_amount") or 0)
    verdict = "盈" if profit > 0 else "亏" if profit < 0 else "平"
    held = hold_text(m.get("open_date"), m.get("close_date"))
    lines = [
        f"{mode_tag(ctx.get('live', False))}{word} {pair_label(m['pair'])} · {BOT_LABEL.get(bot, bot)}",
        f"{ctx['now']:%m/%d %H:%M} 成交：{qty(m.get('amount'))} 个 @ {price(m.get('close_rate'))}"
        f"（开仓价 {price(m.get('open_rate'))}" + (f"，持有 {held}）" if held else "）"),
        f"这笔收益 {pct(m.get('profit_ratio'))}，模拟账户盈亏 {profit:+,.2f} USDT（已扣手续费）"
        if not ctx.get("live") else f"这笔收益 {pct(m.get('profit_ratio'))}，盈亏 {profit:+,.2f} USDT（已扣手续费）",
        "原因：" + exit_reason(m.get("exit_reason"), ctx.get("signal"), ctx.get("stoploss"))
        + " · " + strategy_label(ctx.get("strategy")),
    ]
    if ctx.get("account"):
        lines.append(account_line(ctx["account"]))
    eid = f"{bot}:exit:{m.get('trade_id')}:{str(m.get('close_date', ''))[:19]}"
    return (f"机器人{word} {coin(m['pair'])} {verdict} {pct(m.get('profit_ratio'))}", "\n".join(lines),
            eid.replace(" ", "T"))


def cancel_message(bot: str, m: dict, ctx: dict) -> tuple[str, str, str]:
    short = str(m.get("direction", "")).lower() == "short"
    entry = m.get("type") == "entry_cancel"
    word = open_word(bot, short) if entry else close_word(bot, short)
    lines = [
        f"{mode_tag(ctx.get('live', False))}{word}单已撤销 {pair_label(m['pair'])} · {BOT_LABEL.get(bot, bot)}",
        f"{ctx['now']:%m/%d %H:%M} 限价单 {price(m.get('order_rate'))} 未在时限内成交",
        f"撤单原因：{m.get('reason') or '超时'}",
        "后续：" + ("本次不开仓，下一根日线收盘后重新判断" if entry else "机器人会重新挂出平仓单"),
    ]
    return f"机器人{word}单撤销 {coin(m['pair'])}", "\n".join(lines), f"{bot}:{m.get('type')}:{m.get('trade_id')}:{ctx['now']:%Y%m%d%H%M}"


def startup_message(bot: str, cfg: dict | None, live: bool) -> tuple[str, str]:
    label = BOT_LABEL.get(bot, bot)
    if not cfg:
        return f"{label}机器人已启动", f"{mode_tag(live)}{label}机器人已启动（配置暂未读到）"
    stop = cfg.get("stoploss")
    lines = [
        f"{mode_tag(live)}{label}机器人已启动，开始按策略自动交易",
        f"策略：{strategy_label(cfg.get('strategy'))}，{cfg.get('timeframe')} 周期",
        f"规则：{STRATEGY_RULES.get(cfg.get('strategy') or '', '见策略文件')}",
        f"资金：{num(cfg.get('capital'))} USDT，最多 {int(cfg.get('max_open_trades') or 0)} 个持仓，"
        f"单仓止损 {pct(stop, 0)}" + ("，逐仓 1 倍" if cfg.get("trading_mode") == "futures" else ""),
        f"交易所：{str(cfg.get('exchange', '')).upper()}，每天北京时间 08:00 日线收盘后决策",
    ]
    return f"{label}机器人已启动", "\n".join(lines)


def alert_message(bot: str, kind: str, text: str, live: bool) -> tuple[str, str]:
    label = BOT_LABEL.get(bot, bot)
    title = f"{label}机器人{'异常' if kind == 'exception' else '提醒'}"
    return title, f"{mode_tag(live)}{title}\n内容：{text[:1200]}\n下一步：登录控制台「机器人」页或服务器日志查看"


def signal_line(r: dict) -> str:
    gap = f" / {pct(r['gap'], 1)}" if r.get("gap") is not None else ""
    return f"{coin(r['pair'])} {pct(r.get('ret'), 1)}{gap} → {r['state']}" + (f"：{r['why']}" if r.get("why") else "")


def daily_message(day: str, now: datetime, live: bool, btc: dict, rows: list[dict], ops: list[str],
                  accounts: list[dict], health: list[str]) -> tuple[str, str]:
    total = sum(a.get("equity") or 0 for a in accounts)
    pnl = sum(a.get("pnl") or 0 for a in accounts)
    change = f"（{pct(pnl / (total - pnl))}）" if total - pnl > 0 else ""
    lines = [f"{mode_tag(live)}{day[5:].replace('-', '/')} 日线（北京 {now:%m/%d} 08:00 收盘）决策结果"]
    if btc:
        gap = btc["close"] / btc["sma"] - 1
        lines.append(f"市场：BTC {num(btc['close'], 0)}，200 日均线 {num(btc['sma'], 0)}（{pct(gap, 1)}）→ "
                     + ("牛市，允许开多" if btc["bull"] else "熊市，不开新仓、持仓按离场规则处理"))
    lines.append("今日操作：" + ("无" if not ops else ""))
    lines.extend(ops)
    if rows:
        lines.append("信号（30 日涨幅 / 相对 EMA50 → 判定）：")
        lines.extend(signal_line(r) for r in rows)
    lines.append("账户：")
    for a in accounts:
        if a.get("error"):
            lines.append(f"{a['label']} 读取失败：{a['error']}")
            continue
        lines.append(f"{a['label']} {num(a['equity'])} USDT，累计 {a['pnl']:+,.2f}（{pct(a['pnl_ratio'])}），"
                     f"持仓 {len(a['open'])}/{a['max']}")
        lines.extend(f"  {t}" for t in a["open"])
    lines.append("体检：" + "；".join(health))
    return f"Aten 每日决策 {now:%m-%d} · 总权益 {num(total)}{change}", "\n".join(lines)
