import { cn } from "cn"

import { pct, signedMoney } from "@/lib/format"

/** 盈亏数字：正数用涨色、负数用跌色、0 用中性色 */
export function Pnl({
  value,
  ratio,
  className,
}: {
  value?: number | null
  ratio?: number | null
  className?: string
}) {
  const sign = Math.sign((value ?? ratio ?? 0) as number)
  return (
    <span
      className={cn(
        "tabular-nums",
        sign > 0 && "text-up",
        sign < 0 && "text-down",
        sign === 0 && "text-muted-foreground",
        className
      )}
    >
      {value != null && signedMoney(value)}
      {value != null && ratio != null && " "}
      {ratio != null && (value != null ? <span className="text-xs opacity-80">{pct(ratio)}</span> : pct(ratio))}
    </span>
  )
}
