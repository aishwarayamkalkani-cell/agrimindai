import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Badge, Button, chartColors, Field, Input, Metric, Notice, PageHead, Panel, Select, Spinner, Tabs } from '../components/ui'
import { api, fmtDate, pct } from '../lib/api'
import { useApp } from '../lib/app-context'

const tip = { contentStyle: { background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 8, fontSize: 12 } }
type Tab = 'stats' | 'users' | 'queries' | 'config'

export default function Admin() {
  const { t } = useApp()
  const [tab, setTab] = useState<Tab>('stats')
  return (
    <div className="mx-auto max-w-6xl">
      <PageHead title={t('admin')} intro={<>Manage users, monitor queries and configure models. Documents are managed in the <Link to="/knowledge" className="font-semibold text-leaf-600 underline">Knowledge Base</Link>; evaluation history is on the <Link to="/evaluation" className="font-semibold text-leaf-600 underline">Evaluation</Link> page.</>} />
      <Tabs value={tab} onChange={setTab} items={[{ id: 'stats', label: 'System statistics' }, { id: 'users', label: 'Users' }, { id: 'queries', label: 'Query monitoring' }, { id: 'config', label: 'Model configuration' }]} />
      {tab === 'stats' ? <Stats /> : tab === 'users' ? <Users /> : tab === 'queries' ? <Queries /> : <Config />}
    </div>
  )
}

function Stats() {
  const [s, setS] = useState<any>(null)
  useEffect(() => { api('/admin/stats').then(setS) }, [])
  if (!s) return <Spinner />
  return (
    <div className="space-y-6">
      <Panel><div className="grid grid-cols-2 gap-5 sm:grid-cols-4 lg:grid-cols-7">
        <Metric label="Users" value={s.users} sub={`${s.active_users} active`} /><Metric label="Documents" value={s.documents} sub={`${s.chunks} passages`} />
        <Metric label="Conversations" value={s.conversations} /><Metric label="Queries" value={s.queries} /><Metric label="Eval runs" value={s.eval_runs} />
        <Metric label="Price records" value={s.price_rows} /><Metric label="GPU (CUDA)" value={s.cuda ? 'Yes' : 'No'} sub={s.embedder.device} />
      </div></Panel>
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Queries per day (30 days)">
          {s.per_day.length === 0 ? <p className="muted text-sm">No queries yet.</p> : <div className="h-60"><ResponsiveContainer><BarChart data={s.per_day}>
            <CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="d" tick={{ fontSize: 10, fill: 'var(--muted)' }} /><YAxis allowDecimals={false} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
            <Tooltip {...tip} /><Bar dataKey="n" name="Queries" fill={chartColors[0]} radius={[3, 3, 0, 0]} maxBarSize={36} /></BarChart></ResponsiveContainer></div>}
        </Panel>
        <Panel title="Usage by feature">
          {s.features.length === 0 ? <p className="muted text-sm">No usage yet.</p> : <div className="h-60"><ResponsiveContainer><BarChart data={s.features} layout="vertical" margin={{ left: 20 }}>
            <CartesianGrid stroke="var(--line)" horizontal={false} /><XAxis type="number" allowDecimals={false} tick={{ fontSize: 11, fill: 'var(--muted)' }} /><YAxis type="category" dataKey="feature" width={130} tick={{ fontSize: 11, fill: 'var(--muted)' }} />
            <Tooltip {...tip} /><Bar dataKey="n" name="Requests" fill={chartColors[1]} radius={[0, 3, 3, 0]} /></BarChart></ResponsiveContainer></div>}
        </Panel>
      </div>
      <Panel title="Feature health">
        <table className="w-full text-sm"><thead className="muted text-left text-xs"><tr><th>Feature</th><th className="text-right">Requests</th><th className="text-right">Avg latency</th><th className="text-right">Avg groundedness</th><th className="text-right">Errors</th></tr></thead>
          <tbody>{s.features.map((f: any) => <tr key={f.feature} className="border-t line"><td className="py-1.5">{f.feature}</td><td className="text-right">{f.n}</td><td className="text-right">{f.lat ? `${Math.round(f.lat)} ms` : '—'}</td><td className="text-right">{pct(f.g)}</td><td className="text-right">{f.errors || 0}</td></tr>)}</tbody></table>
        <p className="muted mt-3 text-xs">LLM: {s.llm.provider}:{s.llm.model} ({s.llm.configured ? 'configured' : 'not configured'}) · Embeddings: {s.embedder.kind} {s.embedder.model}</p>
      </Panel>
    </div>
  )
}

