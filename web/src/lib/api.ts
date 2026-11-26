// Freqtrade REST API 客户端。两个机器人共用一套账号，令牌按机器人分别保存。
export const BOTS = [
  { id: "spot", label: "现货" },
  { id: "futures", label: "永续合约" },
] as const
export type BotId = (typeof BOTS)[number]["id"]

type Tokens = { access: string; refresh: string }
const tokenKey = (bot: BotId) => `aten.token.${bot}`
export const LOGOUT_EVENT = "aten:logout"

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function loadTokens(bot: BotId): Tokens | null {
  try {
    return JSON.parse(localStorage.getItem(tokenKey(bot)) ?? "null")
  } catch {
    return null
  }
}

function saveTokens(bot: BotId, tokens: Tokens | null) {
  try {
    if (tokens) localStorage.setItem(tokenKey(bot), JSON.stringify(tokens))
    else localStorage.removeItem(tokenKey(bot))
  } catch {
    // 隐私模式下 localStorage 不可用：本次会话内仍可用内存态重新登录
  }
}

export const isLoggedIn = () => BOTS.some((b) => loadTokens(b.id))

export function logout() {
  BOTS.forEach((b) => saveTokens(b.id, null))
  window.dispatchEvent(new Event(LOGOUT_EVENT))
}

const basic = (user: string, pass: string) =>
  "Basic " + btoa(String.fromCharCode(...new TextEncoder().encode(`${user}:${pass}`)))

async function errorOf(res: Response) {
  let detail = res.statusText
  try {
    const body = await res.json()
    detail = body.detail ?? body.error ?? detail
  } catch {
    // 非 JSON 错误体，保留 statusText
  }
  return new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail))
}

/** 登录所有机器人；至少一个成功即算登录成功（其余机器人可能未启动）。 */
export async function login(username: string, password: string) {
  const results = await Promise.allSettled(
    BOTS.map(async ({ id }) => {
      const res = await fetch(`/ft/${id}/api/v1/token/login`, {
        method: "POST",
        headers: { Authorization: basic(username, password) },
      })
      if (!res.ok) throw await errorOf(res)
      const d = await res.json()
      saveTokens(id, { access: d.access_token, refresh: d.refresh_token })
    })
  )
  if (results.some((r) => r.status === "fulfilled")) return
  const err = (results[0] as PromiseRejectedResult).reason
  if (err instanceof ApiError && err.status === 401) throw new ApiError(401, "用户名或密码错误")
  throw new ApiError(0, "连不上机器人，请确认 docker compose 已启动")
}

async function refresh(bot: BotId, tokens: Tokens) {
  const res = await fetch(`/ft/${bot}/api/v1/token/refresh`, {
    method: "POST",
    headers: { Authorization: `Bearer ${tokens.refresh}` },
  })
  if (!res.ok) return null
  const next = { ...tokens, access: (await res.json()).access_token }
  saveTokens(bot, next)
  return next
}

export async function api<T>(bot: BotId, path: string, init: RequestInit = {}): Promise<T> {
  const tokens = loadTokens(bot)
  if (!tokens) throw new ApiError(401, "未登录")
  const call = (t: Tokens) =>
    fetch(`/ft/${bot}/api/v1/${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers, Authorization: `Bearer ${t.access}` },
    })
  let res = await call(tokens)
  if (res.status === 401) {
    const next = await refresh(bot, tokens)
    if (!next) {
      logout()
      throw new ApiError(401, "登录已过期")
    }
    res = await call(next)
  }
  if (!res.ok) throw await errorOf(res)
  return res.json()
}

export const post = <T>(bot: BotId, path: string, body?: unknown) =>
  api<T>(bot, path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) })

// ---- 响应类型（只声明界面用到的字段） ----
export type BotConfig = {
  bot_name: string
  state: "running" | "stopped" | "paused" | string
  dry_run: boolean
  trading_mode: "spot" | "futures" | string
  margin_mode: string
  exchange: string
  strategy: string
  timeframe: string
  stake_currency: string
  stake_amount: string | number
  max_open_trades: number
  stoploss: number
  minimal_roi: Record<string, number>
  trailing_stop: boolean
  version: string
}

export type Trade = {
  trade_id: number
  pair: string
  is_open: boolean
  is_short: boolean
  leverage: number
  amount: number
  stake_amount: number
  open_rate: number
  close_rate: number | null
  current_rate?: number
  open_timestamp: number
  close_timestamp: number | null
  profit_ratio: number | null
  profit_abs: number | null
  stop_loss_abs: number | null
  liquidation_price: number | null
  enter_tag: string | null
  exit_reason: string | null
}

export type Profit = {
  profit_all_coin: number
  profit_all_ratio: number
  profit_closed_coin: number
  closed_trade_count: number
  winning_trades: number
  losing_trades: number
  winrate: number
  max_drawdown: number
  profit_factor: number | null
}

export type Balance = { total: number; stake: string; starting_capital: number }
export type Daily = { data: { date: string; abs_profit: number; trade_count: number }[] }
export type Candles = { columns: string[]; data: (string | number | null)[][]; timeframe: string }

export type Snapshot = {
  bot: BotId
  config: BotConfig
  profit: Profit
  balance: Balance
  open: Trade[]
}

export async function snapshot(bot: BotId): Promise<Snapshot> {
  const [config, profit, balance, open] = await Promise.all([
    api<BotConfig>(bot, "show_config"),
    api<Profit>(bot, "profit"),
    api<Balance>(bot, "balance"),
    api<Trade[]>(bot, "status"),
  ])
  return { bot, config, profit, balance, open }
}

/** 并行取所有机器人；离线的机器人返回 error 而不是让整页失败。 */
export async function allBots<T>(fn: (bot: BotId) => Promise<T>) {
  const settled = await Promise.allSettled(BOTS.map((b) => fn(b.id)))
  return BOTS.map((b, i) => {
    const r = settled[i]
    return r.status === "fulfilled"
      ? { bot: b.id, data: r.value, error: null }
      : { bot: b.id, data: null, error: r.reason as Error }
  })
}

export const botLabel = (bot: BotId) => BOTS.find((b) => b.id === bot)!.label
