import { useState } from "react"
import { toast } from "sonner"
import { PauseIcon, PlayIcon, RotateCwIcon, SquareIcon } from "lucide-react"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { usePoll } from "@/hooks/use-poll"
import { allBots, api, botLabel, BOTS, post, type BotConfig, type BotId } from "@/lib/api"
import { pct } from "@/lib/format"

type Action = { bot: BotId; path: "start" | "stop" | "stopentry" | "reload_config"; label: string; danger?: string }

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1.5 text-sm">
      <dt className="text-muted-foreground">{k}</dt>
      <dd className="text-right tabular-nums">{v}</dd>
    </div>
  )
}

function BotPanel({ bot, c, onAction }: { bot: BotId; c: BotConfig; onAction: (a: Action) => void }) {
  const roi = Object.entries(c.minimal_roi)
    .map(([m, r]) => `${m}分→${pct(r, 0).replace("+", "")}`)
    .join("，")
  return (
    <Card>
      <CardHeader>
        <CardTitle>{botLabel(bot)}</CardTitle>
        <CardDescription>
          Freqtrade {c.version} · {c.bot_name}
        </CardDescription>
        <CardAction>
          {c.dry_run ? <Badge variant="secondary">模拟盘</Badge> : <Badge variant="destructive">● 实盘</Badge>}
        </CardAction>
      </CardHeader>
      <CardContent>
        <dl className="divide-y">
          <Row k="状态" v={{ running: "运行中", stopped: "已停止", paused: "暂停开仓" }[c.state] ?? c.state} />
          <Row k="交易所" v={c.exchange} />
          <Row k="市场" v={c.trading_mode === "futures" ? `永续合约（${c.margin_mode === "isolated" ? "逐仓" : "全仓"}）` : "现货"} />
          <Row k="策略" v={`${c.strategy} · ${c.timeframe}`} />
          <Row k="最大持仓数" v={c.max_open_trades} />
          <Row k="每笔仓位" v={c.stake_amount === "unlimited" ? "可用资金均分" : `${c.stake_amount} ${c.stake_currency}`} />
          <Row k="止损" v={pct(c.stoploss)} />
          <Row k="止盈 ROI" v={<span className="text-xs">{roi}</span>} />
          <Row k="移动止损" v={c.trailing_stop ? "开启" : "关闭"} />
        </dl>
      </CardContent>
      <CardFooter className="flex flex-wrap gap-2">
        {c.state === "running" ? (
          <>
            <Button variant="outline" size="sm" onClick={() => onAction({ bot, path: "stopentry", label: "暂停开仓", danger: "不再开新仓，已有持仓照常按策略止盈止损。" })}>
              <PauseIcon data-icon="inline-start" />
              暂停开仓
            </Button>
            <Button variant="outline" size="sm" onClick={() => onAction({ bot, path: "stop", label: "停止机器人", danger: "停止后不会再处理任何持仓（包括止损），已有持仓需要你自己盯。" })}>
              <SquareIcon data-icon="inline-start" />
              停止
            </Button>
          </>
        ) : (
          <Button size="sm" onClick={() => onAction({ bot, path: "start", label: "启动机器人" })}>
            <PlayIcon data-icon="inline-start" />
            启动
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={() => onAction({ bot, path: "reload_config", label: "重载配置", danger: "重新读取配置和策略文件，机器人会短暂中断。" })}>
          <RotateCwIcon data-icon="inline-start" />
          重载配置
        </Button>
      </CardFooter>
    </Card>
  )
}

export function BotsPage() {
  const cfgs = usePoll(() => allBots((b) => api<BotConfig>(b, "show_config")), 15_000)
  const [pending, setPending] = useState<Action | null>(null)
  const [busy, setBusy] = useState(false)

  async function run(a: Action) {
    setBusy(true)
    try {
      await post(a.bot, a.path)
      toast.success(`${botLabel(a.bot)}：${a.label}成功`)
      cfgs.refresh()
    } catch (e) {
      toast.error(`${a.label}失败：${(e as Error).message}`)
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  return (
    <>
      <div className="grid gap-4 lg:grid-cols-2">
        {cfgs.loading && !cfgs.data
          ? BOTS.map((b) => <Skeleton key={b.id} className="h-96" />)
          : (cfgs.data ?? []).map((r) =>
              r.data ? (
                <BotPanel key={r.bot} bot={r.bot} c={r.data} onAction={(a) => (a.danger ? setPending(a) : run(a))} />
              ) : (
                <Card key={r.bot}>
                  <CardHeader>
                    <CardTitle>{botLabel(r.bot)}</CardTitle>
                    <CardDescription className="text-destructive">离线：{r.error?.message}</CardDescription>
                  </CardHeader>
                </Card>
              )
            )}
      </div>
      <AlertDialog open={!!pending} onOpenChange={(o) => !o && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pending && botLabel(pending.bot)}：{pending?.label}？
            </AlertDialogTitle>
            <AlertDialogDescription>{pending?.danger}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>取消</AlertDialogCancel>
            <AlertDialogAction disabled={busy} onClick={() => pending && run(pending)}>
              确认
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
