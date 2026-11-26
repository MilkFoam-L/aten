import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { BOTS, type BotId } from "@/lib/api"

export type BotFilterValue = BotId | "all"

export function BotFilter({
  value,
  onChange,
  allowAll = true,
}: {
  value: BotFilterValue
  onChange: (v: BotFilterValue) => void
  allowAll?: boolean
}) {
  return (
    <ToggleGroup
      variant="outline"
      size="sm"
      spacing={0}
      value={[value]}
      onValueChange={(v) => v[0] && onChange(v[0] as BotFilterValue)}
      aria-label="选择机器人"
    >
      {allowAll && <ToggleGroupItem value="all">全部</ToggleGroupItem>}
      {BOTS.map((b) => (
        <ToggleGroupItem key={b.id} value={b.id}>
          {b.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )
}
