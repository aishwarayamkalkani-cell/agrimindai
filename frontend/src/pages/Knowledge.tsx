import { FileText, Search, Trash2, Upload } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Badge, Button, Empty, Input, Notice, PageHead, Panel, Spinner } from '../components/ui'
import { api, fmtDate } from '../lib/api'
import { useApp } from '../lib/app-context'

export default function Knowledge() {
  const { t, user, toast } = useApp()
  const [docs, setDocs] = useState<any[] | null>(null)
  const [q, setQ] = useState('')
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [view, setView] = useState<{ doc: any; chunks: any[] } | null>(null)
  const file = useRef<HTMLInputElement>(null)

  const load = () => api('/documents').then(setDocs)
  useEffect(() => { load() }, [])

  const upload = async (files: FileList | null) => {
    if (!files?.length) return
    setUploading(true)
    for (const f of Array.from(files)) {
      const fd = new FormData(); fd.append('file', f)
      try { const d = await api('/documents', { form: fd }); toast(`Added “${d.title}” (${d.n_chunks} passages)`) }
      catch (e: any) { toast(`${f.name}: ${e.message}`, 'error') }
    }
    setUploading(false); if (file.current) file.current.value = ''; load()
  }
  const search = async (e: FormEvent) => {
    e.preventDefault(); if (q.trim().length < 2) return
    setBusy(true); try { setRes(await api(`/search?q=${encodeURIComponent(q)}&k=6`)) } catch (x: any) { toast(x.message, 'error') } finally { setBusy(false) }
  }
  const remove = async (d: any) => {
    if (!confirm(`Delete “${d.title}” from the knowledge base?`)) return
    try { await api(`/documents/${d.id}`, { method: 'DELETE' }); toast('Document deleted'); load(); setView(null) } catch (e: any) { toast(e.message, 'error') }
  }
  const open = async (d: any) => setView({ doc: d, chunks: await api(`/documents/${d.id}/chunks`) })

  return (
    <div className="mx-auto max-w-6xl">
      <PageHead title={t('knowledge')} intro="Documents here are split into passages, embedded and indexed with FAISS. The assistant retrieves the closest passages and cites them.">
        <input ref={file} type="file" multiple accept=".pdf,.docx,.txt,.md,.csv" className="hidden" onChange={e => upload(e.target.files)} />
        <Button onClick={() => file.current?.click()} loading={uploading}><Upload className="size-4" />{t('upload')}</Button>
      </PageHead>

      <Panel className="mb-6">
        <form onSubmit={search} className="flex gap-2">
          <Input value={q} onChange={e => setQ(e.target.value)} placeholder={t('searchKb')} aria-label={t('searchKb')} />
          <Button loading={busy}><Search className="size-4" />{t('search')}</Button>
        </form>
        {res && (
          <div className="mt-4 space-y-3">
            <p className="muted text-xs">{res.results.length} passages in {res.latency_ms} ms · {res.embedder.kind} ({res.embedder.model.split('/').pop()})</p>
            {res.results.map((h: any, i: number) => (
              <div key={h.id} className="rounded-lg border line p-3">
                <div className="mb-1 flex flex-wrap items-center gap-2 text-sm"><span className="font-semibold">{i + 1}. {h.title}</span><Badge tone="info">score {h.score.toFixed(3)}</Badge>{h.page && <Badge>p.{h.page}</Badge>}</div>
                <p className="muted whitespace-pre-line text-sm">{h.text.slice(0, 500)}{h.text.length > 500 ? '…' : ''}</p>
              </div>
            ))}
            {res.embedder.note && <Notice tone="warn">{res.embedder.note}</Notice>}
          </div>
        )}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
        <Panel title={`Documents (${docs?.length ?? 0})`}>
          {!docs ? <Spinner /> : docs.length === 0 ? <Empty title="No documents yet">Upload PDF, DOCX, TXT, Markdown or CSV files.</Empty> : (
            <ul className="divide-y divide-[var(--line)]">
              {docs.map(d => (
                <li key={d.id} className={`flex items-center gap-3 py-2.5 ${view?.doc.id === d.id ? 'text-leaf-600' : ''}`}>
                  <FileText className="muted size-4 shrink-0" />
                  <button onClick={() => open(d)} className="min-w-0 flex-1 text-left">
                    <span className="block truncate text-sm font-semibold">{d.title}</span>
                    <span className="muted text-xs">{d.file_type.toUpperCase()} · {(d.size_bytes / 1024).toFixed(0)} KB · {d.n_chunks} passages · {d.is_demo ? 'demo' : d.uploader ?? '—'} · {fmtDate(d.created_at)}</span>
                  </button>
                  {(user?.role === 'admin' || d.uploaded_by === user?.id) &&
                    <button onClick={() => remove(d)} className="muted rounded p-1.5 hover:text-red-600" aria-label={`Delete ${d.title}`}><Trash2 className="size-4" /></button>}
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title={view ? view.doc.title : 'Passages'}>
          {!view ? <p className="muted text-sm">Select a document to see how it was split into passages for retrieval.</p> : (
            <ol className="max-h-[60vh] space-y-2 overflow-y-auto pr-1">
              {view.chunks.map(c => <li key={c.id} className="surface-2 rounded-lg border line p-3 text-xs leading-relaxed whitespace-pre-line"><span className="font-semibold">#{c.idx + 1}{c.page ? ` · p.${c.page}` : ''}</span>  {c.text}</li>)}
            </ol>
          )}
        </Panel>
      </div>
    </div>
  )
}