function Users() {
  const { user, toast } = useApp()
  const [us, setUs] = useState<any[] | null>(null)
  const load = () => api('/admin/users').then(setUs)
  useEffect(() => { load() }, [])
  const patch = async (id: number, body: any) => { try { await api(`/admin/users/${id}`, { method: 'PATCH', body }); load(); toast('User updated') } catch (e: any) { toast(e.message, 'error') } }
  const del = async (u: any) => { if (!confirm(`Delete ${u.email} and their conversations?`)) return; try { await api(`/admin/users/${u.id}`, { method: 'DELETE' }); load(); toast('User deleted') } catch (e: any) { toast(e.message, 'error') } }
  if (!us) return <Spinner />
  return (
    <Panel>
      <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="muted text-left text-xs"><tr><th className="py-1">User</th><th>Role</th><th>Status</th><th className="text-right">Queries</th><th>Joined</th><th>Last sign-in</th><th /></tr></thead>
        <tbody>{us.map(u => (
          <tr key={u.id} className="border-t line">
            <td className="py-2"><div className="font-semibold">{u.name}</div><div className="muted text-xs">{u.email}</div></td>
            <td><Select className="w-auto py-1" value={u.role} disabled={u.id === user?.id} onChange={e => patch(u.id, { role: e.target.value })}>{['farmer', 'expert', 'admin'].map(r => <option key={r}>{r}</option>)}</Select></td>
            <td>{u.active ? <Badge tone="good">active</Badge> : <Badge tone="bad">disabled</Badge>}</td>
            <td className="text-right">{u.queries}</td><td className="muted text-xs">{fmtDate(u.created_at)}</td><td className="muted text-xs">{u.last_login ? fmtDate(u.last_login) : '—'}</td>
            <td className="text-right whitespace-nowrap">{u.id !== user?.id && <><Button variant="quiet" onClick={() => patch(u.id, { active: !u.active })}>{u.active ? 'Disable' : 'Enable'}</Button><Button variant="danger" onClick={() => del(u)}>Delete</Button></>}</td>
          </tr>))}</tbody></table></div>
    </Panel>
  )
}

function Queries() {
  const [qs, setQs] = useState<any[] | null>(null)
  const [feature, setFeature] = useState('')
  useEffect(() => { setQs(null); api(`/admin/queries?limit=300${feature ? `&feature=${encodeURIComponent(feature)}` : ''}`).then(setQs) }, [feature])
  return (
    <Panel action={<Select className="w-48" value={feature} onChange={e => setFeature(e.target.value)} aria-label="Filter by feature"><option value="">All features</option>
      {['chat', 'search', 'disease', 'soil', 'crop-recommendation', 'irrigation', 'advisor', 'lab:rag', 'upload'].map(f => <option key={f}>{f}</option>)}</Select>} title="Recent queries">
      {!qs ? <Spinner /> : qs.length === 0 ? <p className="muted text-sm">No queries recorded.</p> : (
        <div className="max-h-[60vh] overflow-auto"><table className="w-full text-sm"><thead className="muted sticky top-0 bg-[var(--surface)] text-left text-xs"><tr><th className="py-1">When</th><th>User</th><th>Feature</th><th>Query</th><th>Lang</th><th className="text-right">Latency</th><th className="text-right">Grounded</th><th>Status</th></tr></thead>
          <tbody>{qs.map(q => (
            <tr key={q.id} className="border-t line align-top"><td className="muted py-1.5 text-xs whitespace-nowrap">{fmtDate(q.created_at)}</td><td className="text-xs">{q.email}</td><td><Badge>{q.feature}</Badge></td>
              <td className="max-w-md">{q.query}{q.error && <div className="text-xs text-red-700 dark:text-red-400">{q.error}</div>}</td><td className="text-xs">{q.language ?? ''}</td>
              <td className="text-right text-xs tabular-nums">{q.latency_ms ? `${Math.round(q.latency_ms)} ms` : ''}</td><td className="text-right text-xs">{q.groundedness != null ? pct(q.groundedness, 0) : ''}</td>
              <td>{q.ok ? <Badge tone="good">ok</Badge> : <Badge tone="warn">fallback/error</Badge>}</td></tr>))}</tbody></table></div>
      )}
    </Panel>
  )
}

