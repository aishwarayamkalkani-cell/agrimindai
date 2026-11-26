import { useEffect, useState, type FormEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Badge, Button, Field, Notice, PageHead, Panel, Select } from '../components/ui'
import { api, pct } from '../lib/api'
import { useApp } from '../lib/app-context'
import { Citations } from './Assistant'

const MODES = [
  { id: 'baseline', name: 'Baseline Grok', desc: 'The question alone with a generic system prompt.' },
  { id: 'engineered', name: 'Prompt-engineered Grok', desc: 'Agronomist role, Indian context, structure and safety rules.' },
  { id: 'rag', name: 'RAG-grounded Grok', desc: 'Same prompt plus retrieved knowledge-base passages and citation rules.' },
]

export default function Lab() {
  const { t, lang, toast } = useApp()
  const [bench, setBench] = useState<any[]>([])
  const [q, setQ] = useState('What premium does a farmer pay under PMFBY for a kharif crop?')
  const [ref, setRef] = useState('A maximum of 2% of the sum insured for Kharif food and oilseed crops (1.5% Rabi, 5% commercial/horticultural).')
  const [r, setR] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [showClaims, setShowClaims] = useState<string | null>(null)
  const [judge, setJudge] = useState(true)
  useEffect(() => { api('/lab/benchmark').then(setBench) }, [])

  const go = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setR(null)
    try { setR(await api('/lab/compare', { body: { question: q, language: lang, reference: ref || null, judge } })) } catch (x: any) { toast(x.message, 'error') } finally { setBusy(false) }
  }
  const pickBench = (id: string) => { const b = bench.find(x => x.id === id); if (b) { setQ(b.question); setRef(b.reference) } }

  return (
    <div className="mx-auto max-w-7xl">
      <PageHead title={t('lab')} intro="Send one question to the same Grok model in three configurations and compare relevance, faithfulness, citation correctness, groundedness, latency and token usage." />
      <Panel className="mb-6">
        <form onSubmit={go} className="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end">
          <Field label="Question"><textarea value={q} onChange={e => setQ(e.target.value)} rows={2} required className="w-full rounded-lg border line bg-[var(--surface)] px-3 py-2 text-sm" /></Field>
          <Field label="Reference answer (optional, for semantic similarity)"><textarea value={ref} onChange={e => setRef(e.target.value)} rows={2} className="w-full rounded-lg border line bg-[var(--surface)] px-3 py-2 text-sm" /></Field>
          <Button loading={busy}>{t('compare')}</Button>
        </form>
        <label className="muted mt-3 flex items-center gap-2 text-sm"><input type="checkbox" className="accent-leaf-600" checked={judge} onChange={e => setJudge(e.target.checked)} />Measure faithfulness with Grok as judge (one extra request per answer)</label>
        <div className="mt-3 max-w-md"><Select onChange={e => pickBench(e.target.value)} defaultValue="" aria-label="Load benchmark question"><option value="" disabled>Load a benchmark question…</option>{bench.map(b => <option key={b.id} value={b.id}>{b.id}: {b.question}</option>)}</Select></div>
      </Panel>
      {busy && <Notice>Running three generations — this takes as long as three normal answers.</Notice>}
      {r && (
        <>
          <div className="grid gap-4 lg:grid-cols-3">
            {MODES.map(m => {
              const x = r.results[m.id]
              return (
                <Panel key={m.id} title={m.name} className="flex flex-col">
                  <p className="muted -mt-2 mb-3 text-xs">{m.desc}</p>
                  {x.error ? <Notice tone="bad">{x.error}</Notice> : (
                    <>
                      <div className="mb-3 grid grid-cols-2 gap-2 text-xs">
                        {[['Answer relevance', x.answer_relevance?.toFixed(3) ?? '—'], ['Faithfulness (judge)', x.faithfulness == null ? (x.judge_error ? 'error' : '—') : pct(x.faithfulness, 0)],
                          ['Citation correctness', x.citation_correctness == null ? 'no citations' : pct(x.citation_correctness, 0)], ['Groundedness', pct(x.groundedness, 0)],
                          ['Unsupported claims', pct(x.unsupported_rate, 0)], ['Similarity to reference', x.semantic_similarity == null ? '—' : x.semantic_similarity.toFixed(3)],
                          ['Latency', `${(x.latency_ms / 1000).toFixed(1)} s`], ['Tokens', x.usage ? `${x.usage.total_tokens}` : 'n/a']].map(([l, v]) => (
                          <div key={l} className="surface-2 rounded-lg p-2"><div className="muted">{l}</div><div className="font-display text-lg font-bold">{v}</div></div>))}
                      </div>
                      {x.usage && <p className="muted mb-2 text-xs">{x.usage.prompt_tokens} prompt · {x.usage.completion_tokens} completion{x.usage.reasoning_tokens ? ` · ${x.usage.reasoning_tokens} reasoning` : ''}{x.judge_usage ? ` · judge ${x.judge_usage.total_tokens}` : ''}{x.retries ? ` · ${x.retries} retries` : ''}</p>}
                      {x.judge_error && <p className="mb-2 text-xs text-red-700 dark:text-red-400">Judge: {x.judge_error}</p>}
                      <div className="flex flex-wrap gap-1.5 text-xs"><Badge>{x.words} words</Badge><Badge>{x.n_claims} claims</Badge>{x.has_citations && <Badge tone="good">cites sources</Badge>}</div>
                      <div className="prose-agri mt-3 max-h-[420px] overflow-y-auto text-sm"><ReactMarkdown remarkPlugins={[remarkGfm]}>{x.answer}</ReactMarkdown></div>
                      <button className="mt-3 text-left text-xs font-semibold text-leaf-600" onClick={() => setShowClaims(showClaims === m.id ? null : m.id)}>{showClaims === m.id ? 'Hide' : 'Show'} claim-level support</button>
                      {showClaims === m.id && <ul className="mt-2 space-y-1 text-xs">{x.claims.map((c: any, i: number) => <li key={i} className={c.supported ? '' : 'text-red-700 dark:text-red-400'}>{c.supported ? '✓' : '✗'} {c.support.toFixed(2)}{c.judge ? ` · judge: ${c.judge}` : ''} — {c.text}</li>)}</ul>}
                    </>
                  )}
                </Panel>
              )
            })}
          </div>
          <Panel title="Retrieved evidence used for scoring" className="mt-6"><Citations items={r.citations} />
            <p className="muted mt-3 text-xs">All three answers come from the same Grok model and are scored against the same retrieved passages (only the RAG configuration sees them). Answer relevance: cosine similarity of question and answer. Faithfulness: share of claims Grok-as-judge marks as supported by the passages. Citation correctness: share of [n] markers whose sentence matches the cited passage. Groundedness: share of claims whose best embedding similarity with a passage sentence reaches the threshold.</p>
          </Panel>
        </>
      )}
    </div>
  )
}
