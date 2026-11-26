import { createContext, useContext, useEffect, useState, type ReactNode } from "react"

/** 涨跌配色：intl = 绿涨红跌（加密惯例），cn = 红涨绿跌（A 股习惯） */
export type UpDown = "intl" | "cn"
const KEY = "aten.updown"

const read = (): UpDown => {
  try {
    return localStorage.getItem(KEY) === "cn" ? "cn" : "intl"
  } catch {
    return "intl"
  }
}

const PrefsContext = createContext<{ updown: UpDown; setUpdown: (v: UpDown) => void }>({
  updown: "intl",
  setUpdown: () => {},
})

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [updown, setUpdown] = useState<UpDown>(read)
  useEffect(() => {
    document.documentElement.dataset.updown = updown
    try {
      localStorage.setItem(KEY, updown)
    } catch {
      // 不可写时只在本次会话生效
    }
  }, [updown])
  return <PrefsContext.Provider value={{ updown, setUpdown }}>{children}</PrefsContext.Provider>
}

export const usePrefs = () => useContext(PrefsContext)
