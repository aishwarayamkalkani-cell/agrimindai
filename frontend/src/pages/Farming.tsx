import { useEffect, useState, type FormEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Badge, Button, chartColors, Field, Input, Metric, Notice, PageHead, Panel, Select, Spinner, Tabs } from '../components/ui'
import { api, pct } from '../lib/api'
import { useApp } from '../lib/app-context'
import { Citations } from './Assistant'

const tip = { contentStyle: { background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 8, fontSize: 12 } }
type Tab = 'crop' | 'fert' | 'irr' | 'plan' | 'advisor'

export default function Farming() {
  const { t } = useApp()
  const [tab, setTab] = useState<Tab>('crop')
  const [meta, setMeta] = useState<any>(null)
  useEffect(() => { api('/farming/meta').then(setMeta) }, [])
  return (
    <div className="mx-auto max-w-6xl">
      <PageHead title={t('farming')} intro={meta ? `${t('season')}: ${meta.season}. Plan what to grow, how much fertiliser to buy and how much to irrigate.` : ''} />
      <Tabs value={tab} onChange={setTab} items={[{ id: 'crop', label: 'Crop recommendation' }, { id: 'fert', label: 'Fertiliser calculator' },
        { id: 'irr', label: 'Irrigation planner' }, { id: 'plan', label: 'District crop history' }, { id: 'advisor', label: 'AI farm advisor' }]} />
      {!meta ? <Spinner /> : tab === 'crop' ? <CropRec /> : tab === 'fert' ? <Fert /> : tab === 'irr' ? <Irrigation meta={meta} /> : tab === 'plan' ? <Plan meta={meta} /> : <Advisor />}
    </div>
  )
}

