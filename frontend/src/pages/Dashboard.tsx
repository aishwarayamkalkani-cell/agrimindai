import { ArrowUpRight, Bot, CloudSun, Landmark, Layers, Leaf, Tractor } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Badge, Notice, Panel, Spinner } from '../components/ui'
import { api, fmtDate, pct } from '../lib/api'
import { useApp } from '../lib/app-context'

const SEASON_NOTE: Record<string, string> = {
  Kharif: 'Monsoon crops in the field: watch for blast in paddy, fall armyworm in maize and leaf spots after rain.',
  Rabi: 'Post-monsoon sowing of chickpea, wheat, rabi jowar and vegetables; plan irrigation around critical stages.',
  'Zaid (summer)': 'Irrigated summer crops: mulch, irrigate in the evening and watch for mites and heat stress.',
}

export default function Dashboard() {
  const { user, t, lang } = useApp()
  const nav = useNavigate()
  const [d, setD] = useState<any>(null)
  const [q, setQ] = useState('')
  useEffect(() => { api('/dashboard').then(setD).catch(() => setD({})) }, [])

  const ask = (e: FormEvent) => { e.preventDefault(); if (q.trim()) nav('/assistant', { state: { ask: q.trim() } }) }
  const tools = [
    { to: '/disease', icon: Leaf, title: t('disease'), text: 'Photograph a tomato, potato, maize or capsicum leaf for a diagnosis.' },
    { to: '/soil', icon: Layers, title: t('soil'), text: 'Turn a soil test report into ratings, suitable crops and fertiliser doses.' },
    { to: '/farming', icon: Tractor, title: t('farming'), text: 'Crop recommendation, irrigation scheduling and district crop history.' },
    { to: '/weather', icon: CloudSun, title: t('weather'), text: 'Forecast with spray windows, disease-risk alerts and mandi prices.' },
    { to: '/schemes', icon: Landmark, title: t('schemes'), text: 'PM-KISAN, PMFBY, KCC, drip subsidy and more with eligibility.' },
  ]

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <section className="furrows relative overflow-hidden rounded-2xl bg-navy-900 px-6 py-8 text-white sm:px-10 sm:py-10">
        <div className="text-sm text-shoot">{d ? `${t('season')}: ${d.season}` : ' '}</div>
        <h1 className="mt-1 text-[2.1rem] font-bold sm:text-[2.6rem]">{t('welcome')}, {user?.name.split(' ')[0]}.</h1>
        <p className="mt-2 max-w-xl text-white/70">{d?.season ? SEASON_NOTE[d.season] : ''}</p>
        <form onSubmit={ask} className="mt-6 flex max-w-2xl gap-2 rounded-xl bg-white/8 p-1.5 ring-1 ring-white/15 focus-within:ring-shoot">
          <input value={q} onChange={e => setQ(e.target.value)} placeholder={t('askPlaceholder')} aria-label={t('quickAsk')}
            className="min-w-0 flex-1 bg-transparent px-3 text-white placeholder:text-white/45 focus:outline-none" />
          <button className="flex shrink-0 items-center gap-2 rounded-lg bg-shoot px-4 py-2 text-sm font-bold text-navy-900 hover:bg-white" aria-label={t("quickAsk")}><Bot className="size-4" /><span className="hidden sm:inline">{t("quickAsk")}</span></button>
        </form>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {(lang === 'kn' ? ['ಟೊಮೆಟೊ ಎಲೆ ಮುರುಟು ರೋಗ ನಿಯಂತ್ರಣ ಹೇಗೆ?', 'ರಾಗಿ ಬಿತ್ತನೆ ಅಂತರ ಎಷ್ಟು?'] : lang === 'hi' ? ['टमाटर में झुलसा रोग कैसे रोकें?', 'ड्रिप सिंचाई पर कितनी सब्सिडी है?'] :
            ['How do I manage late blight in tomato?', 'What subsidy is there for drip irrigation?', 'When should I harvest paddy?']).map(s => (
            <button key={s} onClick={() => nav('/assistant', { state: { ask: s } })} className="rounded-full border border-white/20 px-3 py-1 text-white/80 hover:border-shoot hover:text-white">{s}</button>
          ))}
        </div>
      </section>

      {!d ? <Spinner /> : (
        <>
          {d.llm && !d.llm.configured && (
            <Notice tone="warn">Grok is not configured yet, so the assistant can only return retrieved passages.
              {user?.role === 'admin' ? <> Add an xAI API key or switch to Ollama in <Link className="font-semibold underline" to="/admin">Admin → Model configuration</Link>.</> : ' Ask your administrator to add an xAI API key.'}</Notice>
          )}
          <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr] [&>*]:min-w-0">
            <Panel title="Tools">
              <ul className="divide-y divide-[var(--line)]">
                {tools.map(x => (
                  <li key={x.to}>
                    <Link to={x.to} className="group flex items-start gap-4 py-3.5 first:pt-0">
                      <span className="mt-0.5 rounded-lg bg-leaf-600/10 p-2 text-leaf-600 dark:text-shoot"><x.icon className="size-5" /></span>
                      <span className="flex-1"><span className="block font-semibold group-hover:text-leaf-600">{x.title}</span><span className="muted text-sm">{x.text}</span></span>
                      <ArrowUpRight className="muted mt-1 size-4 opacity-0 transition-opacity group-hover:opacity-100" />
                    </Link>
                  </li>
                ))}
              </ul>
            </Panel>
            <div className="space-y-6">
              <Panel title="System" tone="soft">
                <dl className="grid grid-cols-2 gap-x-4 gap-y-4 text-sm">
                  <div><dt className="muted text-xs">Knowledge base</dt><dd className="font-display text-xl font-bold">{d.documents} docs</dd><dd className="muted text-xs">{d.chunks} indexed passages</dd></div>
                  <div><dt className="muted text-xs">Language model</dt><dd className="font-semibold break-all">{d.llm.model}</dd><dd>{d.llm.configured ? <Badge tone="good">{d.llm.label}</Badge> : <Badge tone="warn">not configured</Badge>}</dd></div>
                  <div><dt className="muted text-xs">Leaf disease model</dt><dd className="font-display text-xl font-bold">{pct(d.disease_accuracy)}</dd><dd className="muted text-xs">test accuracy, 19 classes</dd></div>
                  <div><dt className="muted text-xs">Embeddings</dt><dd className="font-semibold">{d.embedder.kind === 'sentence-transformers' ? 'Sentence-Transformers' : 'TF-IDF fallback'}</dd><dd className="muted text-xs">{d.embedder.device}</dd></div>
                </dl>
              </Panel>
              <Panel title="Recent conversations" action={<Link to="/assistant" className="text-sm font-semibold text-leaf-600">Open</Link>}>
                {d.conversations.length === 0 ? <p className="muted text-sm">{t('noChats')}</p> : (
                  <ul className="space-y-2 text-sm">{d.conversations.map((c: any) => (
                    <li key={c.id}><Link to={`/assistant/${c.id}`} className="flex justify-between gap-3 hover:text-leaf-600"><span className="truncate">{c.title}</span><span className="muted shrink-0 text-xs">{fmtDate(c.updated_at)}</span></Link></li>))}</ul>
                )}
              </Panel>
            </div>
          </div>
          {d.recent.length > 0 && (
            <Panel title="Your recent activity">
              <ul className="space-y-1.5 text-sm">{d.recent.map((r: any, i: number) => (
                <li key={i} className="flex gap-3"><Badge>{r.feature}</Badge><span className="truncate">{r.query}</span><span className="muted ml-auto shrink-0 text-xs">{fmtDate(r.created_at)}</span></li>))}</ul>
            </Panel>
          )}
        </>
      )}
    </div>
  )
}
