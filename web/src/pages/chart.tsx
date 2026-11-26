import { useState } from "react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { BotFilter } from "@/components/bot-filter"
import { CandleChart } from "@/components/candle-chart"
import { usePoll } from "@/hooks/use-poll"
import { api, type BotId, type Candles, type Trade } from "@/lib/api"
import { pairLabel, price } from "@/lib/format"

export function ChartPage() {
  const [bot, setBot] = useState<BotId>("spot")
  const [picked, setPicked] = useState<string | null>(null)
  const wl = usePoll(() => api<{ whitelist: string[] }>(bot, "whitelist"), 60_000, [bot])
  const pairs = wl.data?.whitelist ?? []
  const pair = picked && pairs.includes(picked) ? picked : pairs[0]

  const view = usePoll(
    async () => {
      if (!pair) return null
      const q = encodeURIComponent(pair)
      const [cfg, open, hist] = await Promise.all([
        api<{ timeframe: string }>(bot, "show_config"),
        api<Trade[]>(bot, "status"),
        api<{ trades: Trade[] }>(bot, "trades?limit=500"),
      ])
      const candles = await api<Candles>(bot, `pair_candles?pair=${q}&timeframe=${cfg.timeframe}&limit=500`)
      const trades = [...open, ...hist.trades.filter((t) => !t.is_open)].filter((t) => t.pair === pair)
      return { candles, trades }
    },
    30_000,
    [bot, pair]
  )

  const last = view.data?.candles.data.at(-1)
  const closeIdx = view.data?.candles.columns.indexOf("close") ?? -1

  return (
    <Card>
      <CardHeader className="max-sm:flex max-sm:flex-col">
        <CardTitle className="flex items-baseline gap-3">
          {pair ? pairLabel(pair) : "行情"}
          {last && closeIdx >= 0 && <span className="text-lg tabular-nums">{price(last[closeIdx] as number)}</span>}
        </CardTitle>
        <CardDescription>
          策略周期 {view.data?.candles.timeframe ?? "—"} · 线为策略指标，箭头为实际开仓、圆点为平仓
        </CardDescription>
        <CardAction className="flex flex-wrap items-center gap-2 max-sm:mt-2 max-sm:self-start">
          <BotFilter value={bot} onChange={(v) => setBot(v as BotId)} allowAll={false} />
          <Select value={pair ?? null} onValueChange={(v) => setPicked(v as string)}>
            <SelectTrigger size="sm" className="w-36" aria-label="交易对">
              <SelectValue placeholder="交易对" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {pairs.map((p) => (
                  <SelectItem key={p} value={p}>
                    {pairLabel(p)}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </CardAction>
      </CardHeader>
      <CardContent>
        {view.error && !view.data ? (
          <Alert variant="destructive">
            <AlertTitle>K 线加载失败</AlertTitle>
            <AlertDescription>{view.error.message}</AlertDescription>
          </Alert>
        ) : view.data ? (
          <CandleChart candles={view.data.candles} trades={view.data.trades} />
        ) : (
          <Skeleton className="h-[min(60svh,520px)] w-full" />
        )}
      </CardContent>
    </Card>
  )
}