function CropRec() {
  const { t, toast } = useApp()
  const [f, setF] = useState({ N: 90, P: 42, K: 43, temperature: 26, humidity: 80, ph: 6.5, rainfall: 200 })
  const [r, setR] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const go = async (e: FormEvent) => { e.preventDefault(); setBusy(true); try { setR(await api('/farming/recommend-crop', { body: f })) } catch (x: any) { toast(x.message, 'error') } finally { setBusy(false) } }
  const fields: [keyof typeof f, string][] = [['N', 'Nitrogen (N)'], ['P', 'Phosphorus (P)'], ['K', 'Potassium (K)'], ['temperature', 'Temperature (°C)'], ['humidity', 'Humidity (%)'], ['ph', 'pH'], ['rainfall', 'Rainfall (mm)']]
  return (
    <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
      <Panel title="Field conditions">
        <form onSubmit={go} className="grid grid-cols-2 gap-3">
          {fields.map(([k, l]) => <Field key={k} label={l}><Input type="number" step="any" required value={f[k]} onChange={e => setF({ ...f, [k]: +e.target.value })} /></Field>)}
          <Button className="col-span-2" loading={busy}>{t('recommend')}</Button>
        </form>
        <p className="muted mt-3 text-xs">N, P and K use the scale of the training dataset (N 0–140, P 5–145, K 5–205), not soil-test kg/ha. Rainfall is the seasonal total.</p>
      </Panel>
      {!r ? <Panel tone="soft"><p className="muted text-sm">The model ranks 22 crops by probability and shows how your inputs compare with fields where each crop was grown.</p></Panel> : (
        <div className="space-y-6">
          {r.out_of_range.length > 0 && <Notice tone="warn">Outside the model's training data, so treat with caution: {r.out_of_range.join('; ')}.</Notice>}
          <Panel title="Recommended crops">
            <ol className="space-y-4">{r.recommendations.map((c: any, i: number) => (
              <li key={c.crop}>
                <div className="flex items-center justify-between"><span className="font-display text-lg font-bold capitalize">{i + 1}. {c.crop}</span><Badge tone={i === 0 ? 'good' : 'neutral'}>{pct(c.probability)}</Badge></div>
                <div className="mt-1.5 flex flex-wrap gap-1.5 text-xs">{Object.entries(c.comparison).map(([k, v]: any) => (
                  <span key={k} title={`typical ${v.p10}–${v.p90}`} className={`rounded px-1.5 py-0.5 ${v.status === 'typical' ? 'bg-leaf-600/10 text-leaf-700 dark:text-shoot' : 'bg-turmeric/15 text-soil-700 dark:text-turmeric'}`}>{k} {v.status}</span>))}</div>
              </li>))}</ol>
          </Panel>
          <Panel title="Model" tone="soft">
            <div className="grid grid-cols-3 gap-4"><Metric label="Selected model" value={<span className="text-base">{r.metrics.selected_model}</span>} /><Metric label="Test accuracy" value={pct(r.metrics.test_accuracy)} /><Metric label="Macro F1" value={pct(r.metrics.test_macro_f1)} /></div>
            <p className="muted mt-3 text-xs">{r.metrics.dataset}. {r.metrics.limitations}</p>
          </Panel>
        </div>
      )}
    </div>
  )
}

function Fert() {
  const { toast } = useApp()
  const presets: Record<string, [number, number, number]> = { 'Rice (irrigated)': [100, 50, 50], 'Ragi (rain-fed)': [50, 40, 25], 'Tomato (hybrid)': [225, 125, 125], Custom: [0, 0, 0] }
  const [preset, setPreset] = useState('Rice (irrigated)')
  const [f, setF] = useState({ N: 100, P2O5: 50, K2O: 50, area_ha: 1, aN: 'Medium', aP: 'Medium', aK: 'Medium' })
  const [r, setR] = useState<any>(null)
  const pick = (p: string) => { setPreset(p); const v = presets[p]; if (p !== 'Custom') setF({ ...f, N: v[0], P2O5: v[1], K2O: v[2] }) }
  const go = async (e: FormEvent) => {
    e.preventDefault()
    try { setR(await api('/farming/fertiliser', { body: { N: f.N, P2O5: f.P2O5, K2O: f.K2O, area_ha: f.area_ha, adjust: { N: f.aN, P: f.aP, K: f.aK } } })) } catch (x: any) { toast(x.message, 'error') }
  }
  const lvl = (k: 'aN' | 'aP' | 'aK') => <Select value={f[k]} onChange={e => setF({ ...f, [k]: e.target.value })}>{['Low', 'Medium', 'High'].map(x => <option key={x}>{x}</option>)}</Select>
  return (
    <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
      <Panel title="Recommended dose">
        <form onSubmit={go} className="grid grid-cols-3 gap-3">
          <div className="col-span-3"><Field label="Crop preset" hint="Typical package-of-practice doses; use your Soil Health Card dose if you have one."><Select value={preset} onChange={e => pick(e.target.value)}>{Object.keys(presets).map(p => <option key={p}>{p}</option>)}</Select></Field></div>
          <Field label="N kg/ha"><Input type="number" min={0} value={f.N} onChange={e => setF({ ...f, N: +e.target.value })} /></Field>
          <Field label="P₂O₅ kg/ha"><Input type="number" min={0} value={f.P2O5} onChange={e => setF({ ...f, P2O5: +e.target.value })} /></Field>
          <Field label="K₂O kg/ha"><Input type="number" min={0} value={f.K2O} onChange={e => setF({ ...f, K2O: +e.target.value })} /></Field>
          <Field label="Soil N">{lvl('aN')}</Field><Field label="Soil P">{lvl('aP')}</Field><Field label="Soil K">{lvl('aK')}</Field>
          <div className="col-span-3"><Field label="Area (hectares)" hint="1 acre = 0.405 ha"><Input type="number" step="0.01" min={0.01} value={f.area_ha} onChange={e => setF({ ...f, area_ha: +e.target.value })} /></Field></div>
          <Button className="col-span-3">Calculate</Button>
        </form>
      </Panel>
      {!r ? <Panel tone="soft"><p className="muted text-sm">Converts a nutrient recommendation into bags of DAP, urea and muriate of potash, adjusted for your soil-test rating.</p></Panel> : (
        <Panel title="Fertiliser to buy">
          <div className="grid grid-cols-3 gap-4">{Object.entries(r.products_total_kg).map(([k, v]: any) => <Metric key={k} label={k} value={`${v} kg`} sub={`${r.bags_50kg_total[k]} bags of 50 kg`} />)}</div>
          <p className="muted mt-3 text-sm">Adjusted target per hectare: N {r.target_per_ha.N}, P₂O₅ {r.target_per_ha.P2O5}, K₂O {r.target_per_ha.K2O} kg.</p>
          <h3 className="mt-4 mb-1 text-sm font-semibold">When to apply</h3>
          <ul className="list-disc space-y-1 pl-5 text-sm">{r.schedule.map((s: string) => <li key={s}>{s}</li>)}</ul>
          <p className="muted mt-3 text-xs">{r.basis}</p>
        </Panel>
      )}
    </div>
  )
}

function Irrigation({ meta }: { meta: any }) {
  const { toast } = useApp()
  const [f, setF] = useState({ crop: 'Tomato', stage: 'mid', method: 'drip', area_ha: 1, place: 'Mandya' })
  const [loc, setLoc] = useState<any>(null)
  const [manual, setManual] = useState('5.2, 5.0, 4.8, 5.5, 5.1, 4.9, 5.3')
  const [r, setR] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const go = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true)
    try {
      let l = loc
      if (!l && f.place.trim()) { const g = await api(`/weather/geocode?q=${encodeURIComponent(f.place)}`).catch(() => []); l = g[0]; setLoc(l ?? null) }
      const body: any = { crop: f.crop, stage: f.stage, method: f.method, area_ha: f.area_ha, et0: manual.split(',').map(Number).filter(x => !isNaN(x)) }
      if (l) { body.lat = l.lat; body.lon = l.lon }
      setR(await api('/farming/irrigation', { body }))
    } catch (x: any) { toast(x.message, 'error') } finally { setBusy(false) }
  }
  return (
    <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
      <Panel title="Crop and field">
        <form onSubmit={go} className="space-y-3">
          <Field label="Crop"><Select value={f.crop} onChange={e => setF({ ...f, crop: e.target.value })}>{meta.irrigation_crops.map((c: string) => <option key={c}>{c}</option>)}</Select></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Growth stage"><Select value={f.stage} onChange={e => setF({ ...f, stage: e.target.value })}>{['initial', 'development', 'mid', 'late'].map(s => <option key={s}>{s}</option>)}</Select></Field>
            <Field label="Method"><Select value={f.method} onChange={e => setF({ ...f, method: e.target.value })}>{meta.methods.map((s: string) => <option key={s}>{s}</option>)}</Select></Field>
          </div>
          <Field label="Area (ha)"><Input type="number" step="0.01" min={0.01} value={f.area_ha} onChange={e => setF({ ...f, area_ha: +e.target.value })} /></Field>
          <Field label="Village / town" hint={loc ? `Using ${loc.name}, ${loc.admin1}` : 'Forecast ET₀ and rain come from Open-Meteo.'}><Input value={f.place} onChange={e => { setF({ ...f, place: e.target.value }); setLoc(null) }} /></Field>
          <Field label="Fallback ET₀ (mm/day, comma separated)" hint="Used only if the weather service cannot be reached."><Input value={manual} onChange={e => setManual(e.target.value)} /></Field>
          <Button className="w-full" loading={busy}>Plan irrigation</Button>
        </form>
      </Panel>
      {!r ? <Panel tone="soft"><p className="muted text-sm">Estimates crop water use with the FAO-56 method (ETc = Kc × ET₀), subtracts forecast rain and converts it to litres for your field.</p></Panel> : (
        <Panel title={`${r.crop}, ${r.stage} stage (Kc ${r.kc})`}>
          <div className="grid grid-cols-3 gap-4">
            <Metric label="Net need, 7 days" value={`${r.net_total_mm} mm`} />
            <Metric label={`Gross with ${r.method}`} value={`${r.gross_total_mm} mm`} sub={`efficiency ${pct(r.efficiency, 0)}`} />
            <Metric label="Water per day" value={`${(r.litres_per_day / 1000).toFixed(1)} kL`} sub={`${r.litres_total.toLocaleString()} L total`} />
          </div>
          <div className="mt-5 h-64"><ResponsiveContainer><BarChart data={r.days}>
            <CartesianGrid vertical={false} stroke="var(--line)" /><XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--muted)' }} /><YAxis unit=" mm" tick={{ fontSize: 11, fill: 'var(--muted)' }} />
            <Tooltip {...tip} /><Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="etc" name="Crop water use (ETc)" fill={chartColors[0]} radius={[3, 3, 0, 0]} />
            <Bar dataKey="effective_rain" name="Effective rain" fill={chartColors[2]} radius={[3, 3, 0, 0]} />
            <Bar dataKey="net_mm" name="Irrigation needed" fill={chartColors[1]} radius={[3, 3, 0, 0]} />
          </BarChart></ResponsiveContainer></div>
          <p className="muted mt-2 text-xs">{r.note} Weather: {r.weather_source}.</p>
        </Panel>
      )}
    </div>
  )
}

