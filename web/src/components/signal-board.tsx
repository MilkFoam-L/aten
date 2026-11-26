import { useState } from "react"
import { cn } from "cn"

import { Badge } from "@/components/ui/badge"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { BotFilter } from "@/components/bot-filter"
import { usePoll } from "@/hooks/use-poll"
import { api, type BotConfig, type BotId, type Candles, type Trade } from "@/lib/api"
import { pairLabel, pct, price } from "@/lib/format"

type State = "入场" | "持有" | "离场信号" | "观望" | "数据不足"
type Row = { pair: string; close: number; ret: number | null; gap: number | null; state: State; why: string }
type Btc = { close: number; sma: number; bull: boolean } | null

const STATE_CLASS: Record<State, string> = {
  入场: "bg-up-soft text-up",
  持有: "bg-accent text-accent-foreground",
  离场信号: "bg-warn-soft text-warn",
  观望: "bg-muted text-muted-foreground",
  数据不足: "bg-muted text-muted-foreground",
}

/** 与 AtenMomentum 规则一致（notifier/aten_notifier.py 的 signal_rows 同一口径） */
function classify(held: boolean, bull: boolean, ret: number | null, close: number, ema: number | null): [State, string] {
  if (ret == null || ema == null) return ["数据不足", ""]
  if (held) {
    if (ret < 0) return ["离场信号", "动量转负"]
    if (close < ema) return ["离场信号", "跌破 EMA50"]
    return ["持有", "趋势延续"]
  }
  if (!bull) return ["观望", "BTC 熊市过滤"]
  if (ret <= 0) return ["观望", "30 日动量为负"]
  if (close <= ema) return ["观望", "低于 EMA50"]
  return ["入场", "动量向上且在 EMA50 上方"]
}

async function loadSignals(bot: BotId): Promise<{ btc: Btc; rows: Row[]; date: string }> {
  const [cfg, open, wl] = await Promise.all([
    api<BotConfig>(bot, "show_config"),
    api<Trade[]>(bot, "status"),
    api<{ whitelist: string[] }>(bot, "whitelist"),
  ])
  const held = new Set(open.map((t) => t.pair))
  const candles = await Promise.all(
    wl.whitelist.map((p) =>
      api<Candles>(bot, `pair_candles?pair=${encodeURIComponent(p)}&timeframe=${cfg.timeframe}&limit=2`)
    )
  )
  let btc: Btc = null
  let date = ""
  const rows = wl.whitelist.flatMap((pair, i): Row[] => {
    const c = candles[i]
    if (!c.data.length) return []
    const last = Object.fromEntries(c.columns.map((k, j) => [k, c.data.at(-1)![j]])) as Record<string, number | null>
    if (!btc && last.btc_sma200 != null && last.btc_close != null) {
      btc = { close: last.btc_close, sma: last.btc_sma200, bull: last.btc_bull === 1 }
      date = String(last.date).slice(0, 10)
    }
    const close = last.close as number
    const ema = last.ema50
    const [state, why] = classify(held.has(pair), btc?.bull ?? false, last.ret30, close, ema)
    return [{ pair, close, ret: last.ret30, gap: ema ? close / ema - 1 : null, state, why }]
  })
  return { btc, rows, date }
}

export function SignalBoard() {
  const [bot, setBot] = useState<BotId>("spot")
  const sig = usePoll(() => loadSignals(bot), 5 * 60_000, [bot])
  const btc = sig.data?.btc

  return (
    <Card>
      <CardHeader className="max-sm:flex max-sm:flex-col">
        <CardTitle>今日策略信号</CardTitle>
        <CardDescription>
          {sig.data?.date ? `${sig.data.date} 日线收盘` : "日线收盘"}后自动决策，每天北京时间 08:00 执行
        </CardDescription>
        <CardAction className="max-sm:mt-2 max-sm:self-start">
          <BotFilter value={bot} onChange={(v) => setBot(v as BotId)} allowAll={false} />
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {sig.loading && !sig.data ? (
          <Skeleton className="h-64 w-full" />
        ) : sig.error && !sig.data ? (
          <p className="text-sm text-destructive">策略信号读取失败：{sig.error.message}</p>
        ) : (
          <>
            {btc && (
              <div
                className={cn(
                  "flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-lg px-3 py-2 text-sm",
                  btc.bull ? "bg-up-soft" : "bg-muted"
                )}
              >
                <span className={cn("font-medium", btc.bull ? "text-up" : "text-foreground")}>
                  {btc.bull ? "牛市 · 允许开多" : "熊市 · 不开新仓"}
                </span>
                <span className="text-muted-foreground tabular-nums">
                  BTC {price(btc.close)}，200 日均线 {price(btc.sma)}（{pct(btc.close / btc.sma - 1, 1)}）
                </span>
              </div>
            )}
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>币种</TableHead>
                  <TableHead className="text-right">收盘价</TableHead>
                  <TableHead className="text-right">30 日动量</TableHead>
                  <TableHead className="hidden text-right sm:table-cell">相对 EMA50</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead className="hidden md:table-cell">原因</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sig.data?.rows.map((r) => (
                  <TableRow key={r.pair}>
                    <TableCell className="font-medium">{pairLabel(r.pair)}</TableCell>
                    <TableCell className="text-right tabular-nums">{price(r.close)}</TableCell>
                    <TableCell className={cn("text-right tabular-nums", (r.ret ?? 0) > 0 ? "text-up" : "text-down")}>
                      {pct(r.ret, 1)}
                    </TableCell>
                    <TableCell className="hidden text-right tabular-nums text-muted-foreground sm:table-cell">
                      {pct(r.gap, 1)}
                    </TableCell>
                    <TableCell>
                      <Badge className={STATE_CLASS[r.state]}>{r.state}</Badge>
                    </TableCell>
                    <TableCell className="hidden text-xs text-muted-foreground md:table-cell">{r.why}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}
      </CardContent>
    </Card>
  )
}
