import { useState } from "react"

import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { BotFilter, type BotFilterValue } from "@/components/bot-filter"
import { TradeTable, type BotTrade } from "@/components/trade-table"
import { usePoll } from "@/hooks/use-poll"
import { allBots, api, type Trade } from "@/lib/api"

type History = { trades: Trade[] }

export function TradesPage() {
  const [bot, setBot] = useState<BotFilterValue>("all")
  const data = usePoll(
    () =>
      allBots(async (b) => {
        const [open, hist] = await Promise.all([api<Trade[]>(b, "status"), api<History>(b, "trades?limit=200")])
        return { open, closed: hist.trades.filter((t) => !t.is_open) }
      }),
    10_000
  )
  const rows = (data.data ?? []).filter((r) => r.data && (bot === "all" || r.bot === bot))
  const open: BotTrade[] = rows.flatMap((r) => r.data!.open.map((t) => ({ ...t, bot: r.bot })))
  const closed: BotTrade[] = rows
    .flatMap((r) => r.data!.closed.map((t) => ({ ...t, bot: r.bot })))
    .sort((a, b) => (b.close_timestamp ?? 0) - (a.close_timestamp ?? 0))

  return (
    <Card>
      <Tabs defaultValue="open">
        <CardHeader className="max-sm:flex max-sm:flex-col">
          <CardTitle className="sr-only">持仓与交易</CardTitle>
          <TabsList>
            <TabsTrigger value="open">持仓 {open.length > 0 && `(${open.length})`}</TabsTrigger>
            <TabsTrigger value="closed">历史 {closed.length > 0 && `(${closed.length})`}</TabsTrigger>
          </TabsList>
          <CardAction className="max-sm:mt-2 max-sm:self-start">
            <BotFilter value={bot} onChange={setBot} />
          </CardAction>
        </CardHeader>
        <CardContent>
          {data.loading && !data.data ? (
            <Skeleton className="h-48 w-full" />
          ) : (
            <>
              <TabsContent value="open">
                <TradeTable trades={open} mode="open" onChanged={data.refresh} />
              </TabsContent>
              <TabsContent value="closed">
                <TradeTable trades={closed} mode="closed" />
              </TabsContent>
            </>
          )}
        </CardContent>
      </Tabs>
    </Card>
  )
}
