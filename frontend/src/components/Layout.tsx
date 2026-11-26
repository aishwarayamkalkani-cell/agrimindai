import { BarChart3, Bot, CloudSun, FlaskConical, Gauge, Landmark, Layers, Leaf, LogOut, Menu, Moon, Shield, Sprout, Sun, Tractor, X } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useApp } from '../lib/app-context'
import { LANGS, type Lang } from '../lib/i18n'

export function Logo({ light }: { light?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="size-8" aria-hidden>
        <rect width="32" height="32" rx="8" fill={light ? '#1d3150' : '#14233A'} />
        <path d="M16 26V13" stroke="#A9D18E" strokeWidth="2.4" strokeLinecap="round" />
        <path d="M16 17c-5 0-8-3-8-8 5 0 8 3 8 8zM16 14c0-5 3-8 8-8 0 5-3 8-8 8z" fill="#3b9963" />
      </svg>
      <span className={`font-display text-lg font-bold tracking-tight ${light ? 'text-white' : 'hidden sm:inline'}`}>AgriMind<span className="text-shoot"> AI</span></span>
    </div>
  )
}

export default function Layout() {
  const { t, user, logout, lang, setLang, dark, toggleDark } = useApp()
  const [open, setOpen] = useState(false)
  const groups = [
    { label: t('grow'), items: [
      { to: '/', icon: Gauge, label: t('dashboard'), end: true },
      { to: '/assistant', icon: Bot, label: t('assistant') },
      { to: '/disease', icon: Leaf, label: t('disease') },
      { to: '/soil', icon: Layers, label: t('soil') },
      { to: '/farming', icon: Tractor, label: t('farming') },
      { to: '/weather', icon: CloudSun, label: t('weather') },
    ] },
    { label: t('learn'), items: [
      { to: '/knowledge', icon: Sprout, label: t('knowledge') },
      { to: '/schemes', icon: Landmark, label: t('schemes') },
    ] },
    { label: t('research'), items: [
      { to: '/lab', icon: FlaskConical, label: t('lab') },
      { to: '/evaluation', icon: BarChart3, label: t('evaluation') },
      ...(user?.role === 'admin' ? [{ to: '/admin', icon: Shield, label: t('admin') }] : []),
    ] },
  ]

  const nav = (
    <nav className="flex flex-1 flex-col gap-5 overflow-y-auto px-3 py-4" aria-label="Main">
      {groups.map(g => (
        <div key={g.label}>
          <div className="px-3 pb-1.5 text-xs font-semibold text-white/45">{g.label}</div>
          {g.items.map(i => (
            <NavLink key={i.to} to={i.to} end={'end' in i} onClick={() => setOpen(false)}
              className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-[0.93rem] transition-colors ${isActive
                ? 'bg-shoot/15 font-semibold text-shoot' : 'text-white/75 hover:bg-white/5 hover:text-white'}`}>
              <i.icon className="size-[18px] shrink-0" aria-hidden />{i.label}
            </NavLink>
          ))}
        </div>
      ))}
    </nav>
  )

  return (
    <div className="flex h-full">
      <aside className={`furrows fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-navy-900 transition-transform lg:static lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex items-center justify-between px-5 py-5"><Logo light />
          <button className="text-white lg:hidden" onClick={() => setOpen(false)} aria-label="Close menu"><X /></button></div>
        {nav}
        <div className="border-t border-white/10 p-4 text-sm text-white/80">
          <div className="truncate font-semibold text-white">{user?.name}</div>
          <div className="truncate text-xs text-white/50">{user?.email} · {user?.role}</div>
          <button onClick={logout} className="mt-3 flex items-center gap-2 text-white/70 hover:text-white"><LogOut className="size-4" />{t('signOut')}</button>
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={() => setOpen(false)} />}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b line bg-[var(--surface)] px-4 py-2.5 lg:px-8">
          <button className="lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu"><Menu /></button>
          <div className="lg:hidden"><Logo /></div>
          <div className="ml-auto flex items-center gap-2">
            <div className="flex rounded-lg border line p-0.5" role="group" aria-label={t('language')}>
              {LANGS.map(l => (
                <button key={l.code} onClick={() => setLang(l.code as Lang)} aria-pressed={lang === l.code}
                  className={`rounded-md px-2.5 py-1 text-xs font-semibold ${lang === l.code ? 'bg-leaf-600 text-white' : 'muted hover:text-[var(--ink)]'}`}>{l.label}</button>
              ))}
            </div>
            <button onClick={toggleDark} className="rounded-lg border line p-2" aria-label={t('theme')} title={t('theme')}>
              {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </button>
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto px-4 py-6 lg:px-8 lg:py-8"><Outlet /></main>
      </div>
    </div>
  )
}
