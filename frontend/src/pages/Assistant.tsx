import { BookOpen, Plus, SendHorizontal, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { Badge } from '../components/ui'
import { api, fmtDate, pct } from '../lib/api'
import { useApp } from '../lib/app-context'

type Cit = { n: number; title: string; filename: string; page?: number; score: number; snippet: string }
type Msg = { id?: number; role: 'user' | 'assistant'; content: string; citations?: Cit[]; meta?: any }

export function Citations({ items }: { items: Cit[] }) {
  const { t } = useApp()
  const [open, setOpen] = useState<number | null>(null)
  if (!items?.length) return null
  return (
    <div className="mt-3 border-t line pt-2">
      <div className="muted mb-1.5 flex items-center gap-1.5 text-xs font-semibold"><BookOpen className="size-3.5" />{t('sources')}</div>
      <div className="flex flex-wrap gap-1.5">
        {items.map(c => (
          <button key={c.n} onClick={() => setOpen(open === c.n ? null : c.n)} aria-expanded={open === c.n}
            className={`rounded-md border px-2 py-0.5 text-xs ${open === c.n ? 'border-leaf-500 bg-leaf-600/10' : 'line hover:border-leaf-500'}`}>
            [{c.n}] {c.title}{c.page ? `, p.${c.page}` : ''}
          </button>
        ))}
      </div>
      {open != null && (() => { const c = items.find(x => x.n === open)!; return (
        <blockquote className="surface-2 mt-2 rounded-lg border line p-3 text-xs leading-relaxed">
          <div className="muted mb-1">{c.filename} · similarity {c.score.toFixed(3)}</div>{c.snippet}…
        </blockquote>) })()}
    </div>
  )
}

export default function Assistant() {
  const { t, lang, toast } = useApp()
  const { id } = useParams()
  const nav = useNavigate()
  const loc = useLocation() as { state?: { ask?: string } }
  const [convs, setConvs] = useState<any[]>([])
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [useKb, setUseKb] = useState(true)
  const end = useRef<HTMLDivElement>(null)
  const asked = useRef(false)
  const cid = id ? Number(id) : null

  const loadConvs = useCallback(() => api('/conversations').then(setConvs).catch(() => {}), [])
  useEffect(() => { loadConvs() }, [loadConvs])
  useEffect(() => {
    if (!cid) { setMsgs([]); return }
    api(`/conversations/${cid}`).then(c => setMsgs(c.messages)).catch(e => { toast(e.message, 'error'); nav('/assistant') })
  }, [cid, nav, toast])
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, busy])

  const send = useCallback(async (text: string) => {
    if (!text.trim() || busy) return
    setMsgs(m => [...m, { role: 'user', content: text }]); setInput(''); setBusy(true)
    try {
      const r = await api('/chat', { body: { message: text, conversation_id: cid, language: lang, use_rag: useKb } })
      setMsgs(m => [...m, r.message])
      if (!cid) nav(`/assistant/${r.conversation_id}`, { replace: true })
      loadConvs()
    } catch (e: any) {
      setMsgs(m => [...m, { role: 'assistant', content: `**Could not answer.** ${e.message}` }])
    } finally { setBusy(false) }
  }, [busy, cid, lang, useKb, nav, loadConvs])

  useEffect(() => {
    if (loc.state?.ask && !asked.current) { asked.current = true; send(loc.state.ask); window.history.replaceState({}, '') }
  }, [loc.state, send])

  const submit = (e: FormEvent) => { e.preventDefault(); send(input) }
  const remove = async (x: number) => {
    await api(`/conversations/${x}`, { method: 'DELETE' }); loadConvs(); if (x === cid) nav('/assistant')
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-8.5rem)] max-w-6xl gap-5">
      <aside className="surface hidden w-64 shrink-0 flex-col rounded-xl md:flex">
        <button onClick={() => nav('/assistant')} className="m-3 flex items-center justify-center gap-2 rounded-lg bg-leaf-600 px-3 py-2 text-sm font-semibold text-white hover:bg-leaf-700"><Plus className="size-4" />{t('newChat')}</button>
        <ul className="flex-1 overflow-y-auto px-2 pb-2 text-sm">
          {convs.length === 0 && <li className="muted px-2 py-3">{t('noChats')}</li>}
          {convs.map(c => (
            <li key={c.id} className={`group flex items-center rounded-lg ${c.id === cid ? 'bg-leaf-600/10' : 'hover:bg-[var(--surface-2)]'}`}>
              <button onClick={() => nav(`/assistant/${c.id}`)} className="min-w-0 flex-1 px-2.5 py-2 text-left">
                <span className="block truncate font-medium">{c.title}</span><span className="muted text-xs">{fmtDate(c.updated_at)}</span>
              </button>
              <button onClick={() => remove(c.id)} className="muted mr-1 rounded p-1.5 opacity-0 hover:text-red-600 group-hover:opacity-100 focus:opacity-100" aria-label="Delete conversation"><Trash2 className="size-3.5" /></button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="surface flex min-w-0 flex-1 flex-col rounded-xl">
        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {msgs.length === 0 && !busy && (
            <div className="mx-auto max-w-lg pt-10 text-center">
              <h1 className="text-2xl font-bold">{t('assistant')}</h1>
              <p className="muted mt-2 text-sm">Answers are drawn from the AgriMind knowledge base and cite their sources as [1], [2]… Click a source to read the passage. Ask in English, ಕನ್ನಡ or हिन्दी.</p>
            </div>
          )}
          {msgs.map((m, i) => m.role === 'user' ? (
            <div key={i} className="flex justify-end"><div className="max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-navy-900 px-4 py-2.5 text-white dark:bg-navy-700">{m.content}</div></div>
          ) : (
            <div key={i} className="max-w-[92%]">
              <div className="prose-agri"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown></div>
              <Citations items={m.citations ?? []} />
              {m.meta?.provider && (
                <div className="muted mt-2 flex flex-wrap items-center gap-2 text-xs">
                  <span>{m.meta.provider === 'xai' ? 'Grok' : m.meta.provider} · {m.meta.model} · {(m.meta.latency_ms / 1000).toFixed(1)} s{m.meta.usage?.total_tokens ? ` · ${m.meta.usage.total_tokens} tokens` : ''}</span>
                  {m.meta.grounding?.groundedness != null && (
                    <Badge tone={m.meta.grounding.groundedness >= 0.8 ? 'good' : m.meta.grounding.groundedness >= 0.5 ? 'warn' : 'bad'}>
                      grounded {pct(m.meta.grounding.groundedness, 0)} of {m.meta.grounding.n_claims} claims</Badge>)}
                  {m.meta.fallback && <Badge tone="warn">retrieval only</Badge>}
                </div>
              )}
            </div>
          ))}
          {busy && <div className="muted flex items-center gap-2 text-sm"><span className="typing text-lg leading-none"><span>•</span><span>•</span><span>•</span></span>{useKb ? t('thinking') : t('loading')}</div>}
          <div ref={end} />
        </div>
        <form onSubmit={submit} className="border-t line p-3">
          <div className="flex items-end gap-2">
            <textarea value={input} onChange={e => setInput(e.target.value)} rows={1} placeholder={t('askPlaceholder')} aria-label={t('askPlaceholder')}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
              className="max-h-40 min-h-[44px] flex-1 resize-y rounded-xl border line bg-[var(--surface-2)] px-4 py-2.5 focus:border-leaf-500 focus:outline-none" />
            <button disabled={busy || !input.trim()} className="rounded-xl bg-leaf-600 p-3 text-white hover:bg-leaf-700 disabled:opacity-40" aria-label={t('send')}><SendHorizontal className="size-5" /></button>
          </div>
          <label className="muted mt-2 flex items-center gap-2 text-xs"><input type="checkbox" checked={useKb} onChange={e => setUseKb(e.target.checked)} className="accent-leaf-600" />{t('useKb')}</label>
        </form>
      </section>
    </div>
  )
}
