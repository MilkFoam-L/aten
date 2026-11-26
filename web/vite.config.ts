import { resolve } from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// 每个机器人一个代理前缀：/ft/<bot>/api/v1/... → 对应 Freqtrade REST API，省掉 CORS 配置
const BOTS: Record<string, string> = {
  spot: "http://127.0.0.1:8080",
  futures: "http://127.0.0.1:8081",
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": resolve(import.meta.dirname, "./src"),
    },
  },
  server: {
    proxy: Object.fromEntries(
      Object.entries(BOTS).map(([id, target]) => [
        `/ft/${id}`,
        { target, changeOrigin: true, rewrite: (p: string) => p.replace(`/ft/${id}`, "") },
      ])
    ),
  },
})