function Plan({ meta }: { meta: any }) {
  const opts = meta.crop_stats
  const [state, setState] = useState('Karnataka')
  const [dists, setDists] = useState<string[]>([])
  const [district, setDistrict] = useState('')
  const [season, setSeason] = useState('All')
  const [r, setR] = useState<any>(null)
  useEffect(() => { api(`/farming/districts?state=${encodeURIComponent(state)}`).then(d => { setDists(d); setDistrict('') }) }, [state])
  useEffect(() => {
    setR(null)
    const p = new URLSearchParams({ state, ...(district && { district }), ...(season !== 'All' && { season }) })
    api(`/farming/crop-stats?${p}`).then(setR)
  }, [state, district, season])
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="State"><Select value={state} onChange={e => setState(e.target.value)}>{opts.states.map((s: string) => <option key={s}>{s}</option>)}</Select></Field>
        <Field label="District"><Select value={district} onChange={e => setDistrict(e.target.value)}><option value="">All districts</option>{dists.map(s => <option key={s}>{s}</option>)}</Select></Field>
        <Field label="Season"><Select value={season} onChange={e => setSeason(e.target.value)}><option>All</option>{opts.seasons.map((s: string) => <option key={s}>{s}</option>)}</Select></Field>
      </div>
      {!r ? <Spinner /> : r.top_crops.length === 0 ? <Notice>No records for this selection.</Notice> : (
        <div className="grid gap-6 lg:grid-cols-[1fr_1.3fr]">
          <Panel title={`Main crops, ${r.period}`}>
            <table className="w-full text-sm"><thead><tr className="muted border-b line text-left text-xs"><th className="py-1.5">Crop</th><th className="text-right">Avg area (ha/yr)</th><th className="text-right">Yield (t/ha)</th></tr></thead>
              <tbody>{r.top_crops.map((c: any) => <tr key={c.crop} className="border-b line last:border-0"><td className="py-1.5">{c.crop}</td><td className="text-right tabular-nums">{Math.round(c.avg_area_ha).toLocaleString()}</td><td className="text-right tabular-nums">{c.yield ?? '—'}</td></tr>)}</tbody></table>
          </Panel>
          <Panel title="Area under the top five crops">
            <div className="h-72"><ResponsiveContainer><LineChart data={r.trend}>
              <CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="year" tick={{ fontSize: 11, fill: 'var(--muted)' }} />
              <YAxis tick={{ fontSize: 11, fill: 'var(--muted)' }} tickFormatter={v => `${Math.round(v / 1000)}k`} /><Tooltip {...tip} formatter={(v: any) => `${Math.round(v).toLocaleString()} ha`} /><Legend wrapperStyle={{ fontSize: 12 }} />
              {r.trend_crops.map((c: string, i: number) => <Line key={c} dataKey={c} stroke={chartColors[i]} strokeWidth={2} dot={false} />)}
            </LineChart></ResponsiveContainer></div>
            <p className="muted mt-2 text-xs">{r.source}</p>
          </Panel>
        </div>
      )}
    </div>
  )
}

