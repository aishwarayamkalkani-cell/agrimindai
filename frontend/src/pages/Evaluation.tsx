import { Download, Play } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Badge, Button, chartColors, Empty, Field, Metric, Notice, PageHead, Panel, Select, Spinner, Tabs } from '../components/ui'
import { api, download, fmtDate, pct } from '../lib/api'
import { useApp } from '../lib/app-context'

const tip = { contentStyle: { background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 8, fontSize: 12 } }
const MODE_NAMES: Record<string, string> = { baseline: 'Baseline Grok', engineered: 'Prompt-engineered Grok', rag: 'RAG-grounded Grok' }

export default function Evaluation() {
  const { t, toast } = useApp()
  const [tab, setTab] = useState<'rag' | 'gen' | 'cls'>('rag')
  const [runs, setRuns] = useState<any[] | null>(null)
  const [cls, setCls] = useState<any>(null)
  const [job, setJob] = useState<any>(null)
  const [sel, setSel] = useState<any>(null)
  const [n, setN] = useState(8)
  const [judge, setJudge] = useState(true)

  const loadRuns = () => api('/eval/runs').then(setRuns)
  useEffect(() => { loadRuns(); api('/eval/classification').then(setCls) }, [])
  useEffect(() => {
    if (!runs) return
    const kind = tab === 'rag' ? 'retrieval' : 'generation'
    const r = runs.find(x => x.kind === kind)
    if (r) api(`/eval/runs/${r.id}`).then(setSel); else setSel(null)
  }, [runs, tab])
  useEffect(() => {
    if (!job || job.status !== 'running') return
    const h = setInterval(async () => {
      const j = await api(`/eval/jobs/${job.id}`); setJob(j)
      if (j.status === 'done') { toast('Evaluation finished'); loadRuns() }
      if (j.status === 'error') toast(j.error, 'error')
    }, 1500)
    return () => clearInterval(h)
  }, [job, toast])

  const start = async (kind: string) => { try { setJob(await api('/eval/run', { body: { kind, n, judge } })) } catch (e: any) { toast(e.message, 'error') } }
  const running = job?.status === 'running'

  return (
    <div className="mx-auto max-w-6xl">
      <PageHead title={t('evaluation')} intro="All numbers on this page are computed by running the system: retrieval on the benchmark question set, generation with the configured LLM, and the trained models on held-out test data." />
      <Tabs value={tab} onChange={setTab} items={[{ id: 'rag', label: 'Retrieval (RAG)' }, { id: 'gen', label: 'LLM comparison' }, { id: 'cls', label: 'Classification models' }]} />

      {tab === 'rag' && (
        <div className="space-y-6">
          <div className="flex items-center gap-3"><Button onClick={() => start('retrieval')} loading={running && job.kind === 'retrieval'}><Play className="size-4" />Run retrieval evaluation</Button>
            <span className="muted text-sm">36 benchmark questions (incl. Kannada and Hindi), K = 1, 3, 5.</span></div>
          {!sel ? <Empty title="No retrieval run yet">Run the evaluation to measure Recall@K, Precision@K and MRR.</Empty> : <RetrievalRun r={sel} />}
        </div>
      )}
      {tab === 'gen' && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-40"><Field label="Questions"><Select value={n} onChange={e => setN(+e.target.value)}>{[4, 8, 12, 20, 36].map(x => <option key={x}>{x}</option>)}</Select></Field></div>
            <Button onClick={() => start('generation')} loading={running && job.kind === 'generation'}><Play className="size-4" />Run LLM comparison</Button>
            <label className="muted flex items-center gap-2 pb-2 text-sm"><input type="checkbox" className="accent-leaf-600" checked={judge} onChange={e => setJudge(e.target.checked)} />Grok-as-judge faithfulness</label>
            {running && job.kind === 'generation' && <span className="muted pb-2 text-sm">{job.progress}/{job.total || n} questions…</span>}
          </div>
          <Notice>Each question is answered three times (baseline, prompt-engineered, RAG-grounded) by the configured Grok model{judge ? ', and each answer is checked once by Grok as judge' : ''}, so {n} questions make {n * (judge ? 6 : 3)} API calls. Only results actually measured in a run are shown.</Notice>
          {!sel ? <Empty title="No comparison run yet">Add your xAI API key in Admin → Model configuration, then run the comparison.</Empty> : <GenRun r={sel} />}
        </div>
      )}
      {tab === 'cls' && (!cls ? <Spinner /> : <Classification cls={cls} />)}

      <Panel title="Evaluation history" className="mt-8">
        {!runs ? <Spinner /> : runs.length === 0 ? <p className="muted text-sm">No runs yet.</p> : (
          <table className="w-full text-sm"><thead className="muted text-left text-xs"><tr><th className="py-1">Run</th><th>Type</th><th>When</th><th>Headline</th><th /></tr></thead>
            <tbody>{runs.map(r => (
              <tr key={r.id} className="border-t line">
                <td className="py-2"><button className="font-semibold text-leaf-600" onClick={() => { setTab(r.kind === 'retrieval' ? 'rag' : 'gen'); api(`/eval/runs/${r.id}`).then(setSel) }}>#{r.id}</button></td>
                <td><Badge tone="info">{r.kind}</Badge></td><td className="muted">{fmtDate(r.created_at)}</td>
                <td className="tabular-nums">{r.kind === 'retrieval' ? `MRR ${r.summary.mrr} · Recall@5 ${pct(r.summary['recall@5'])}` : `${r.summary.llm?.model ?? ''}: RAG faithfulness ${pct(r.summary.rag?.faithfulness)}, groundedness ${pct(r.summary.rag?.groundedness)} vs baseline ${pct(r.summary.baseline?.groundedness)}`}</td>
                <td className="text-right whitespace-nowrap">
                  <Button variant="quiet" onClick={() => download(`/eval/runs/${r.id}/download?fmt=csv`, `agrimind_eval_${r.id}.csv`)}><Download className="size-4" />CSV</Button>
                  <Button variant="quiet" onClick={() => download(`/eval/runs/${r.id}/download?fmt=json`, `agrimind_eval_${r.id}.json`)}>JSON</Button>
                </td></tr>))}</tbody></table>
        )}
      </Panel>
    </div>
  )
}

