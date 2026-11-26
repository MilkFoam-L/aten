"""Aten → QQ 群推送服务（仅标准库）。消息格式对齐 Quanti，文案见 messages.py。

* POST /hook/<bot>  接收 Freqtrade webhook：开平仓成交、撤单、启动、异常。
  成交时现取「触发信号的那根日线」的指标数值和账户状态，写清做了什么、按什么规则、数值多少。
* 每 60 秒探活各机器人，连续 OFFLINE_AFTER 次失败告警「离线」，恢复后告警「已恢复」。
* 每天 ATEN_DAILY_REPORT_HOUR:15（北京时间，默认 08:15，日线收盘下单之后）推「每日决策」：
  市场状态、当日操作、各币信号与判定原因、账户与持仓、体检——空仓时也说明原因。
* 同类告警 10 分钟内只发一次（对齐 Quanti 的告警去抖）。

推送走 QQ 机器人（OneBot）的 Aten 专用推送入口；目标群由机器人侧配置决定，这里无法指定。
推送失败只记日志，绝不影响交易。环境变量见 .env.example。
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

import messages as msg

log = logging.getLogger("aten-notifier")
TZ = ZoneInfo("Asia/Shanghai")
MAX_MESSAGE = 3500
OFFLINE_AFTER = 5  # 连续探活失败次数（每分钟一次）。OKX 永续启动要 1~2 分钟初始化，阈值低了会误报
ALERT_DEDUPE_SEC = 600


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def bots() -> dict[str, str]:
    """ATEN_BOTS=spot=http://127.0.0.1:18701,futures=http://127.0.0.1:18702"""
    out = {}
    for item in env("ATEN_BOTS", "spot=http://spot:8080,futures=http://futures:8080").split(","):
        name, _, url = item.partition("=")
        if name and url:
            out[name.strip()] = url.strip().rstrip("/")
    return out


# ---------------- 推送 ----------------
def push(title: str, message: str, event_id: str | None = None) -> bool:
    url, token = env("ATEN_QQ_PUSH_URL"), env("ATEN_QQ_PUSH_TOKEN")
    if not (url and token):
        log.info("QQ 推送未配置，跳过：%s", title)
        return False
    if not (url.startswith("https://") or url.startswith("http://127.0.0.1")):
        log.warning("ATEN_QQ_PUSH_URL 只允许 https 或本机回环地址")
        return False
    body = {"token": token, "title": title[:200], "message": message[:MAX_MESSAGE]}
    if event_id:
        body["event_id"] = event_id[:100]
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status == 202
    except (urllib.error.URLError, TimeoutError) as e:
        log.warning("QQ 推送失败：%s %s", title, getattr(e, "code", type(e).__name__))
        return False
    log.info("QQ 推送%s：%s", "成功" if ok else "被拒", title)
    return ok


_last_alert: dict[str, float] = {}
_alert_lock = threading.Lock()


def alert(key: str, title: str, message: str) -> bool:
    """告警去抖：同一 key 在 ALERT_DEDUPE_SEC 内只发一次。"""
    with _alert_lock:
        now = time.monotonic()
        if now - _last_alert.get(key, -1e9) < ALERT_DEDUPE_SEC:
            log.info("告警去抖，跳过：%s", title)
            return False
        _last_alert[key] = now
    return push(title, message)