function Advisor() {
  const { lang, toast } = useApp()
  const [q, setQ] = useState('I have 2 acres of red sandy loam near Tumakuru with a borewell. What should I grow this season and how should I manage water?')
  const [ctx, setCtx] = useState({ location: 'Tumakuru, Karnataka', land: '2 acres', soil: 'red sandy loam, pH 6.3', water: 'borewell' })
  const [r, setR] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const go = async (e: FormEvent) => { e.preventDefault(); setBusy(true); try { setR(await api('/farming/advisor', { body: { question: q, context: ctx, language: lang } })) } catch (x: any) { toast(x.message, 'error') } finally { setBusy(false) } }
  return (
    <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
      <Panel title="Your farm">
        <form onSubmit={go} className="space-y-3">
          {Object.entries(ctx).map(([k, v]) => <Field key={k} label={k[0].toUpperCase() + k.slice(1)}><Input value={v} onChange={e => setCtx({ ...ctx, [k]: e.target.value })} /></Field>)}
          <Field label="Question"><textarea value={q} onChange={e => setQ(e.target.value)} rows={4} className="w-full rounded-lg border line bg-[var(--surface)] px-3 py-2 text-sm" /></Field>
          <Button className="w-full" loading={busy}>Get a plan</Button>
        </form>
      </Panel>
      {!r ? <Panel tone="soft"><p className="muted text-sm">The advisor combines your farm details with the current season and passages retrieved from the knowledge base.</p></Panel> : (
        <Panel title="Farm plan">
          <div className="prose-agri"><ReactMarkdown remarkPlugins={[remarkGfm]}>{r.answer}</ReactMarkdown></div>
          <Citations items={r.citations} />
          <p className="muted mt-2 text-xs">{r.model} · {(r.latency_ms / 1000).toFixed(1)} s{r.grounding?.groundedness != null ? ` · grounded ${pct(r.grounding.groundedness, 0)}` : ''}</p>
        </Panel>
      )}
    </div>
  )
}