function RetrievalRun({ r }: { r: any }) {
  const s = r.summary
  const data = [1, 3, 5].map(k => ({ k: `K=${k}`, Recall: +(s[`recall@${k}`] * 100).toFixed(1), Precision: +(s[`precision@${k}`] * 100).toFixed(1), Hit: +(s[`hit@${k}`] * 100).toFixed(1) }))
  return (
    <>
      <Panel title={`Run #${r.id} · ${fmtDate(r.created_at)}`}>
        <div className="grid grid-cols-2 gap-5 sm:grid-cols-5">
          <Metric label="MRR" value={s.mrr.toFixed(3)} /><Metric label="Recall@1" value={pct(s['recall@1'])} /><Metric label="Recall@5" value={pct(s['recall@5'])} />
          <Metric label="Precision@3" value={pct(s['precision@3'])} /><Metric label="Search time" value={`${(s.seconds / s.n_questions * 1000).toFixed(1)} ms`} sub="per query" />
        </div>
        <div className="mt-5 h-64"><ResponsiveContainer><BarChart data={data}>
          <CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="k" tick={{ fontSize: 12, fill: 'var(--muted)' }} /><YAxis unit="%" domain={[0, 100]} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
          <Tooltip {...tip} /><Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="Recall" fill={chartColors[0]} radius={[3, 3, 0, 0]} /><Bar dataKey="Precision" fill={chartColors[1]} radius={[3, 3, 0, 0]} /><Bar dataKey="Hit" fill={chartColors[2]} radius={[3, 3, 0, 0]} />
        </BarChart></ResponsiveContainer></div>
        <p className="muted mt-2 text-xs">Embedder: {s.embedder.kind} ({s.embedder.model}) · {s.n_chunks} passages · {s.n_questions} questions. Relevance is judged at document level: a retrieved passage is relevant if it comes from a document listed as containing the answer. Precision@K is low by construction when only one document is relevant.</p>
        {s.embedder.note && <div className="mt-3"><Notice tone="warn">{s.embedder.note}</Notice></div>}
      </Panel>
      <Panel title="Per question">
        <div className="max-h-96 overflow-auto"><table className="w-full text-sm"><thead className="muted text-left text-xs"><tr><th>Question</th><th>Top retrieved document</th><th className="text-right">RR</th><th className="text-right">R@3</th></tr></thead>
          <tbody>{r.details.map((d: any) => (
            <tr key={d.id} className="border-t line"><td className="py-1.5 pr-3">{d.question}</td><td className={`text-xs ${d.relevant.includes(d.retrieved[0]) ? '' : 'text-red-700 dark:text-red-400'}`}>{d.retrieved[0]}</td>
              <td className="text-right tabular-nums">{d.rr.toFixed(2)}</td><td className="text-right tabular-nums">{d['recall@3']}</td></tr>))}</tbody></table></div>
      </Panel>
    </>
  )
}

