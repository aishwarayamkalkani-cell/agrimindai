import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, getToken, setToken, setUnauthorizedHandler } from './api'
import { dict, type Lang } from './i18n'

export type User = { id: number; email: string; name: string; role: 'admin' | 'farmer' | 'expert'; language: Lang }

type Ctx = {
  user: User | null
  ready: boolean
  login: (email: string, password: string) => Promise<void>
  register: (name: string, email: string, password: string) => Promise<void>
  logout: () => void
  lang: Lang
  setLang: (l: Lang) => void
  t: (k: keyof typeof dict.en) => string
  dark: boolean
  toggleDark: () => void
  toast: (msg: string, kind?: 'ok' | 'error') => void
}

const AppCtx = createContext<Ctx>(null as unknown as Ctx)
export const useApp = () => useContext(AppCtx)

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)
  const [lang, setLangState] = useState<Lang>((localStorage.getItem('agrimind.lang') as Lang) || 'en')
  const [dark, setDark] = useState(() => localStorage.getItem('agrimind.theme') === 'dark' ||
    (!localStorage.getItem('agrimind.theme') && window.matchMedia('(prefers-color-scheme: dark)').matches))
  const [toasts, setToasts] = useState<{ id: number; msg: string; kind: string }[]>([])

  const logout = useCallback(() => { setToken(null); setUser(null) }, [])
  useEffect(() => { setUnauthorizedHandler(logout) }, [logout])
  useEffect(() => {
    if (!getToken()) { setReady(true); return }
    api<User>('/auth/me').then(setUser).catch(() => setToken(null)).finally(() => setReady(true))
  }, [])
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('agrimind.theme', dark ? 'dark' : 'light')
  }, [dark])
  useEffect(() => { document.documentElement.lang = lang; localStorage.setItem('agrimind.lang', lang) }, [lang])

  const setLang = (l: Lang) => {
    setLangState(l)
    if (user) api('/auth/me', { method: 'PATCH', body: { language: l } }).catch(() => {})
  }
  const login = async (email: string, password: string) => {
    const r = await api<{ token: string; user: User }>('/auth/login', { body: { email, password } })
    setToken(r.token); setUser(r.user)
  }
  const register = async (name: string, email: string, password: string) => {
    const r = await api<{ token: string; user: User }>('/auth/register', { body: { name, email, password, language: lang } })
    setToken(r.token); setUser(r.user)
  }
  const toast = useCallback((msg: string, kind: 'ok' | 'error' = 'ok') => {
    const id = Date.now() + Math.random()
    setToasts(t => [...t, { id, msg, kind }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 4500)
  }, [])
  const t = useCallback((k: keyof typeof dict.en) => dict[lang][k] ?? dict.en[k], [lang])

  const value = useMemo(() => ({ user, ready, login, register, logout, lang, setLang, t, dark, toggleDark: () => setDark(d => !d), toast }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [user, ready, lang, dark, t, toast, logout])

  return (
    <AppCtx.Provider value={value}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2" role="status" aria-live="polite">
        {toasts.map(x => (
          <div key={x.id} className={`max-w-sm rounded-lg px-4 py-3 text-sm shadow-lg ${x.kind === 'error' ? 'bg-red-700 text-white' : 'bg-navy-900 text-white'}`}>{x.msg}</div>
        ))}
      </div>
    </AppCtx.Provider>
  )
}
