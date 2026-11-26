"""Aten → QQ 群推送服务（仅标准库）。

* POST /hook/<bot>    接收 Freqtrade webhook（开平仓成交、启动、异常），格式化成中文推到 QQ 群
* 每 60 秒探活各机器人，连续 5 次失败告警「离线」，恢复后告警「已恢复」
* 每天 ATEN_DAILY_REPORT_HOUR 点（北京时间，默认 21）推日报：权益、累计/当日盈亏、持仓

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
import urllib.request
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

log = logging.getLogger("aten-notifier")
TZ = ZoneInfo("Asia/Shanghai")
MAX_MESSAGE = 3500
OFFLINE_AFTER = 5  # 连续探活失败次数（每分钟一次）

BOT_LABEL = {"spot": "现货", "futures": "永续"}
EXIT_REASON = {
    "exit_signal": "信号离场", "stop_loss": "止损", "stoploss": "止损", "trailing_stop_loss": "移动止损",
    "roi": "止盈", "force_exit": "手动平仓", "liquidation": "强平", "stoploss_on_exchange": "交易所止损",
    "emergency_exit": "紧急平仓", "custom_exit": "策略离场",
}
ENTER_TAG = {"tsmom_up": "动量向上", "tsmom_down": "动量向下", "donchian_up": "通道突破", "ema_cross_up": "均线金叉"}


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


# ---------------- 格式化 ----------------
def num(v, d: int = 2) -> str:
    try:
        return f"{float(v):,.{d}f}"
    except (TypeError, ValueError):
        return str(v)


def price(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return num(f, 2 if f >= 1000 else 4 if f >= 1 else 6)


def pct(ratio) -> str:
    try:
        r = float(ratio) * 100
    except (TypeError, ValueError):
        return "—"
    return f"{r:+.2f}%"


def pair_label(pair: str) -> str:
    return pair.split(":")[0]


def mode_label(bot: str) -> str:
    return "实盘" if STATE.live.get(bot) else "模拟盘"


def format_event(bot: str, m: dict) -> tuple[str, str, str | None] | None:
    """Freqtrade webhook 负载 → (标题, 正文, 去重 ID)；不关心的类型返回 None。"""
    kind = m.get("type", "")
    where = f"{BOT_LABEL.get(bot, bot)}·{mode_label(bot)}"
    short = str(m.get("direction", "")).lower() == "short"
    side = "空" if short else "多"
    if kind == "entry_fill":
        lev = float(m.get("leverage") or 1)
        tag = ENTER_TAG.get(m.get("enter_tag") or "", m.get("enter_tag") or "—")
        return (
            f"开{side} {pair_label(m['pair'])}",
            f"    成交价 {price(m.get('open_rate'))}\n"
            f"    仓位 {num(m.get('stake_amount'))} USDT · {lev:g}x\n"
            f"    信号 {tag}\n"
            f"    {where} · #{m.get('trade_id')}",
            f"{bot}:entry:{m.get('trade_id')}",
        )
    if kind == "exit_fill":
        profit = float(m.get("profit_amount") or 0)
        verdict = "盈" if profit > 0 else "亏" if profit < 0 else "平"
        reason = EXIT_REASON.get(m.get("exit_reason") or "", m.get("exit_reason") or "—")
        held = ""
        try:
            o = datetime.fromisoformat(str(m["open_date"]))
            c = datetime.fromisoformat(str(m["close_date"]))
            h = (c - o).total_seconds() / 3600
            held = f"\n    持有 {h / 24:.1f} 天" if h >= 48 else f"\n    持有 {h:.0f} 小时"
        except (KeyError, ValueError):
            pass
        return (
            f"平{side} {pair_label(m['pair'])} {verdict} {pct(m.get('profit_ratio'))}",
            f"    {price(m.get('open_rate'))} → {price(m.get('close_rate'))}\n"
            f"    盈亏 {profit:+,.2f} USDT\n"
            f"    原因 {reason}{held}\n"
            f"    {where} · #{m.get('trade_id')}",
            f"{bot}:exit:{m.get('trade_id')}:{m.get('close_date', '')}"[:100].replace(" ", "T").replace("+", "Z"),
        )
    if kind == "startup":
        text = str(m.get("status", ""))
        if not text.startswith("*Exchange"):
            return None  # 启动时有多条 startup，只推交易所那条
        return (f"{BOT_LABEL.get(bot, bot)}机器人已启动", f"    模式 {mode_label(bot)}\n    {text.replace('*', '').replace('`', '')[:600]}", None)
    if kind in ("exception", "liquidation_warning"):
        return (f"{BOT_LABEL.get(bot, bot)}机器人异常", f"    {str(m.get('status') or m)[:1500]}\n    下一步：登录控制台查看日志", None)
    if kind == "warning":
        text = str(m.get("status", ""))
        if "Dry run is enabled" in text:
            return None
        return (f"{BOT_LABEL.get(bot, bot)}机器人提醒", f"    {text[:1500]}", None)
    return None


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


def refresh_mode() -> None:
    for name, api in STATE.apis.items():
        try:
            STATE.live[name] = not api.get("show_config").get("dry_run", True)
        except Exception as e:  # noqa: BLE001 - 机器人可能未就绪
            log.debug("show_config %s 失败：%s", name, e)


def watch_loop() -> None:
    """探活：连续 5 次失败才告警。OKX 永续启动要初始化 500+ 合约杠杆档位，约 1~2 分钟不响应，阈值低了会误报。"""
    while True:
        for name, api in STATE.apis.items():
            if api.ping():
                STATE.failures[name] = 0
                if name in STATE.down:
                    STATE.down.discard(name)
                    push(f"{BOT_LABEL.get(name, name)}机器人已恢复", "    API 恢复响应，交易继续。")
                continue
            STATE.failures[name] = STATE.failures.get(name, 0) + 1
            if STATE.failures[name] == OFFLINE_AFTER:
                STATE.down.add(name)
                push(f"{BOT_LABEL.get(name, name)}机器人离线",
                     f"    连续 {OFFLINE_AFTER} 分钟无响应，持仓的止损可能无法执行。\n    下一步：登录服务器 docker compose ps 检查")
        refresh_mode()
        time.sleep(60)


def daily_report() -> tuple[str, str]:
    lines = []
    total = 0.0
    for name, api in STATE.apis.items():
        label = f"{BOT_LABEL.get(name, name)}·{mode_label(name)}"
        try:
            bal, prof, open_ = api.get("balance"), api.get("profit"), api.get("status")
            day = api.get("daily?timescale=1")["data"][0]
        except Exception as e:  # noqa: BLE001
            lines.append(f"{label}\n    读取失败：{type(e).__name__}")
            continue
        total += float(bal.get("total") or 0)
        lines.append(
            f"{label}\n"
            f"    权益 {num(bal.get('total'))} USDT\n"
            f"    今日已实现 {float(day.get('abs_profit') or 0):+,.2f}\n"
            f"    累计 {float(prof.get('profit_all_coin') or 0):+,.2f}（{pct(prof.get('profit_all_ratio'))}）"
            f" · 胜率 {float(prof.get('winrate') or 0) * 100:.0f}%"
        )
        for t in open_[:8]:
            side = "空" if t.get("is_short") else "多"
            lines.append(f"    {side} {pair_label(t['pair'])} {pct(t.get('profit_ratio'))}")
        if len(open_) > 8:
            lines.append(f"    …共 {len(open_)} 个持仓")
    title = f"Aten 日报 {datetime.now(TZ):%m-%d} · 总权益 {num(total)}"
    return title, "\n".join(lines)


def report_loop() -> None:
    hour = int(env("ATEN_DAILY_REPORT_HOUR", "21"))
    while True:
        now = datetime.now(TZ)
        nxt = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        time.sleep((nxt - now).total_seconds())
        title, msg = daily_report()
        push(title, msg, f"daily:{datetime.now(TZ):%Y-%m-%d}")


# ---------------- HTTP ----------------
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        parts = self.path.strip("/").split("/")
        if len(parts) != 2 or parts[0] != "hook" or parts[1] not in STATE.apis:
            self.send_error(404)
            return
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 64_000)
            msg = json.loads(self.rfile.read(n) or b"{}")
            out = format_event(parts[1], msg)
        except (ValueError, KeyError) as e:
            log.warning("无法解析 webhook：%s", e)
            self.send_error(400)
            return
        self.send_response(204)
        self.end_headers()
        if out:  # 先回 204 再推送，不让 Freqtrade 等 QQ 入口
            threading.Thread(target=push, args=out, daemon=True).start()

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
    if env("ATEN_PUSH_TEST") == "1":
        threading.Timer(5, lambda: push(*daily_report())).start()
    log.info("aten-notifier 监听 %s:%s，机器人 %s", host, port, ", ".join(STATE.apis))
    ThreadingHTTPServer((host, int(port)), Handler).serve_forever()


if __name__ == "__main__":
    main()
