import { useState, type FormEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import { Badge, Button, Field, Input, Notice, PageHead, Panel } from '../components/ui'
import { api } from '../lib/api'
import { useApp } from '../lib/app-context'

const toneOf = (r: string) => (r === 'Low' ? 'bad' : r === 'High' ? 'info' : 'good') as any

export default function Soil() {
  const { t, lang, toast } = useApp()
  const [f, setF] = useState({ N: '240', P: '18', K: '150', ph: '6.4', oc: '0.45', ec: '0.4', rainfall: '800', irrigated: false })
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const num = (v: string) => (v === '' ? null : Number(v))

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true)
    try {
      setRes(await api('/soil/analyse', { body: { N: +f.N, P: +f.P, K: +f.K, ph: +f.ph, oc: num(f.oc), ec: num(f.ec), rainfall: num(f.rainfall), irrigated: f.irrigated, language: lang } }))
    } catch (x: any) { toast(x.message, 'error') } finally { setBusy(false) }
  }
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value })

  return (
    <div className="mx-auto max-w-6xl">
      <PageHead title={t('soil')} intro="Enter the values from your Soil Health Card or laboratory report. Ratings follow the standard Indian soil-test classes." />
      <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
        <Panel title="Soil test report">
          <form onSubmit={submit} className="grid grid-cols-2 gap-3">
            <Field label="Available N (kg/ha)"><Input type="number" step="any" min={0} required value={f.N} onChange={set('N')} /></Field>
            <Field label="Available P (kg/ha)"><Input type="number" step="any" min={0} required value={f.P} onChange={set('P')} /></Field>
            <Field label="Available K (kg/ha)"><Input type="number" step="any" min={0} required value={f.K} onChange={set('K')} /></Field>
            <Field label="pH"><Input type="number" step="0.1" min={3} max={11} required value={f.ph} onChange={set('ph')} /></Field>
            <Field label="Organic carbon (%)"><Input type="number" step="0.01" min={0} value={f.oc} onChange={set('oc')} /></Field>
            <Field label="EC (dS/m)"><Input type="number" step="0.01" min={0} value={f.ec} onChange={set('ec')} /></Field>
            <Field label="Annual rainfall (mm)"><Input type="number" min={0} value={f.rainfall} onChange={set('rainfall')} /></Field>
            <label className="mt-6 flex items-center gap-2 text-sm"><input type="checkbox" className="accent-leaf-600" checked={f.irrigated} onChange={e => setF({ ...f, irrigated: e.target.checked })} />Irrigation available</label>
            <Button className="col-span-2 mt-1" loading={busy}>{t('analyse')}</Button>
          </form>
        </Panel>

        {!res ? <Panel tone="soft"><p className="muted text-sm">Your soil ratings, a plain-language summary, crops that match the soil, and fertiliser adjustments will appear here.</p></Panel> : (
          <div className="space-y-6">
            <Panel title="Summary">
              <div className="prose-agri"><ReactMarkdown>{res.summary}</ReactMarkdown></div>
              <p className="muted mt-2 text-xs">{res.summary_source === 'rule-based' ? `Rule-based summary${res.summary_note ? ` (language model unavailable: ${res.summary_note})` : ''}` : `Written by ${res.summary_source} from the computed ratings`}</p>
            </Panel>
            <div className="grid gap-6 md:grid-cols-2">
              <Panel title="Fertility ratings">
                <table className="w-full text-sm"><tbody>
                  {Object.entries(res.ratings).map(([k, r]: any) => (
                    <tr key={k} className="border-b line last:border-0"><td className="py-2 font-semibold">{({ N: 'Nitrogen', P: 'Phosphorus', K: 'Potassium', OC: 'Organic carbon' } as any)[k]}</td>
                      <td className="tabular-nums whitespace-nowrap">{r.value} {r.unit}</td><td className="text-right"><Badge tone={toneOf(r.rating)}>{r.rating}</Badge></td></tr>))}
                  <tr className="border-b line"><td className="py-2 font-semibold">pH</td><td>{res.ph.value}</td><td className="text-right"><Badge tone="info">{res.ph.class}</Badge></td></tr>
                  {res.ec && <tr><td className="py-2 font-semibold">EC</td><td>{res.ec.value} dS/m</td><td className="text-right"><Badge tone={res.ec.class === 'Normal' ? 'good' : 'warn'}>{res.ec.class}</Badge></td></tr>}
                </tbody></table>
                <p className="muted mt-3 text-xs">Fertiliser dose adjustment vs. general recommendation: N {res.fertiliser_adjustment.N}, P {res.fertiliser_adjustment.P}, K {res.fertiliser_adjustment.K}.</p>
              </Panel>
              <Panel title="What to do">
                <ul className="list-disc space-y-1.5 pl-5 text-sm">{res.tips.map((x: string) => <li key={x}>{x}</li>)}</ul>
              </Panel>
            </div>
            <Panel title="Crop suitability for this soil">
              <div className="space-y-2">
                {res.suitability.slice(0, 10).map((s: any) => (
                  <div key={s.crop} className="grid grid-cols-[150px_1fr_44px] items-center gap-3 text-sm">
                    <span className="font-medium">{s.crop}</span>
                    <div title={s.reasons.join('; ')} className="h-2.5 rounded-full bg-[var(--surface-2)]"><div className={`h-2.5 rounded-full ${s.score >= 80 ? 'bg-leaf-600' : s.score >= 50 ? 'bg-turmeric' : 'bg-soil-500'}`} style={{ width: `${s.score}%` }} /></div>
                    <span className="text-right tabular-nums">{s.score}</span>
                  </div>))}
              </div>
              <p className="muted mt-3 text-xs">{res.method} Hover a bar to see the reasons. For a model-based recommendation using climate too, use Smart Farming → Crop recommendation.</p>
            </Panel>
            <Notice>Soil tests describe the sampled field only. Re-test every 2–3 years and follow crop-specific doses from your Soil Health Card or University of Agricultural Sciences package of practices.</Notice>
          </div>
        )}
      </div>
    </div>
  )
}
