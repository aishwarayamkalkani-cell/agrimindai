import { useState, type FormEvent } from 'react'
import { Logo } from '../components/Layout'
import { Button, Field, Input, Notice } from '../components/ui'
import { useApp } from '../lib/app-context'
import { LANGS, type Lang } from '../lib/i18n'

export default function Login() {
  const { login, register, t, lang, setLang } = useApp()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [f, setF] = useState({ name: '', email: '', password: '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setErr(''); setBusy(true)
    try {
      if (mode === 'login') await login(f.email, f.password)
      else await register(f.name, f.email, f.password)
    } catch (x: any) { setErr(x.message) } finally { setBusy(false) }
  }

  return (
    <div className="grid min-h-full lg:grid-cols-[1.1fr_1fr]">
      <div className="furrows relative hidden flex-col justify-between bg-navy-900 p-12 text-white lg:flex">
        <Logo light />
        <div className="max-w-md">
          <h1 className="text-[2.6rem] font-bold leading-[1.08]">Field advice grounded in documents you can check.</h1>
          <p className="mt-4 text-white/70">AgriMind answers farming questions from a curated agricultural knowledge base, diagnoses leaf
            diseases with a trained vision model, reads your soil test and plans irrigation from live weather — in English, ಕನ್ನಡ and हिन्दी.</p>
        </div>
        <svg viewBox="0 0 400 90" className="w-full max-w-md" aria-hidden>
          {Array.from({ length: 26 }).map((_, i) => {
            const h = 25 + ((i * 37) % 55)
            return <rect key={i} className="sprout" style={{ animationDelay: `${i * 35}ms` }} x={i * 15.4} y={90 - h} width="7" height={h} rx="3.5" fill={i % 5 === 0 ? '#d9a21b' : '#3b9963'} opacity={0.55 + (i % 3) * 0.15} />
          })}
        </svg>
      </div>
      <div className="flex items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-sm space-y-4">
          <div className="lg:hidden"><Logo /></div>
          <div className="flex gap-1">{LANGS.map(l => (
            <button type="button" key={l.code} onClick={() => setLang(l.code as Lang)}
              className={`rounded-md px-2.5 py-1 text-xs font-semibold ${lang === l.code ? 'bg-leaf-600 text-white' : 'muted border line'}`}>{l.label}</button>))}</div>
          <h2 className="text-2xl font-bold">{mode === 'login' ? t('login') : t('register')}</h2>
          {mode === 'register' && <Field label={t('name')}><Input required minLength={2} value={f.name} onChange={e => setF({ ...f, name: e.target.value })} autoComplete="name" /></Field>}
          <Field label={t('email')}><Input required type="email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} autoComplete="email" /></Field>
          <Field label={t('password')} hint={mode === 'register' ? 'At least 8 characters.' : undefined}>
            <Input required type="password" minLength={mode === 'register' ? 8 : 1} value={f.password} onChange={e => setF({ ...f, password: e.target.value })}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
          </Field>
          {err && <Notice tone="bad">{err}</Notice>}
          <Button className="w-full" loading={busy}>{mode === 'login' ? t('login') : t('register')}</Button>
          <p className="muted text-center text-sm">
            {mode === 'login' ? 'New to AgriMind? ' : 'Already registered? '}
            <button type="button" className="font-semibold text-leaf-600 underline-offset-2 hover:underline" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setErr('') }}>
              {mode === 'login' ? t('register') : t('login')}</button>
          </p>
          {mode === 'register' && <p className="muted text-xs">The first account created on a new installation becomes the administrator.</p>}
        </form>
      </div>
    </div>
  )
}
