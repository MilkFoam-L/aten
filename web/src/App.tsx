import { lazy, Suspense, useEffect, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AppSidebar, NAV, type Route } from "@/components/app-sidebar"
import { usePoll } from "@/hooks/use-poll"
import { allBots, api, isLoggedIn, LOGOUT_EVENT, type BotConfig } from "@/lib/api"
import { PrefsProvider } from "@/lib/prefs"
import { Skeleton } from "@/components/ui/skeleton"
import { LoginPage } from "@/pages/login"

// 页面按需加载：recharts / lightweight-charts 体积大，不压首屏
const PAGES: Record<Route, React.ComponentType> = {
  overview: lazy(() => import("@/pages/overview").then((m) => ({ default: m.OverviewPage }))),
  trades: lazy(() => import("@/pages/trades").then((m) => ({ default: m.TradesPage }))),
  chart: lazy(() => import("@/pages/chart").then((m) => ({ default: m.ChartPage }))),
  bots: lazy(() => import("@/pages/bots").then((m) => ({ default: m.BotsPage }))),
}

const readRoute = (): Route => {
  const r = location.hash.replace(/^#\//, "")
  return r in PAGES ? (r as Route) : "overview"
}

function useRoute() {
  const [route, setRoute] = useState(readRoute)
  useEffect(() => {
    const on = () => setRoute(readRoute())
    window.addEventListener("hashchange", on)
    return () => window.removeEventListener("hashchange", on)
  }, [])
  return route
}

/** 任一机器人是实盘就醒目标红，避免把真钱当模拟 */
function ModeBadge() {
  const cfgs = usePoll(() => allBots((b) => api<BotConfig>(b, "show_config")), 30_000)
  const live = (cfgs.data ?? []).some((r) => r.data && !r.data.dry_run)
  return live ? (
    <Badge variant="destructive" title="实盘 — 真实资金，下单会真实成交">● 实盘</Badge>
  ) : (
    <Badge variant="secondary" title="模拟盘 — 虚拟资金，不涉及真钱">模拟盘</Badge>
  )
}

function Shell() {
  const route = useRoute()
  const Page = PAGES[route]
  const label = NAV.find((n) => n.route === route)!.label
  return (
    <SidebarProvider>
      <AppSidebar route={route} />
      <SidebarInset className="min-w-0">
        <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b bg-background/85 px-3 backdrop-blur-md sm:px-4">
          <SidebarTrigger className="-ml-0.5" aria-label="展开或收起导航" />
          <Separator orientation="vertical" className="mr-1 h-5!" />
          <span className="truncate text-sm font-medium">{label}</span>
          <div className="ml-auto">
            <ModeBadge />
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl p-4 sm:p-6">
          <Suspense fallback={<Skeleton className="h-96 w-full" />}>
            <Page />
          </Suspense>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

export function App() {
  const [authed, setAuthed] = useState(isLoggedIn)
  useEffect(() => {
    const on = () => setAuthed(false)
    window.addEventListener(LOGOUT_EVENT, on)
    return () => window.removeEventListener(LOGOUT_EVENT, on)
  }, [])

  return (
    <PrefsProvider>
      <TooltipProvider>
        {authed ? <Shell /> : <LoginPage onDone={() => setAuthed(true)} />}
        <Toaster position="top-center" />
      </TooltipProvider>
    </PrefsProvider>
  )
}

export default App