function GenRun({ r }: { r: any }) {
  const s = r.summary
  const modes = ['baseline', 'engineered', 'rag']
  const val = (m: string, key: string, scale: number) => s[m]?.[key] == null ? null : +(s[m][key] * scale).toFixed(key.includes('tokens') ? 0 : 1)
  const metric = (key: string, scale = 100) => modes.map(m => ({ mode: MODE_NAMES[m], value: val(m, key, scale) }))
  const charts = [
    { key: 'answer_relevance', title: 'Answer relevance (%)' }, { key: 'faithfulness', title: 'Faithfulness — Grok judge (%)' },
    { key: 'citation_correctness', title: 'Citation correctness (%)' }, { key: 'groundedness', title: 'Groundedness (%)' },
    { key: 'latency_ms', title: 'Mean latency (s)', scale: 0.001 }, { key: 'total_tokens', title: 'Mean tokens per answer', scale: 1 },
  ]
  const f = (v: any, kind: 'pct' | 'num' | 's' | 'int') => v == null ? '—' : kind === 'pct' ? pct(v) : kind === 's' ? `${(v / 1000).toFixed(2)} s` : kind === 'int' ? Math.round(v).toLocaleString() : v.toFixed(3)
  return (
    <>
      <Panel title={`Run #${r.id} · ${s.n_questions} questions · ${s.llm.label ?? s.llm.provider} · ${s.llm.model}`}>
        <div className="grid gap-6 md:grid-cols-2">
          {charts.map((c, i) => {
            const data = metric(c.key, c.scale)
            return (
              <div key={c.key}><h3 className="mb-1 text-sm font-semibold">{c.title}</h3>
                {data.every(d => d.value == null) ? <p className="muted py-6 text-sm">Not measured in this run{c.key === 'faithfulness' ? ' (judge disabled)' : c.key === 'citation_correctness' ? ' (no citations produced)' : ''}.</p> : (
                  <div className="h-40"><ResponsiveContainer><BarChart data={data} layout="vertical" margin={{ left: 20 }}>
                    <CartesianGrid stroke="var(--line)" horizontal={false} /><XAxis type="number" tick={{ fontSize: 11, fill: 'var(--muted)' }} /><YAxis type="category" dataKey="mode" width={150} tick={{ fontSize: 11.5, fill: 'var(--muted)' }} />
                    <Tooltip {...tip} /><Bar dataKey="value" fill={chartColors[i % chartColors.length]} radius={[0, 3, 3, 0]} barSize={16} />
                  </BarChart></ResponsiveContainer></div>)}
              </div>)
          })}
        </div>
        <div className="mt-5 overflow-x-auto"><table className="w-full text-sm"><thead className="muted text-left text-xs"><tr><th>Configuration</th><th className="text-right">Relevance</th><th className="text-right">Faithfulness</th><th className="text-right">Contradicted</th><th className="text-right">Citation validity</th><th className="text-right">Citation correct</th><th className="text-right">Grounded</th><th className="text-right">Unsupported</th><th className="text-right">Similarity</th><th className="text-right">Latency</th><th className="text-right">Tokens (in/out/reasoning)</th><th className="text-right">Errors</th></tr></thead>
          <tbody>{modes.map(m => { const x = s[m] ?? {}; return (
            <tr key={m} className="border-t line"><td className="py-1.5 font-semibold whitespace-nowrap">{MODE_NAMES[m]}</td><td className="text-right">{f(x.answer_relevance, 'num')}</td><td className="text-right">{f(x.faithfulness, 'pct')}</td><td className="text-right">{f(x.contradicted_rate, 'pct')}</td>
              <td className="text-right">{f(x.citation_validity, 'pct')}</td><td className="text-right">{f(x.citation_correctness, 'pct')}</td><td className="text-right">{f(x.groundedness, 'pct')}</td><td className="text-right">{f(x.unsupported_rate, 'pct')}</td>
              <td className="text-right">{f(x.semantic_similarity, 'num')}</td><td className="text-right">{f(x.latency_ms, 's')}</td>
              <td className="text-right whitespace-nowrap">{x.total_tokens == null ? 'n/a' : `${f(x.prompt_tokens, 'int')} / ${f(x.completion_tokens, 'int')} / ${f(x.reasoning_tokens, 'int')}`}</td><td className="text-right">{x.errors}</td></tr>) })}</tbody></table></div>
        <p className="muted mt-3 text-xs">Means over the questions answered without error. Relevance and similarity are cosine similarities ({s.embedder?.kind ?? 'embeddings'}); groundedness counts claims whose best similarity with a retrieved sentence ≥ {s.grounding_threshold}; faithfulness is the share of claims Grok-as-judge marked “supported” by the retrieved passages {s.judge ? '' : '(not run)'}; citation correctness is the share of [n] markers whose sentence matches passage n. Token counts are those reported by the API; reasoning tokens are counted by xAI separately from completion tokens.</p>
      </Panel>
      <Panel title="Answers">
        <div className="max-h-[500px] space-y-4 overflow-auto">{r.details.map((d: any) => (
          <details key={d.id} className="rounded-lg border line p-3"><summary className="cursor-pointer text-sm font-semibold">{d.id}: {d.question}</summary>
            <p className="muted mt-2 text-xs">Reference: {d.reference}</p>
            <div className="mt-2 grid gap-3 md:grid-cols-3">{modes.map(m => <div key={m} className="text-xs"><div className="mb-1 flex flex-wrap gap-1 font-semibold">{MODE_NAMES[m]} {d[m]?.groundedness != null && <Badge>grounded {pct(d[m].groundedness, 0)}</Badge>}{d[m]?.faithfulness != null && <Badge tone="info">faithful {pct(d[m].faithfulness, 0)}</Badge>}</div><p className="whitespace-pre-wrap">{d[m]?.answer ?? d[m]?.error}</p></div>)}</div>
          </details>))}</div>
      </Panel>
    </>
  )
}

