import { useEffect, useRef } from "react"
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  LineSeries,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts"

import { useTheme } from "@/components/theme-provider"
import type { Candles, Trade } from "@/lib/api"
import { usePrefs } from "@/lib/prefs"

/** lightweight-charts 不认 oklch：借 1×1 canvas 把 CSS 变量解析成 rgba */
function cssColor(name: string, alpha = 1) {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  const ctx = document.createElement("canvas").getContext("2d")!
  ctx.fillStyle = raw
  ctx.fillRect(0, 0, 1, 1)
  const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data
  return `rgba(${r},${g},${b},${((a / 255) * alpha).toFixed(3)})`
}

const LINES = [
  { col: "ema_fast", color: "--chart-2", title: "EMA21" },
  { col: "ema_slow", color: "--chart-3", title: "EMA55" },
  { col: "ema_trend", color: "--chart-4", title: "EMA200" },
  { col: "ema50", color: "--chart-3", title: "EMA50" },
]

const toTime = (v: string | number) => Math.floor(new Date(v).getTime() / 1000) as UTCTimestamp

export function CandleChart({ candles, trades }: { candles: Candles; trades: Trade[] }) {
  const ref = useRef<HTMLDivElement>(null)
  const { theme } = useTheme()
  const { updown } = usePrefs()

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const idx = Object.fromEntries(candles.columns.map((c, i) => [c, i]))
    const up = cssColor("--up")
    const down = cssColor("--down")
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: cssColor("--muted-foreground"),
        fontFamily: getComputedStyle(document.body).fontFamily,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: cssColor("--border", 0.6) },
        horzLines: { color: cssColor("--border", 0.6) },
      },
      rightPriceScale: { borderColor: cssColor("--border") },
      timeScale: { borderColor: cssColor("--border"), timeVisible: true },
      localization: { locale: "zh-CN" },
    })

    const candle = chart.addSeries(CandlestickSeries, {
      upColor: up,
      downColor: down,
      borderVisible: false,
      wickUpColor: up,
      wickDownColor: down,
    })
    candle.setData(
      candles.data.map((r) => ({
        time: toTime(r[idx.date] as string),
        open: r[idx.open] as number,
        high: r[idx.high] as number,
        low: r[idx.low] as number,
        close: r[idx.close] as number,
      }))
    )

    for (const l of LINES) {
      if (idx[l.col] == null) continue
      chart
        .addSeries(LineSeries, {
          color: cssColor(l.color),
          lineWidth: 1,
          title: l.title,
          priceLineVisible: false,
          lastValueVisible: false,
        })
        .setData(
          candles.data
            .filter((r) => r[idx[l.col]] != null)
            .map((r) => ({ time: toTime(r[idx.date] as string), value: r[idx[l.col]] as number }))
        )
    }

    // 实际成交标记：开仓箭头 + 平仓圆点。标记时间对齐到 K 线起点，否则落在两根之间不显示。
    const tfSec = candles.data.length > 1 ? toTime(candles.data[1][idx.date] as string) - toTime(candles.data[0][idx.date] as string) : 3600
    const first = candles.data.length ? toTime(candles.data[0][idx.date] as string) : 0
    const snap = (ms: number) => (Math.floor(ms / 1000 / tfSec) * tfSec) as UTCTimestamp
    const markers: SeriesMarker<Time>[] = []
    for (const t of trades) {
      const color = t.is_short ? down : up
      const open = snap(t.open_timestamp)
      if (open >= first)
        markers.push({
          time: open,
          position: t.is_short ? "aboveBar" : "belowBar",
          shape: t.is_short ? "arrowDown" : "arrowUp",
          color,
          text: t.is_short ? "开空" : "开多",
        })
      if (t.close_timestamp && snap(t.close_timestamp) >= first)
        markers.push({ time: snap(t.close_timestamp), position: "inBar", shape: "circle", color: cssColor("--foreground"), text: "平" })
    }
    createSeriesMarkers(candle, markers.sort((a, b) => (a.time as number) - (b.time as number)))
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [candles, trades, theme, updown])

  return <div ref={ref} className="h-[min(60svh,520px)] w-full" role="img" aria-label="K 线图" />
}
