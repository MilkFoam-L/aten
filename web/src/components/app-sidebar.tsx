import { CandlestickChartIcon, LayoutDashboardIcon, ListOrderedIcon, LogOutIcon, MoonIcon, BotIcon, SunIcon, ArrowUpDownIcon } from "lucide-react"

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { useTheme } from "@/components/theme-provider"
import { logout } from "@/lib/api"
import { usePrefs } from "@/lib/prefs"

export const NAV = [
  { route: "overview", label: "总览", icon: LayoutDashboardIcon },
  { route: "trades", label: "持仓与交易", icon: ListOrderedIcon },
  { route: "chart", label: "行情", icon: CandlestickChartIcon },
  { route: "bots", label: "机器人", icon: BotIcon },
] as const
export type Route = (typeof NAV)[number]["route"]

export function AppSidebar({ route }: { route: Route }) {
  const { theme, setTheme } = useTheme()
  const { updown, setUpdown } = usePrefs()
  const dark = theme === "dark" || (theme === "system" && document.documentElement.classList.contains("dark"))

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" render={<a href="#/overview" />}>
              <div className="flex aspect-square size-8 items-center justify-center rounded-md bg-sidebar-primary font-semibold text-sidebar-primary-foreground">
                A
              </div>
              <div className="grid flex-1 text-left leading-tight">
                <span className="font-semibold tracking-tight">Aten</span>
                <span className="text-xs text-muted-foreground">加密量化 · Freqtrade</span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV.map((n) => (
                <SidebarMenuItem key={n.route}>
                  <SidebarMenuButton isActive={route === n.route} tooltip={n.label} render={<a href={`#/${n.route}`} />}>
                    <n.icon />
                    <span>{n.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton tooltip="切换深浅色" onClick={() => setTheme(dark ? "light" : "dark")}>
              {dark ? <SunIcon /> : <MoonIcon />}
              <span>{dark ? "浅色" : "深色"}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton tooltip="涨跌配色" onClick={() => setUpdown(updown === "cn" ? "intl" : "cn")}>
              <ArrowUpDownIcon />
              <span>
                {updown === "cn" ? (
                  <><span className="text-up">红涨</span><span className="text-down">绿跌</span></>
                ) : (
                  <><span className="text-up">绿涨</span><span className="text-down">红跌</span></>
                )}
              </span>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton tooltip="退出登录" onClick={logout}>
              <LogOutIcon />
              <span>退出登录</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
