const num = (n: number, d: number) =>
  n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })

export const money = (n: number | null | undefined, d = 2) => (n == null ? "—" : num(n, d))

export const signedMoney = (n: number | null | undefined, d = 2) =>
  n == null ? "—" : `${n > 0 ? "+" : ""}${num(n, d)}`

/** ratio 0.0123 → "+1.23%" */
export const pct = (ratio: number | null | undefined, d = 2) =>
  ratio == null ? "—" : `${ratio > 0 ? "+" : ""}${num(ratio * 100, d)}%`

/** 价格按量级自动取精度：BTC 6 万取 2 位，DOGE 0.1 取 5 位 */
export const price = (n: number | null | undefined) => {
  if (n == null) return "—"
  const d = n >= 1000 ? 2 : n >= 1 ? 4 : n >= 0.01 ? 5 : 8
  return num(n, d)
}

export const dateTime = (ms: number | null | undefined) =>
  ms == null
    ? "—"
    : new Date(ms).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false })

export const since = (ms: number) => {
  const m = Math.max(0, Math.round((Date.now() - ms) / 60000))
  if (m < 60) return `${m} 分钟`
  const h = Math.floor(m / 60)
  return h < 48 ? `${h} 小时` : `${Math.floor(h / 24)} 天`
}

/** "BTC/USDT:USDT" → "BTC/USDT" */
export const pairLabel = (pair: string) => pair.split(":")[0]

/** 与 notifier/messages.py 的 exit_reason 同一套说法 */
const EXIT_REASON: Record<string, string> = {
  exit_signal: "信号离场",
  stop_loss: "触发止损",
  stoploss_on_exchange: "交易所止损单成交",
  trailing_stop_loss: "触发移动止损",
  roi: "达到止盈目标",
  force_exit: "控制台手动平仓",
  emergency_exit: "紧急平仓",
  liquidation: "被交易所强制平仓",
}
export const exitReason = (r: string | null | undefined) => (r ? (EXIT_REASON[r] ?? r) : "—")

const ENTER_TAG: Record<string, string> = {
  tsmom_up: "30 日涨幅为正且在 EMA50 上方",
  tsmom_down: "30 日涨幅为负且在 EMA50 下方",
  donchian_up: "突破通道上轨",
  donchian_down: "跌破通道下轨",
  ema_up: "均线金叉",
  ema_down: "均线死叉",
}
export const enterTag = (t: string | null | undefined) => (t ? (ENTER_TAG[t] ?? t) : "—")
