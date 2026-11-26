import { ExternalLink, MessageSquare } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge, Button, Input, Notice, PageHead, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { useApp } from '../lib/app-context'

export default function Schemes() {
  const { t } = useApp()
  const nav = useNavigate()
  const [d, setD] = useState<any>(null)
  const [q, setQ] = useState('')
  const [cat, setCat] = useState('All')
  const [open, setOpen] = useState<string | null>('pm-kisan')
  useEffect(() => { api('/schemes').then(setD) }, [])
  if (!d) return <Spinner />
  const cats = ['All', ...Array.from(new Set<string>(d.schemes.map((s: any) => s.category)))]
  const list = d.schemes.filter((s: any) => (cat === 'All' || s.category === cat) && JSON.stringify(s).toLowerCase().includes(q.toLowerCase()))

  return (
    <div className="mx-auto max-w-4xl">
      <PageHead title={t('schemes')} intro={`Central government schemes for farmers. Details checked against official sources on ${d.last_verified}.`} />
      <Notice tone="warn">{d.disclaimer}</Notice>
      <div className="my-5 flex flex-wrap gap-2">
        <Input value={q} onChange={e => setQ(e.target.value)} placeholder="Search schemes, e.g. insurance, pension, drip" className="max-w-xs" aria-label="Search schemes" />
        {cats.map(c => <button key={c} onClick={() => setCat(c)} className={`rounded-full border px-3 py-1 text-sm ${cat === c ? 'border-leaf-600 bg-leaf-600 text-white' : 'line'}`}>{c}</button>)}
      </div>
      <div className="space-y-3">
        {list.map((s: any) => (
          <article key={s.id} className="surface rounded-xl">
            <button onClick={() => setOpen(open === s.id ? null : s.id)} aria-expanded={open === s.id} className="flex w-full items-start justify-between gap-4 p-5 text-left">
              <div><h2 className="text-lg font-semibold">{s.name}</h2><p className="muted mt-1 text-sm">{s.benefit.split('. ')[0]}.</p></div>
              <Badge tone="info">{s.category}</Badge>
            </button>
            {open === s.id && (
              <div className="grid gap-5 border-t line p-5 text-sm md:grid-cols-2">
                <div className="md:col-span-2"><h3 className="mb-1 font-semibold">{t('benefit')}</h3><p>{s.benefit}</p></div>
                <div><h3 className="mb-1 font-semibold">{t('eligibility')}</h3><ul className="list-disc space-y-1 pl-5">{s.eligibility.map((e: string) => <li key={e}>{e}</li>)}</ul></div>
                <div><h3 className="mb-1 font-semibold">{t('howToApply')}</h3><ol className="list-decimal space-y-1 pl-5">{s.how_to_apply.map((e: string) => <li key={e}>{e}</li>)}</ol>
                  <h3 className="mt-3 mb-1 font-semibold">{t('documents')}</h3><p>{s.documents.join(', ')}</p></div>
                <div className="flex flex-wrap items-center gap-3 md:col-span-2">
                  <a href={s.official_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 font-semibold text-leaf-600 hover:underline">{t('officialSite')} <ExternalLink className="size-3.5" /></a>
                  <Button variant="ghost" onClick={() => nav('/assistant', { state: { ask: `Am I eligible for ${s.name} and how do I apply?` } })}><MessageSquare className="size-4" />Ask about this scheme</Button>
                  <span className="muted text-xs">Sources: {s.sources.map((u: string, i: number) => <a key={u} href={u} target="_blank" rel="noreferrer" className="underline">[{i + 1}]</a>)}</span>
                </div>
              </div>
            )}
          </article>
        ))}
        {list.length === 0 && <p className="muted">No schemes match “{q}”.</p>}
      </div>
    </div>
  )
}
