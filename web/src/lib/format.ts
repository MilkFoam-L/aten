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
