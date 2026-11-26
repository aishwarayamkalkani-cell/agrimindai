import { ImagePlus, MessageSquare } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Badge, Button, Metric, Notice, PageHead, Panel, Spinner } from '../components/ui'
import { api, getToken, pct } from '../lib/api'
import { useApp } from '../lib/app-context'

const pretty = (c: string) => c.replace('___', ' – ').replace(/_/g, ' ').replace('Corn (maize)', 'Maize').replace('Pepper, bell', 'Bell pepper')

export default function Disease() {
  const { t, toast } = useApp()
  const nav = useNavigate()
  const [info, setInfo] = useState<any>(null)
  const [img, setImg] = useState<string | null>(null)
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [drag, setDrag] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { api('/disease/info').then(setInfo) }, [])

  const run = async (f: File | Blob, name = 'leaf.jpg') => {
    setImg(URL.createObjectURL(f)); setRes(null); setBusy(true)
    const fd = new FormData(); fd.append('file', f, name)
    try { setRes(await api('/disease/predict', { form: fd })) } catch (e: any) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  const sample = async (n: string) => {
    const r = await fetch(`/api/disease/samples/${n}`, { headers: { Authorization: `Bearer ${getToken()}` } })
    run(await r.blob(), n)
  }
  const m = info?.metrics
  const perClass = m ? Object.entries(m.per_class).map(([k, v]: any) => ({ name: pretty(k), f1: +(v['f1-score'] * 100).toFixed(1) })) : []

  return (
    <div className="mx-auto max-w-6xl">
      <PageHead title={t('disease')} intro="A MobileNetV3 network fine-tuned on PlantVillage leaf images recognises 19 conditions in tomato, potato, maize and bell pepper." />
      <div className="grid gap-6 lg:grid-cols-[1fr_1.15fr]">
        <div className="space-y-4">
          <div onDragOver={e => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
            onDrop={e => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) run(f, f.name) }}
            className={`surface flex aspect-[4/3] flex-col items-center justify-center overflow-hidden rounded-xl border-2 border-dashed ${drag ? 'border-leaf-500 bg-leaf-600/5' : 'line'}`}>
            {img ? <img src={img} alt="Uploaded leaf" className="h-full w-full object-contain" /> : (
              <button onClick={() => input.current?.click()} className="flex flex-col items-center gap-2 p-6 text-center">
                <ImagePlus className="size-10 text-leaf-600" /><span className="font-semibold">{t('uploadLeaf')}</span><span className="muted text-xs">JPG or PNG · one leaf, plain background works best</span>
              </button>)}
          </div>
          <input ref={input} type="file" accept="image/*" capture="environment" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) run(f, f.name); e.target.value = '' }} />
          <div className="flex gap-2"><Button onClick={() => input.current?.click()} loading={busy}>{t('predict')}</Button>{img && <Button variant="ghost" onClick={() => { setImg(null); setRes(null) }}>Clear</Button>}</div>
          {info?.samples?.length > 0 && (
            <div>
              <p className="muted mb-2 text-xs">Or try a held-out test image (not seen during training):</p>
              <div className="flex flex-wrap gap-1.5">{info.samples.map((s: string) => (
                <button key={s} onClick={() => sample(s)} className="rounded-md border line px-2 py-1 text-xs hover:border-leaf-500">{pretty(s.replace('.jpg', '').replace('Corn_(maize)', 'Corn (maize)').replace('Pepper_bell', 'Pepper, bell'))}</button>))}</div>
            </div>
          )}
        </div>

        <div className="space-y-4">
          {busy && <Panel><Spinner label="Running the model…" /></Panel>}
          {res && (
            <Panel title="Diagnosis">
              <div className="flex flex-wrap items-baseline gap-3">
                <h2 className="text-2xl font-bold">{res.top.crop}: {res.top.disease}</h2>
                <Badge tone={res.top.confidence >= 0.75 ? 'good' : res.top.confidence >= 0.5 ? 'warn' : 'bad'}>{t('confidence')} {pct(res.top.confidence)}</Badge>
              </div>
              {res.top.pathogen !== '—' && <p className="muted mt-1 text-sm italic">{res.top.pathogen}</p>}
              <p className="mt-3 text-sm">{res.top.advice}</p>
              {res.warnings.map((w: string) => <div key={w} className="mt-3"><Notice tone="warn">{w}</Notice></div>)}
              <h3 className="mt-5 mb-2 text-sm font-semibold">Top predictions</h3>
              <ul className="space-y-2">{res.predictions.map((p: any) => (
                <li key={p.class} className="text-sm"><div className="flex justify-between"><span>{p.crop} – {p.disease}</span><span className="tabular-nums">{pct(p.confidence)}</span></div>
                  <div className="mt-1 h-1.5 rounded-full bg-[var(--surface-2)]"><div className="h-1.5 rounded-full bg-leaf-600" style={{ width: `${p.confidence * 100}%` }} /></div></li>))}</ul>
              <p className="muted mt-4 text-xs">{res.model} · {res.device} · {res.latency_ms} ms · normalised entropy {res.uncertainty}</p>
              {!res.top.healthy && <Button variant="ghost" className="mt-4" onClick={() => nav('/assistant', { state: { ask: `How do I manage ${res.top.disease} in ${res.top.crop}? What are the symptoms and prevention steps?` } })}><MessageSquare className="size-4" />Ask the assistant about {res.top.disease}</Button>}
            </Panel>
          )}
          {m && (
            <Panel title="Model evaluation" tone="soft">
              <div className="grid grid-cols-3 gap-4">
                <Metric label="Test accuracy" value={pct(m.test_accuracy)} />
                <Metric label="Macro F1" value={pct(m.test_macro_f1)} />
                <Metric label="Test images" value={m.split.test} sub={`train ${m.split.train} · val ${m.split.val}`} />
              </div>
              <div className="mt-4 h-[470px]">
                <ResponsiveContainer><BarChart data={perClass} layout="vertical" margin={{ left: 10, right: 10 }}>
                  <CartesianGrid horizontal={false} stroke="var(--line)" /><XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11, fill: 'var(--muted)' }} unit="%" />
                  <YAxis type="category" dataKey="name" width={190} tick={{ fontSize: 10.5, fill: 'var(--muted)' }} interval={0} />
                  <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 8 }} formatter={(v: any) => [`${v}%`, 'F1']} />
                  <Bar dataKey="f1" fill="#2f7d4f" radius={[0, 3, 3, 0]} barSize={9} />
                </BarChart></ResponsiveContainer>
              </div>
              <Notice tone="warn"><b>{t('limitations')}.</b> {m.limitations} Only the 19 listed conditions can be recognised; any other crop or disease will be forced into one of them.</Notice>
              <p className="muted mt-3 text-xs">{m.dataset}. Held-out test split, trained {m.trained_at}.</p>
            </Panel>
          )}
        </div>
      </div>
    </div>
  )
}
