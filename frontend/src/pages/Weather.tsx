import { Download, MapPin, RefreshCw, Upload } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Area, Bar, CartesianGrid, ComposedChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Badge, Button, chartColors, Empty, Field, Input, Metric, Notice, PageHead, Panel, Select, Spinner, Tabs } from '../components/ui'
import { api } from '../lib/api'
import { useApp } from '../lib/app-context'

const tip = { contentStyle: { background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 8, fontSize: 12 } }

export default function Weather() {
  const { t } = useApp()
  const [tab, setTab] = useState<'wx' | 'mk'>('wx')
  return (
    <div className="mx-auto max-w-6xl">
      <PageHead title={t('weather')} />
      <Tabs value={tab} onChange={setTab} items={[{ id: 'wx', label: t('forecast') }, { id: 'mk', label: t('prices') }]} />
      {tab === 'wx' ? <WeatherTab /> : <Market />}
    </div>
  )
}

function WeatherTab() {
  const { t, toast } = useApp()
  const [q, setQ] = useState(localStorage.getItem('agrimind.place') || 'Mysuru')
  const [places, setPlaces] = useState<any[]>([])
  const [place, setPlace] = useState<any>(() => JSON.parse(localStorage.getItem('agrimind.placeObj') || 'null'))
  const [w, setW] = useState<any>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const find = async (e?: FormEvent) => {
    e?.preventDefault(); setErr('')
    try { const r = await api(`/weather/geocode?q=${encodeURIComponent(q)}`); setPlaces(r); if (r[0]) choose(r[0]); else setErr('No place found with that name.') }
    catch (x: any) { setErr(x.message) }
  }
  const choose = (p: any) => { setPlace(p); localStorage.setItem('agrimind.place', p.name); localStorage.setItem('agrimind.placeObj', JSON.stringify(p)) }
  useEffect(() => {
    if (!place) { find(); return }
    setBusy(true); setErr('')
    api(`/weather?lat=${place.lat}&lon=${place.lon}`).then(setW).catch(x => { setErr(x.message); toast(x.message, 'error') }).finally(() => setBusy(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [place])

  return (
    <div className="space-y-6">
      <form onSubmit={find} className="flex flex-wrap items-end gap-2">
        <div className="w-64"><Field label="Village, town or district"><Input value={q} onChange={e => setQ(e.target.value)} /></Field></div>
        <Button><MapPin className="size-4" />Find</Button>
        {places.length > 1 && <Select className="w-auto" value={places.indexOf(places.find(p => p.lat === place?.lat)!)} onChange={e => choose(places[+e.target.value])}>
          {places.map((p, i) => <option key={i} value={i}>{p.name}, {p.admin1}, {p.country}</option>)}</Select>}
      </form>
      {err && <Notice tone="bad">{err}</Notice>}
      {busy && <Spinner label="Fetching forecast…" />}
      {w && !busy && (
        <>
          <div className="grid gap-6 lg:grid-cols-[1fr_1.6fr]">
            <Panel title={`${place.name}, ${place.admin1 ?? ''}`}>
              <div className="grid grid-cols-2 gap-5">
                <Metric label="Temperature" value={`${w.current.temperature_2m} °C`} />
                <Metric label="Humidity" value={`${w.current.relative_humidity_2m}%`} />
                <Metric label="Wind" value={`${w.current.wind_speed_10m} km/h`} />
                <Metric label="Rain now" value={`${w.current.precipitation} mm`} />
              </div>
              <p className="muted mt-4 text-xs">{w.source} · {w.timezone}</p>
            </Panel>
            <Panel title={t('forecast')}>
              <div className="h-60"><ResponsiveContainer><ComposedChart data={[...w.past, ...w.forecast]}>
                <CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--muted)' }} tickFormatter={d => d.slice(5)} />
                <YAxis yAxisId="t" unit="°" tick={{ fontSize: 11, fill: 'var(--muted)' }} /><YAxis yAxisId="r" orientation="right" unit="mm" tick={{ fontSize: 11, fill: 'var(--muted)' }} />
                <Tooltip {...tip} /><Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar yAxisId="r" dataKey="rain" name="Rain (mm)" fill={chartColors[2]} radius={[3, 3, 0, 0]} />
                <Area yAxisId="t" dataKey="tmax" name="Max °C" stroke={chartColors[1]} fill={chartColors[1]} fillOpacity={0.12} />
                <Line yAxisId="t" dataKey="tmin" name="Min °C" stroke={chartColors[0]} dot={false} strokeWidth={2} />
              </ComposedChart></ResponsiveContainer></div>
              <p className="muted text-xs">Past 7 days and next 7 days.</p>
            </Panel>
          </div>
          <Panel title={t('advisories')}>
            {w.advisories.length === 0 ? <p className="muted text-sm">No special advisories for the next five days.</p> : (
              <ul className="space-y-2 text-sm">{w.advisories.map((a: any, i: number) => (
                <li key={i} className="flex gap-3"><span className="muted w-24 shrink-0 tabular-nums">{a.date}</span><Badge tone={a.level === 'warning' ? 'warn' : 'good'}>{a.type}</Badge><span>{a.text}</span></li>))}</ul>
            )}
            <p className="muted mt-3 text-xs">Rule-based advisories from forecast humidity, temperature, rain and wind.</p>
          </Panel>
        </>
      )}
    </div>
  )
}

function Market() {
  const { toast, user } = useApp()
  const [ov, setOv] = useState<any>(null)
  const [com, setCom] = useState('')
  const [tr, setTr] = useState<any>(null)
  const [f, setF] = useState({ state: 'Karnataka', commodity: 'Tomato' })
  const [busy, setBusy] = useState(false)
  const file = useRef<HTMLInputElement>(null)
  const load = () => api('/market/overview').then(o => { setOv(o); if (!com && o.commodities[0]) setCom(o.commodities[0].commodity) })
  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (com) api(`/market/trend?commodity=${encodeURIComponent(com)}`).then(setTr) }, [com, ov])

  const fetchLive = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true)
    try { const r = await api('/market/fetch', { body: f }); toast(`Fetched ${r.fetched} price records`); load() } catch (x: any) { toast(x.message, 'error') } finally { setBusy(false) }
  }
  const importCsv = async (fl: FileList | null) => {
    if (!fl?.[0]) return
    const fd = new FormData(); fd.append('file', fl[0])
    try { const r = await api('/market/import', { form: fd }); toast(`Imported ${r.stored} of ${r.rows} rows`); load() } catch (x: any) { toast(x.message, 'error') }
    if (file.current) file.current.value = ''
  }

  return (
    <div className="space-y-6">
      <Panel title="Get price data">
        <div className="grid gap-6 md:grid-cols-2">
          <form onSubmit={fetchLive} className="space-y-3">
            <p className="text-sm">Live daily mandi prices from Agmarknet via the data.gov.in API{user?.role === 'admin' ? ' (add your free API key in Admin → Model configuration)' : ''}. Each fetch is stored so price history builds up.</p>
            <div className="grid grid-cols-2 gap-3">
              <Field label="State"><Input value={f.state} onChange={e => setF({ ...f, state: e.target.value })} /></Field>
              <Field label="Commodity"><Input value={f.commodity} onChange={e => setF({ ...f, commodity: e.target.value })} /></Field>
            </div>
            <Button loading={busy}><RefreshCw className="size-4" />Fetch today's prices</Button>
          </form>
          <div className="space-y-3">
            <p className="text-sm">Historical prices: download a report from <a className="font-semibold text-leaf-600 underline" href="https://agmarknet.gov.in" target="_blank" rel="noreferrer">agmarknet.gov.in</a> (Price & Arrival → CSV) and import it here.</p>
            <input ref={file} type="file" accept=".csv" className="hidden" onChange={e => importCsv(e.target.files)} />
            <Button variant="ghost" onClick={() => file.current?.click()}><Upload className="size-4" />Import Agmarknet CSV</Button>
          </div>
        </div>
      </Panel>
      {!ov ? <Spinner /> : ov.total === 0 ? <Empty title="No price data yet">Fetch live prices or import an Agmarknet CSV. AgriMind does not show prices it cannot source.</Empty> : (
        <>
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-64"><Field label="Commodity"><Select value={com} onChange={e => setCom(e.target.value)}>{ov.commodities.map((c: any) => <option key={c.commodity} value={c.commodity}>{c.commodity} ({c.n})</option>)}</Select></Field></div>
            <p className="muted text-sm">{ov.total.toLocaleString()} price records stored.</p>
          </div>
          {tr?.stats && (
            <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
              <Panel title={`${com}: modal price trend`}>
                <div className="grid grid-cols-4 gap-3"><Metric label="Latest" value={`₹${tr.stats.latest}`} /><Metric label="Average" value={`₹${tr.stats.mean}`} /><Metric label="Range" value={<span className="text-lg">₹{tr.stats.min}–{tr.stats.max}</span>} /><Metric label="Change" value={tr.stats.change_pct == null ? '—' : `${tr.stats.change_pct}%`} /></div>
                <div className="mt-4 h-64"><ResponsiveContainer><LineChart data={tr.series}>
                  <CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="d" tick={{ fontSize: 10, fill: 'var(--muted)' }} /><YAxis tick={{ fontSize: 11, fill: 'var(--muted)' }} />
                  <Tooltip {...tip} formatter={(v: any) => `₹${Math.round(v)}`} /><Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line dataKey="modal" name="Modal (avg of markets)" stroke={chartColors[0]} strokeWidth={2} dot={tr.series.length < 30} />
                  <Line dataKey="min" name="Min" stroke={chartColors[2]} strokeDasharray="4 3" dot={false} /><Line dataKey="max" name="Max" stroke={chartColors[1]} strokeDasharray="4 3" dot={false} />
                </LineChart></ResponsiveContainer></div>
                <p className="muted text-xs">{tr.unit}</p>
              </Panel>
              <Panel title="Markets">
                <table className="w-full text-sm"><tbody>{tr.markets.slice(0, 12).map((m: any) => (
                  <tr key={m.market + m.state} className="border-b line last:border-0"><td className="py-1.5">{m.market}<span className="muted text-xs"> · {m.state}</span></td><td className="text-right tabular-nums">₹{Math.round(m.avg_modal)}</td></tr>))}</tbody></table>
              </Panel>
            </div>
          )}
          <Panel title="Latest records" action={<Button variant="quiet" onClick={() => {
            const csv = ['date,state,market,commodity,variety,min,max,modal', ...ov.latest.map((r: any) => [r.arrival_date, r.state, r.market, r.commodity, r.variety, r.min_price, r.max_price, r.modal_price].join(','))].join('\n')
            const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' })); a.download = 'mandi_prices.csv'; a.click()
          }}><Download className="size-4" />CSV</Button>}>
            <div className="max-h-80 overflow-auto"><table className="w-full text-sm"><thead className="muted text-left text-xs"><tr><th>Date</th><th>Market</th><th>Commodity</th><th className="text-right">Min</th><th className="text-right">Max</th><th className="text-right">Modal</th></tr></thead>
              <tbody>{ov.latest.map((r: any) => <tr key={r.id} className="border-t line"><td className="py-1">{r.arrival_date}</td><td>{r.market}</td><td>{r.commodity} <span className="muted text-xs">{r.variety}</span></td><td className="text-right">{r.min_price}</td><td className="text-right">{r.max_price}</td><td className="text-right font-semibold">{r.modal_price}</td></tr>)}</tbody></table></div>
          </Panel>
        </>
      )}
    </div>
  )
}
