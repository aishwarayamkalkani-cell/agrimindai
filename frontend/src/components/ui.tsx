import { Loader2 } from 'lucide-react'
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'

export function Button({ variant = 'primary', loading, children, className = '', ...p }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' | 'quiet' | 'danger'; loading?: boolean }) {
  const v = {
    primary: 'bg-leaf-600 text-white hover:bg-leaf-700 disabled:bg-leaf-600/50',
    ghost: 'border line ink hover:bg-[var(--surface-2)]',
    quiet: 'ink hover:bg-[var(--surface-2)]',
    danger: 'text-red-700 dark:text-red-400 border border-red-300/60 hover:bg-red-50 dark:hover:bg-red-950/30',
  }[variant]
  return (
    <button {...p} disabled={p.disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed ${v} ${className}`}>
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}{children}
    </button>
  )
}

export function Panel({ title, action, children, className = '', tone = 'plain' }:
  { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; tone?: 'plain' | 'soft' }) {
  return (
    <section className={`${tone === 'soft' ? 'surface-2 border line' : 'surface'} rounded-xl ${className}`}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 px-5 pt-4">
          {title && <h2 className="text-[1.05rem] font-semibold">{title}</h2>}{action}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  )
}

export function PageHead({ title, intro, children }: { title: string; intro?: ReactNode; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl">
        <h1 className="text-[1.9rem] font-bold">{title}</h1>
        {intro && <p className="muted mt-1.5">{intro}</p>}
      </div>
      {children}
    </div>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium">{label}</span>
      {children}
      {hint && <span className="muted mt-1 block text-xs">{hint}</span>}
    </label>
  )
}

const inputCls = 'w-full rounded-lg border line bg-[var(--surface)] px-3 py-2 text-sm ink placeholder:text-[var(--muted)] focus:border-leaf-500 focus:outline-none'
export const Input = (p: InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={`${inputCls} ${p.className ?? ''}`} />
export const Select = ({ children, ...p }: SelectHTMLAttributes<HTMLSelectElement>) =>
  <select {...p} className={`${inputCls} ${p.className ?? ''}`}>{children}</select>

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'good' | 'warn' | 'bad' | 'info' }) {
  const c = {
    neutral: 'bg-[var(--surface-2)] muted border line',
    good: 'bg-leaf-600/12 text-leaf-700 dark:text-shoot',
    warn: 'bg-turmeric/15 text-soil-700 dark:text-turmeric',
    bad: 'bg-red-600/12 text-red-700 dark:text-red-400',
    info: 'bg-navy-700/10 text-navy-800 dark:text-sky-200',
  }[tone]
  return <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ${c}`}>{children}</span>
}

export function Notice({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'warn' | 'bad' }) {
  const c = { info: 'border-navy-700/25 bg-navy-700/5', warn: 'border-turmeric/50 bg-turmeric/10', bad: 'border-red-500/40 bg-red-500/8' }[tone]
  return <div className={`rounded-lg border px-4 py-3 text-sm ${c}`}>{children}</div>
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed line px-6 py-10 text-center">
      <p className="font-semibold">{title}</p>
      {children && <div className="muted mt-1 text-sm">{children}</div>}
    </div>
  )
}

export function Metric({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div>
      <div className="muted text-xs font-medium">{label}</div>
      <div className="font-display text-2xl font-bold tabular-nums">{value}</div>
      {sub && <div className="muted text-xs">{sub}</div>}
    </div>
  )
}

export const Spinner = ({ label }: { label?: string }) => (
  <div className="muted flex items-center gap-2 text-sm"><Loader2 className="size-4 animate-spin" aria-hidden />{label}</div>
)

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { id: T; label: string }[] }) {
  return (
    <div role="tablist" className="mb-5 flex flex-wrap gap-1 border-b line">
      {items.map(i => (
        <button key={i.id} role="tab" aria-selected={value === i.id} onClick={() => onChange(i.id)}
          className={`-mb-px border-b-2 px-3.5 py-2 text-sm font-semibold transition-colors ${value === i.id ? 'border-leaf-600 text-leaf-700 dark:text-shoot' : 'border-transparent muted hover:text-[var(--ink)]'}`}>
          {i.label}
        </button>
      ))}
    </div>
  )
}

export const chartColors = ['#2f7d4f', '#d9a21b', '#2a4268', '#7a5a3a', '#6fae7f', '#b5562f']