function Config() {
  const { toast } = useApp()
  const [s, setS] = useState<any>(null)
  const [prov, setProv] = useState<any>(null)
  const [newKey, setNewKey] = useState('')
  const [newDataKey, setNewDataKey] = useState('')
  const [models, setModels] = useState<any>(null)
  const [test, setTest] = useState<any>(null)
  const [busy, setBusy] = useState('')
  const apply = (r: any) => { setS(r.settings); setProv(r.provider) }
  useEffect(() => { api('/admin/settings').then(apply) }, [])
  if (!s) return <Spinner />
  const set = (k: string) => (e: any) => setS({ ...s, [k]: e.target.value })
  const payload = (extra: any = {}) => {
    const { xai_api_key_set, xai_api_key_source, data_gov_api_key_set, data_gov_api_key_source, ...rest } = s
    void xai_api_key_set; void xai_api_key_source; void data_gov_api_key_set; void data_gov_api_key_source
    return { ...rest, ...(newKey && { xai_api_key: newKey }), ...(newDataKey && { data_gov_api_key: newDataKey }), ...extra }
  }
  const save = async (e?: FormEvent, extra: any = {}) => {
    e?.preventDefault(); setBusy('save')
    try { apply(await api('/admin/settings', { method: 'PUT', body: payload(extra) })); setNewKey(''); setNewDataKey(''); toast('Settings saved') }
    catch (x: any) { toast(x.message, 'error'); throw x } finally { setBusy('') }
  }
  const run = async (what: string) => {
    setBusy(what)
    try {
      if (what === 'test') { await save(); setBusy('test'); setTest(await api('/admin/settings/test', { method: 'POST' })) }
      if (what === 'models') setModels(await api('/admin/models'))
      if (what === 'reindex') { const r = await api('/admin/reindex', { method: 'POST' }); toast(`Re-indexed ${r.chunks} passages in ${r.seconds}s with ${r.embedder.kind}`) }
    } catch (x: any) { toast(x.message, 'error') } finally { setBusy('') }
  }
  const isX = s.llm_provider === 'xai'
  return (
    <form onSubmit={save} className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-6">
        <Panel title="Provider status" tone="soft">
          <dl className="grid grid-cols-2 gap-4 text-sm">
            <div><dt className="muted text-xs">Active provider</dt><dd className="font-semibold">{prov.label}</dd></div>
            <div><dt className="muted text-xs">Active model</dt><dd className="font-semibold break-all">{prov.model}</dd></div>
            <div><dt className="muted text-xs">Endpoint</dt><dd className="break-all">{prov.base_url}</dd></div>
            <div><dt className="muted text-xs">Status</dt><dd>{!prov.configured ? <Badge tone="warn">API key missing</Badge> : test ? (test.ok ? <Badge tone="good">connected</Badge> : <Badge tone="bad">{test.kind ?? 'error'}</Badge>) : <Badge tone="info">not tested yet</Badge>}</dd></div>
          </dl>
        </Panel>
        <Panel title="Language model">
          <div className="space-y-3">
            <Field label="Provider"><Select value={s.llm_provider} onChange={set('llm_provider')}><option value="xai">Grok by xAI (cloud)</option><option value="ollama">Ollama (local)</option></Select></Field>
            {isX ? <>
              <Field label="xAI API key" hint={s.xai_api_key_set ? `A key is saved (${s.xai_api_key_source === 'env' ? 'from backend/.env' : 'in Admin'}). It is never shown again; type a new key to replace it.` : 'Create a key at console.x.ai → API Keys. It stays on this server and is never sent back to the browser.'}>
                <Input type="password" value={newKey} onChange={e => setNewKey(e.target.value)} placeholder={s.xai_api_key_set ? '•••••••• saved' : 'xai-…'} autoComplete="new-password" />
              </Field>
              {s.xai_api_key_source === 'admin' && <Button type="button" variant="danger" onClick={() => { if (confirm('Remove the saved xAI key?')) save(undefined, { xai_api_key: null }).catch(() => {}) }}>Remove saved key</Button>}
              <Field label="Grok model" hint="Default grok-4-1-fast-reasoning. Use “List available models” to see what your key can access."><Input value={s.xai_model} onChange={set('xai_model')} list="model-list" /></Field>
              <Field label="API base URL"><Input value={s.xai_base_url} onChange={set('xai_base_url')} /></Field>
            </> : <>
              <Field label="Ollama URL"><Input value={s.ollama_url} onChange={set('ollama_url')} /></Field>
              <Field label="Ollama model" hint="Pull it first, e.g. `ollama pull llama3.2:3b`."><Input value={s.ollama_model} onChange={set('ollama_model')} list="model-list" /></Field>
            </>}
            <datalist id="model-list">{models?.models?.map((m: string) => <option key={m} value={m} />)}</datalist>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Temperature"><Input type="number" step="0.05" min={0} max={2} value={s.temperature} onChange={set('temperature')} /></Field>
              <Field label="Request timeout (s)"><Input type="number" min={5} max={600} value={s.llm_timeout} onChange={set('llm_timeout')} /></Field>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="ghost" type="button" loading={busy === 'test'} onClick={() => run('test')}>Save and test connection</Button>
              <Button variant="ghost" type="button" loading={busy === 'models'} onClick={() => run('models')}>List available models</Button>
            </div>
            {test && (test.ok
              ? <Notice>Connected to {test.label} · model <b>{test.model}</b> · {(test.latency_ms / 1000).toFixed(2)} s{test.usage ? ` · ${test.usage.total_tokens} tokens (${test.usage.prompt_tokens} in, ${test.usage.completion_tokens} out${test.usage.reasoning_tokens ? `, ${test.usage.reasoning_tokens} reasoning` : ''})` : ''}{test.retries ? ` · ${test.retries} retries` : ''}<br />“{test.text}”</Notice>
              : <Notice tone="bad">{test.error}</Notice>)}
            {models && (models.error ? <Notice tone="bad">{models.error}</Notice> : <div className="muted text-xs">{models.models.length} models available: {models.models.join(', ')}</div>)}
          </div>
        </Panel>
      </div>
      <div className="space-y-6">
        <Panel title="Retrieval">
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2"><Field label="Embedding model (Sentence-Transformers)" hint="Changing it re-embeds every passage. The default multilingual model supports Kannada and Hindi queries."><Input value={s.embedding_model} onChange={set('embedding_model')} /></Field></div>
            <Field label="Passages retrieved (top-K)"><Input type="number" min={1} max={12} value={s.top_k} onChange={set('top_k')} /></Field>
            <Field label="Grounding threshold"><Input type="number" step="0.05" min={0} max={1} value={s.grounding_threshold} onChange={set('grounding_threshold')} /></Field>
            <Field label="Chunk size (characters)" hint="Applies to new uploads."><Input type="number" min={200} max={4000} value={s.chunk_size} onChange={set('chunk_size')} /></Field>
            <Field label="Chunk overlap"><Input type="number" min={0} max={1000} value={s.chunk_overlap} onChange={set('chunk_overlap')} /></Field>
          </div>
          <Button variant="ghost" type="button" className="mt-3" loading={busy === 'reindex'} onClick={() => run('reindex')}>Rebuild vector index</Button>
        </Panel>
        <Panel title="Market data">
          <Field label="data.gov.in API key" hint={s.data_gov_api_key_set ? 'A key is saved. Type a new key to replace it.' : 'Free key from data.gov.in → My Account; used for live Agmarknet prices.'}>
            <Input type="password" value={newDataKey} onChange={e => setNewDataKey(e.target.value)} placeholder={s.data_gov_api_key_set ? '•••••••• saved' : ''} autoComplete="new-password" />
          </Field>
        </Panel>
        <Button loading={busy === 'save'}>Save changes</Button>
      </div>
    </form>
  )
}
