// Light / dark mode. "auto" follows the device setting; the choice is saved in this browser only.
import { useEffect, useState } from 'react'

export type Theme = 'auto' | 'light' | 'dark'
const KEY = 'tabiffy.theme'
const darkQuery = () => window.matchMedia?.('(prefers-color-scheme: dark)')

/** The saved choice ("auto" if none, or if browser storage is unavailable, e.g. private mode). */
export function readTheme(): Theme {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'auto'
  } catch {
    return 'auto'
  }
}

/** Apply a theme to the page (the CSS colors key off `data-theme`) and remember it. */
export function applyTheme(theme: Theme) {
  if (theme === 'auto') delete document.documentElement.dataset.theme
  else document.documentElement.dataset.theme = theme
  try {
    if (theme === 'auto') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, theme)
  } catch {
    // Storage blocked: the theme still applies for this visit.
  }
}

/** True when the page is currently dark, whether chosen directly or via "auto" and the device setting. */
export function useIsDark(theme: Theme): boolean {
  const [deviceDark, setDeviceDark] = useState(() => !!darkQuery()?.matches)
  useEffect(() => {
    const q = darkQuery()
    if (!q) return
    const onChange = () => setDeviceDark(q.matches)
    q.addEventListener('change', onChange)
    return () => q.removeEventListener('change', onChange)
  }, [])
  return theme === 'dark' || (theme === 'auto' && deviceDark)
}
