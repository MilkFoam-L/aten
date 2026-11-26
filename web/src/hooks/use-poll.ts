import { useCallback, useEffect, useRef, useState } from "react"

type PollState<T> = { data?: T; error?: Error; loading: boolean }

/** 立即执行一次 fn，之后每 ms 毫秒轮询；deps 变化时重置。页面隐藏时暂停。 */
export function usePoll<T>(fn: () => Promise<T>, ms: number, deps: unknown[] = []) {
  const [state, setState] = useState<PollState<T>>({ loading: true })
  const [nonce, setNonce] = useState(0)
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    let alive = true
    let timer: number | undefined
    setState({ loading: true })
    const run = async () => {
      if (document.hidden) {
        timer = window.setTimeout(run, ms)
        return
      }
      try {
        const data = await fnRef.current()
        if (alive) setState({ data, loading: false })
      } catch (e) {
        if (alive) setState((s) => ({ data: s.data, error: e as Error, loading: false }))
      }
      if (alive) timer = window.setTimeout(run, ms)
    }
    void run()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, nonce, ...deps])

  const refresh = useCallback(() => setNonce((n) => n + 1), [])
  return { ...state, refresh }
}