function Classification({ cls }: { cls: any }) {
  return (
    <div className="space-y-6">
      {(['disease', 'crop'] as const).map(k => {
        const m = cls[k]
        if (!m) return <Empty key={k} title={`No ${k} model metrics found`} />
        const per = Object.entries(m.per_class).map(([c, v]: any) => ({ c, p: v.precision, r: v.recall, f: v['f1-score'], n: v.support }))
        return (
          <Panel key={k} title={k === 'disease' ? 'Leaf disease classifier' : 'Crop recommendation model'}>
            <div className="grid grid-cols-2 gap-5 sm:grid-cols-4">
              <Metric label="Test accuracy" value={pct(m.test_accuracy)} /><Metric label="Macro F1" value={pct(m.test_macro_f1)} />
              <Metric label="Test samples" value={m.split.test} /><Metric label="Model" value={<span className="text-sm">{m.model ?? m.selected_model}</span>} />
            </div>
            {m.cv_comparison && (
              <table className="mt-4 w-full text-sm"><thead className="muted text-left text-xs"><tr><th>Candidate (5-fold CV on training split)</th><th className="text-right">Macro F1</th></tr></thead>
                <tbody>{Object.entries(m.cv_comparison).map(([n, v]: any) => <tr key={n} className="border-t line"><td className="py-1">{n} {n === m.selected_model && <Badge tone="good">selected</Badge>}</td><td className="text-right tabular-nums">{v.cv_macro_f1_mean.toFixed(4)} ± {v.cv_macro_f1_std.toFixed(4)}</td></tr>)}</tbody></table>)}
            <details className="mt-4"><summary className="cursor-pointer text-sm font-semibold">Per-class precision, recall and F1</summary>
              <table className="mt-2 w-full text-xs"><thead className="muted text-left"><tr><th>Class</th><th className="text-right">Precision</th><th className="text-right">Recall</th><th className="text-right">F1</th><th className="text-right">n</th></tr></thead>
                <tbody>{per.map(x => <tr key={x.c} className="border-t line"><td className="py-1">{x.c.replace('___', ' – ').replace(/_/g, ' ')}</td><td className="text-right">{x.p.toFixed(3)}</td><td className="text-right">{x.r.toFixed(3)}</td><td className="text-right">{x.f.toFixed(3)}</td><td className="text-right">{x.n}</td></tr>)}</tbody></table></details>
            {m.confusion_matrix && <Confusion m={m} />}
            <div className="mt-4"><Notice tone="warn">{m.limitations}</Notice></div>
            <p className="muted mt-2 text-xs">{m.dataset} · trained {m.trained_at}</p>
          </Panel>
        )
      })}
    </div>
  )
}

function Confusion({ m }: { m: any }) {
  const cm: number[][] = m.confusion_matrix
  const max = Math.max(...cm.flat())
  return (
    <details className="mt-3"><summary className="cursor-pointer text-sm font-semibold">Confusion matrix (rows = true class, columns = predicted)</summary>
      <div className="mt-2 overflow-auto"><table className="text-[10px]"><tbody>{cm.map((row, i) => (
        <tr key={i}><td className="pr-2 whitespace-nowrap">{m.classes[i].replace('___', ' – ').replace(/_/g, ' ').slice(0, 34)}</td>
          {row.map((v, j) => <td key={j} title={`${m.classes[i]} → ${m.classes[j]}: ${v}`} className="size-5 text-center" style={{ background: v ? `rgba(47,125,79,${0.12 + 0.88 * v / max})` : 'transparent', color: v / max > 0.5 ? 'white' : undefined }}>{v || ''}</td>)}</tr>))}</tbody></table></div>
    </details>
  )
}
