import { useState } from "react"
import { toast } from "sonner"
import { LogOutIcon } from "lucide-react"

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
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Pnl } from "@/components/pnl"
import { botLabel, post, type BotId, type Trade } from "@/lib/api"
import { dateTime, pairLabel, price, since } from "@/lib/format"

export type BotTrade = Trade & { bot: BotId }

function Side({ t }: { t: BotTrade }) {
  return (
    <div className="flex items-center gap-1.5">
      <Badge variant="outline" className={t.is_short ? "border-down/40 text-down" : "border-up/40 text-up"}>
        {t.is_short ? "空" : "多"}
      </Badge>
      {t.leverage > 1 && <span className="text-xs text-muted-foreground">{t.leverage}x</span>}
    </div>
  )
}

export function TradeTable({
  trades,
  mode,
  onChanged,
}: {
  trades: BotTrade[]
  mode: "open" | "closed"
  onChanged?: () => void
}) {
  const [exiting, setExiting] = useState<BotTrade | null>(null)
  const [busy, setBusy] = useState(false)

  if (trades.length === 0) {
    return (
      <Empty className="border border-dashed py-10">
        <EmptyHeader>
          <EmptyTitle>{mode === "open" ? "当前没有持仓" : "还没有已平仓交易"}</EmptyTitle>
          <EmptyDescription>
            {mode === "open" ? "策略出现入场信号后，持仓会显示在这里。" : "平仓后的交易会按时间倒序列在这里。"}
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  async function confirmExit() {
    if (!exiting) return
    setBusy(true)
    try {
      await post(exiting.bot, "forceexit", { tradeid: String(exiting.trade_id), ordertype: "market" })
      toast.success(`已提交平仓：${pairLabel(exiting.pair)}`)
      onChanged?.()
    } catch (e) {
      toast.error(`平仓失败：${(e as Error).message}`)
    } finally {
      setBusy(false)
      setExiting(null)
    }
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>交易对</TableHead>
            <TableHead>方向</TableHead>
            <TableHead className="text-right">开仓价</TableHead>
            <TableHead className="text-right">{mode === "open" ? "现价" : "平仓价"}</TableHead>
            <TableHead className="text-right">保证金</TableHead>
            <TableHead className="text-right">盈亏</TableHead>
            <TableHead className="hidden md:table-cell">{mode === "open" ? "止损 / 强平" : "平仓原因"}</TableHead>
            <TableHead className="hidden lg:table-cell">{mode === "open" ? "持有" : "平仓时间"}</TableHead>
            {mode === "open" && <TableHead className="w-0" />}
          </TableRow>
        </TableHeader>
        <TableBody>
          {trades.map((t) => (
            <TableRow key={`${t.bot}-${t.trade_id}`}>
              <TableCell>
                <div className="font-medium">{pairLabel(t.pair)}</div>
                <div className="text-xs text-muted-foreground">
                  {botLabel(t.bot)} · #{t.trade_id}
                </div>
              </TableCell>
              <TableCell>
                <Side t={t} />
              </TableCell>
              <TableCell className="text-right tabular-nums">{price(t.open_rate)}</TableCell>
              <TableCell className="text-right tabular-nums">
                {price(mode === "open" ? t.current_rate : t.close_rate)}
              </TableCell>
              <TableCell className="text-right tabular-nums">{t.stake_amount.toFixed(2)}</TableCell>
              <TableCell className="text-right">
                <Pnl value={t.profit_abs} ratio={t.profit_ratio} />
              </TableCell>
              <TableCell className="hidden text-xs text-muted-foreground md:table-cell">
                {mode === "open" ? (
                  <>
                    {price(t.stop_loss_abs)}
                    {t.liquidation_price != null && <span className="text-down"> / {price(t.liquidation_price)}</span>}
                  </>
                ) : (
                  t.exit_reason ?? "—"
                )}
              </TableCell>
              <TableCell className="hidden text-xs text-muted-foreground lg:table-cell">
                {mode === "open" ? since(t.open_timestamp) : dateTime(t.close_timestamp)}
              </TableCell>
              {mode === "open" && (
                <TableCell>
                  <Button variant="ghost" size="sm" onClick={() => setExiting(t)} aria-label={`平仓 ${pairLabel(t.pair)}`}>
                    <LogOutIcon data-icon="inline-start" />
                    平仓
                  </Button>
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <AlertDialog open={!!exiting} onOpenChange={(o) => !o && setExiting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>市价平仓 {exiting && pairLabel(exiting.pair)}？</AlertDialogTitle>
            <AlertDialogDescription>
              将以市价立即平掉这笔{exiting?.is_short ? "空单" : "多单"}（{exiting && botLabel(exiting.bot)} #{exiting?.trade_id}），
              无法撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>取消</AlertDialogCancel>
            <AlertDialogAction variant="destructive" disabled={busy} onClick={confirmExit}>
              确认平仓
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