# ---------------- Freqtrade API ----------------
class Api:
    def __init__(self, base: str):
        self.base = base
        self.token = ""

    def _req(self, path: str, method: str = "GET", auth: str | None = None):
        req = urllib.request.Request(f"{self.base}/api/v1/{path}", method=method)
        req.add_header("Authorization", auth or f"Bearer {self.token}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())

    def get(self, path: str):
        if not self.token:
            self.login()
        try:
            return self._req(path)
        except urllib.error.HTTPError as e:
            if e.code != 401:
                raise
            self.login()
            return self._req(path)

    def login(self) -> None:
        cred = f"{env('FREQTRADE__API_SERVER__USERNAME')}:{env('FREQTRADE__API_SERVER__PASSWORD')}"
        basic = "Basic " + base64.b64encode(cred.encode()).decode()
        self.token = self._req("token/login", "POST", basic)["access_token"]

    def ping(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base}/api/v1/ping", timeout=5) as resp:
                return resp.status == 200
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            return False


class State:
    def __init__(self):
        self.apis = {name: Api(url) for name, url in bots().items()}
        self.live: dict[str, bool] = {}
        self.failures: dict[str, int] = {}
        self.down: set[str] = set()


STATE = State()


def label(bot: str) -> str:
    return msg.BOT_LABEL.get(bot, bot)


def last_signal(api: Api, pair: str, timeframe: str) -> dict | None:
    """策略对该币最新一根已收盘 K 线的分析结果（Freqtrade 只返回已收盘的 K 线）。"""
    d = api.get(f"pair_candles?pair={urllib.parse.quote(pair, safe='')}&timeframe={timeframe}&limit=2")
    if not d.get("data"):
        return None
    return dict(zip(d["columns"], d["data"][-1]))


def account(api: Api, cfg: dict) -> dict:
    bal, cnt = api.get("balance"), api.get("count")
    return {"equity": float(bal.get("total") or 0), "open": cnt.get("current", 0), "max": int(cfg.get("max_open_trades") or 0)}


def context(bot: str, pair: str | None) -> dict:
    """成交消息的上下文：模式、策略、风控参数、信号数值、账户。任何一项取不到都不影响推送。"""
    ctx: dict = {"now": datetime.now(TZ), "live": STATE.live.get(bot, False)}
    api = STATE.apis[bot]
    try:
        cfg = api.get("show_config")
        STATE.live[bot] = ctx["live"] = not cfg.get("dry_run", True)
        ctx.update(strategy=cfg.get("strategy"), stoploss=cfg.get("stoploss"),
                   risk=msg.STRATEGY_RISK.get(cfg.get("strategy") or ""))
        ctx["account"] = account(api, cfg)
        if pair:
            ctx["signal"] = last_signal(api, pair, cfg["timeframe"])
    except Exception as e:  # noqa: BLE001 - 上下文是锦上添花
        log.warning("读取 %s 上下文失败：%s", bot, e)
    return ctx


def handle_event(bot: str, m: dict) -> None:
    kind = m.get("type", "")
    if kind in ("entry_fill", "exit_fill", "entry_cancel", "exit_cancel"):
        ctx = context(bot, m.get("pair"))
        make = {"entry_fill": msg.entry_message, "exit_fill": msg.exit_message}.get(kind, msg.cancel_message)
        push(*make(bot, m, ctx))
    elif kind == "startup":
        if not str(m.get("status", "")).startswith("*Exchange"):
            return  # Freqtrade 启动时发多条 startup，只用交易所那条触发一次
        api = STATE.apis[bot]
        cfg = None
        try:
            cfg = {**api.get("show_config"), "capital": api.get("balance").get("total")}
            STATE.live[bot] = not cfg.get("dry_run", True)
        except Exception as e:  # noqa: BLE001
            log.warning("启动消息读取配置失败：%s", e)
        push(*msg.startup_message(bot, cfg, STATE.live.get(bot, False)))
    elif kind in ("exception", "warning"):
        text = str(m.get("status", ""))
        if "Dry run is enabled" in text:
            return
        alert(f"{bot}:{kind}:{text[:80]}", *msg.alert_message(bot, kind, text, STATE.live.get(bot, False)))


# ---------------- 每日决策 ----------------
def classify(held: bool, bull: bool, ret, close, ema) -> tuple[str, str]:
    """与 AtenMomentum 规则一致（web/src/components/signal-board.tsx 同一口径）。"""
    if ret is None or ema is None:
        return "数据不足", ""
    if held:
        if ret < 0:
            return "离场信号", "30 日涨幅转负"
        if close < ema:
            return "离场信号", "跌破 EMA50"
        return "持有", "趋势延续"
    if not bull:
        return "观望", "BTC 熊市过滤"
    if ret <= 0:
        return "观望", "30 日涨幅为负"
    if close <= ema:
        return "观望", "收盘低于 EMA50"
    return "入场", "涨幅为正且在 EMA50 上方"


def signal_rows(api: Api) -> tuple[dict, list[dict], str]:
    cfg = api.get("show_config")
    held = {t["pair"] for t in api.get("status")}
    rows, btc, day = [], {}, ""
    for pair in api.get("whitelist")["whitelist"]:
        last = last_signal(api, pair, cfg["timeframe"])
        if not last:
            continue
        if not btc and last.get("btc_sma200"):
            btc = {"close": last["btc_close"], "sma": last["btc_sma200"], "bull": last.get("btc_bull") == 1}
            day = str(last.get("date", ""))[:10]
        ret, ema, close = last.get("ret30"), last.get("ema50"), last.get("close")
        state, why = classify(pair in held, btc.get("bull", False), ret, close, ema)
        rows.append({"pair": pair, "ret": ret, "gap": close / ema - 1 if ema else None, "state": state, "why": why})
    return btc, rows, day


def recent_ops(bot: str, api: Api, since_ms: float) -> list[str]:
    """过去 24 小时实际成交的开平仓，逐笔写清数量、价格、收益与原因。"""
    out = []
    trades = api.get("status") + [t for t in api.get("trades?limit=100")["trades"] if not t["is_open"]]
    for t in trades:
        short = bool(t.get("is_short"))
        if (t.get("open_timestamp") or 0) >= since_ms:
            out.append(f"{msg.open_word(bot, short)} {msg.coin(t['pair'])}（{label(bot)}）{msg.qty(t.get('amount'))} 个 "
                       f"@ {msg.price(t.get('open_rate'))}，金额 {msg.num(t.get('stake_amount'))} USDT")
        if not t["is_open"] and (t.get("close_timestamp") or 0) >= since_ms:
            out.append(f"{msg.close_word(bot, short)} {msg.coin(t['pair'])}（{label(bot)}）@ {msg.price(t.get('close_rate'))}，"
                       f"收益 {msg.pct(t.get('profit_ratio'))}（{float(t.get('profit_abs') or 0):+,.2f} USDT），"
                       f"原因 {msg.exit_reason(t.get('exit_reason'), None, t.get('initial_stop_loss_ratio'))}")
    return out


def account_summary(bot: str, api: Api) -> dict:
    try:
        cfg, bal, prof, open_ = api.get("show_config"), api.get("balance"), api.get("profit"), api.get("status")
    except Exception as e:  # noqa: BLE001
        return {"label": label(bot), "error": type(e).__name__}
    lines = []
    for t in open_:
        held = msg.hold_ms(t.get("open_timestamp"), time.time() * 1000)
        side = msg.open_word(bot, bool(t.get("is_short")))
        lines.append(f"{side} {msg.coin(t['pair'])} 成本 {msg.price(t.get('open_rate'))} 现价 {msg.price(t.get('current_rate'))}，"
                     f"浮动 {msg.pct(t.get('profit_ratio'))}（{float(t.get('profit_abs') or 0):+,.2f}），持有 {held}")
    return {"label": f"{label(bot)}·{'实盘' if not cfg.get('dry_run', True) else '模拟盘'}",
            "equity": float(bal.get("total") or 0),
            "pnl": float(prof.get("profit_all_coin") or 0), "pnl_ratio": prof.get("profit_all_ratio"),
            "open": lines, "max": int(cfg.get("max_open_trades") or 0), "state": cfg.get("state")}


def daily_report() -> tuple[str, str, str]:
    now = datetime.now(TZ)
    since = (now - timedelta(hours=24)).timestamp() * 1000
    btc, rows, day, ops, accounts, health = {}, [], "", [], [], []
    for bot, api in STATE.apis.items():
        acct = account_summary(bot, api)
        accounts.append(acct)
        if acct.get("error"):
            health.append(f"{label(bot)}机器人连接失败")
            continue
        health.append(f"{label(bot)}机器人{'运行中' if acct['state'] == 'running' else '未运行（' + str(acct['state']) + '）'}")
        try:
            ops += recent_ops(bot, api, since)
            if not rows:  # 现货与永续信号几乎一致，只展示一份
                btc, rows, day = signal_rows(api)
        except Exception as e:  # noqa: BLE001
            health.append(f"{label(bot)}信号读取失败（{type(e).__name__}）")
    expected = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    if day:
        health.insert(0, "行情数据最新" if day >= expected else f"行情数据陈旧（截至 {day}）")
    live = any(STATE.live.values())
    title, body = msg.daily_message(day or now.strftime("%Y-%m-%d"), now, live, btc, rows, ops, accounts, health)
    return title, body, f"daily:{now:%Y-%m-%d}"


def report_loop() -> None:
    hour = int(env("ATEN_DAILY_REPORT_HOUR", "8"))
    while True:
        now = datetime.now(TZ)
        # :15 —— 日线 UTC 0 点（北京 8 点）收盘后机器人约 1 分钟内下单，限价单 10 分钟超时，15 分时结果已定
        nxt = now.replace(hour=hour, minute=15, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        time.sleep((nxt - now).total_seconds())
        try:
            push(*daily_report())
        except Exception as e:  # noqa: BLE001 - 日报失败不能让线程退出
            log.exception("每日决策生成失败：%s", e)
            alert("daily-fail", "每日决策生成失败", f"错误：{type(e).__name__}\n下一步：查看 aten-notifier 日志")


def watch_loop() -> None:
    while True:
        for name, api in STATE.apis.items():
            if api.ping():
                STATE.failures[name] = 0
                if name in STATE.down:
                    STATE.down.discard(name)
                    push(f"{label(name)}机器人已恢复", f"{msg.mode_tag(STATE.live.get(name, False))}{label(name)}机器人 API 恢复响应，交易继续")
                continue
            STATE.failures[name] = STATE.failures.get(name, 0) + 1
            if STATE.failures[name] == OFFLINE_AFTER:
                STATE.down.add(name)
                push(f"{label(name)}机器人离线",
                     f"{msg.mode_tag(STATE.live.get(name, False))}{label(name)}机器人连续 {OFFLINE_AFTER} 分钟无响应\n"
                     "影响：期间不会开平仓，交易所止损单仍有效\n下一步：服务器执行 docker compose -p aten ps 检查")
        time.sleep(60)


# ---------------- HTTP ----------------
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        parts = self.path.strip("/").split("/")
        if len(parts) != 2 or parts[0] != "hook" or parts[1] not in STATE.apis:
            self.send_error(404)
            return
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 64_000)
            m = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(m, dict):
                raise ValueError("not an object")
        except ValueError as e:
            log.warning("无法解析 webhook：%s", e)
            self.send_error(400)
            return
        self.send_response(204)
        self.end_headers()
        # 先回 204 再取上下文、推送，不让 Freqtrade 等待
        threading.Thread(target=handle_event, args=(parts[1], m), daemon=True).start()

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_error(404)

    def log_message(self, fmt, *args):
        log.debug(fmt, *args)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    host, port = env("ATEN_NOTIFIER_LISTEN", "0.0.0.0:8090").rsplit(":", 1)
    threading.Thread(target=watch_loop, daemon=True).start()
    threading.Thread(target=report_loop, daemon=True).start()
    log.info("aten-notifier 监听 %s:%s，机器人 %s", host, port, ", ".join(STATE.apis))
    ThreadingHTTPServer((host, int(port)), Handler).serve_forever()


if __name__ == "__main__":
    main()
