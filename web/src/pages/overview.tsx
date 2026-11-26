import { Bar, BarChart, CartesianGrid, ReferenceLine, XAxis, YAxis } from "recharts"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Skeleton } from "@/components/ui/skeleton"
import { Pnl } from "@/components/pnl"
import { SignalBoard } from "@/components/signal-board"
import { TradeTable, type BotTrade } from "@/components/trade-table"
import { usePoll } from "@/hooks/use-poll"
import { allBots, api, botLabel, BOTS, snapshot, type Daily, type Snapshot } from "@/lib/api"
import { money, pct } from "@/lib/format"

const STATE: Record<string, { text: string; className: string }> = {
  running: { text: "运行中", className: "bg-up-soft text-up" },
  paused: { text: "暂停开仓", className: "bg-warn-soft text-warn" },
  stopped: { text: "已停止", className: "bg-muted text-muted-foreground" },
}

function Metric({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm font-medium tabular-nums">{children}</span>
    </div>
  )
}

function BotCard({ s }: { s: Snapshot }) {
  const st = STATE[s.config.state] ?? STATE.stopped
  const { profit } = s
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {botLabel(s.bot)}
          <Badge className={st.className}>{st.text}</Badge>
        </CardTitle>
        <CardDescription>
          {s.config.exchange} · {s.config.strategy} · {s.config.timeframe}
        </CardDescription>
        <CardAction>
          {s.config.dry_run ? <Badge variant="secondary">模拟盘</Badge> : <Badge variant="destructive">● 实盘</Badge>}
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div>
          <div className="text-xs text-muted-foreground">账户权益 ({s.balance.stake})</div>
          <div className="text-2xl font-semibold tracking-tight tabular-nums">{money(s.balance.total)}</div>
          <Pnl className="text-sm" value={profit.profit_all_coin} ratio={profit.profit_all_ratio} />
        </div>
        <div className="grid grid-cols-3 gap-3 border-t pt-3">
          <Metric label="持仓">
            {s.open.length} / {s.config.max_open_trades}
          </Metric>
          <Metric label="已平仓">{profit.closed_trade_count}</Metric>
          <Metric label="胜率">{profit.closed_trade_count ? pct(profit.winrate, 1).replace("+", "") : "—"}</Metric>
          <Metric label="最大回撤">{profit.closed_trade_count ? pct(-profit.max_drawdown) : "—"}</Metric>
          <Metric label="盈亏比">{profit.profit_factor?.toFixed(2) ?? "—"}</Metric>
          <Metric label="已实现">
            <Pnl value={profit.profit_closed_coin} />
          </Metric>
        </div>
      </CardContent>
    </Card>
  )
}

const chartConfig = {
  spot: { label: "现货", color: "var(--chart-1)" },
  futures: { label: "永续合约", color: "var(--chart-2)" },
} satisfies ChartConfig

function DailyChart() {
  const daily = usePoll(() => allBots((b) => api<Daily>(b, "daily?timescale=30")), 60_000)
  const rows = new Map<string, Record<string, number | string>>()
  for (const r of daily.data ?? []) {
    for (const d of r.data?.data ?? []) {
      const row = rows.get(d.date) ?? { date: d.date.slice(5) }
      row[r.bot] = d.abs_profit
      rows.set(d.date, row)
    }
  }
  const data = [...rows.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, v]) => v)

  return (
    <Card>
      <CardHeader>
        <CardTitle>近 30 天每日已实现盈亏</CardTitle>
        <CardDescription>按平仓日汇总，单位 USDT</CardDescription>
      </CardHeader>
      <CardContent>
        {daily.loading && !daily.data ? (
          <Skeleton className="h-56 w-full" />
        ) : (
          <ChartContainer config={chartConfig} className="aspect-auto h-56 w-full">
            <BarChart data={data} margin={{ left: 4, right: 4 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="date" tickLine={false} axisLine={false} minTickGap={24} />
              <YAxis tickLine={false} axisLine={false} width={48} />
              <ReferenceLine y={0} stroke="var(--border)" />
              <ChartTooltip content={<ChartTooltipContent />} />
              <ChartLegend content={<ChartLegendContent />} />
              {BOTS.map((b) => (
                <Bar key={b.id} dataKey={b.id} stackId="p" fill={`var(--color-${b.id})`} radius={2} />
              ))}
            </BarChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}

export function OverviewPage() {
  const snaps = usePoll(() => allBots(snapshot), 10_000)
  const ok = (snaps.data ?? []).flatMap((r) => (r.data ? [r.data] : []))
  const offline = (snaps.data ?? []).filter((r) => r.error)
  const equity = ok.reduce((a, s) => a + s.balance.total, 0)
  const pnl = ok.reduce((a, s) => a + s.profit.profit_all_coin, 0)
  const open: BotTrade[] = ok.flatMap((s) => s.open.map((t) => ({ ...t, bot: s.bot })))
  const unrealized = open.reduce((a, t) => a + (t.profit_abs ?? 0), 0)

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="ov-heading" className="flex flex-wrap items-end justify-between gap-x-10 gap-y-3">
        <div>
          <h1 id="ov-heading" className="text-sm text-muted-foreground">总权益 · USDT</h1>
          {snaps.loading && !snaps.data ? (
            <Skeleton className="mt-1 h-10 w-56" />
          ) : (
            <div className="text-4xl font-semibold tracking-tight tabular-nums">{money(equity)}</div>
          )}
        </div>
        <dl className="flex gap-8 text-sm">
          <div>
            <dt className="text-muted-foreground">累计盈亏</dt>
            <dd className="text-lg font-medium"><Pnl value={pnl} /></dd>
          </div>
          <div>
            <dt className="text-muted-foreground">浮动盈亏</dt>
            <dd className="text-lg font-medium"><Pnl value={unrealized} /></dd>
          </div>
          <div>
            <dt className="text-muted-foreground">持仓数</dt>
            <dd className="text-lg font-medium tabular-nums">{open.length}</dd>
          </div>
        </dl>
      </section>

      {offline.length > 0 && (
        <Alert variant="destructive">
          <AlertTitle>{offline.map((o) => botLabel(o.bot)).join("、")} 连接失败</AlertTitle>
          <AlertDescription>{offline[0].error?.message}。请检查 docker compose ps 和机器人日志。</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {snaps.loading && !snaps.data
          ? BOTS.map((b) => <Skeleton key={b.id} className="h-64" />)
          : ok.map((s) => <BotCard key={s.bot} s={s} />)}
      </div>

      <SignalBoard />

      <DailyChart />

      <Card>
        <CardHeader>
          <CardTitle>当前持仓</CardTitle>
          <CardDescription>每 10 秒刷新</CardDescription>
        </CardHeader>
        <CardContent>
          <TradeTable trades={open} mode="open" onChanged={snaps.refresh} />
        </CardContent>
      </Card>
    </div>
  )
}
