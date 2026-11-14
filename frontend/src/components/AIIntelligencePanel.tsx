import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { BrainCircuit, FileText, RefreshCw, Send, Trash2 } from 'lucide-react';
import { formatCount } from '../dashboard';
import { useResource } from '../useResource';
import type { HistoryQuery } from '../history';
import { intelligence } from '../intelligence';
import type { AIEvidence, AIReply, DateWindow, Statement } from '../intelligence';
import ScientificChart from './ScientificChart';

const evidenceValue = (value: number | string | null) => value === null ? 'Unknown / not comparable'
  : typeof value === 'number' ? Number.isInteger(value) ? formatCount(value)
    : value.toLocaleString(undefined, { maximumSignificantDigits: 6 }) : value;

function Statements({ statements, reportId }: { statements: Statement[]; reportId: string }) {
  return <ul className="ai-statements">{statements.map((s, i) => <li key={i}><p dir="auto">{s.text}</p><div className="ai-citations">{s.evidence_ids.map(id => <a key={id} href={`#evidence-${reportId}-${id}`} onClick={() => { const target = document.getElementById(`evidence-${reportId}-${id}`); const details = target?.closest('details'); if (details) details.open = true; }}>{id}</a>)}</div></li>)}</ul>;
}

function EvidenceCard({ evidence, reportId }: { evidence: AIEvidence; reportId: string }) {
  const [showCharts, setShowCharts] = useState(false);
  return <article className="ai-evidence-card" id={`evidence-${reportId}-${evidence.id}`}>
    <div className="ai-evidence-title"><code>{evidence.id}</code><span className={`assessment ${evidence.status === 'available' ? 'within_range' : ''}`}>{evidence.status}</span></div>
    <h4>{evidence.tool.replaceAll('_', ' ')}</h4>
    {evidence.status === 'unavailable' && <p className="analysis-explanation">{String(evidence.data.reason ?? 'No supporting dataset is available.')}</p>}
    <p className="ai-evidence-meta">Snapshot: {evidence.retrieved_at} · {evidence.cache_hit ? 'Cached for up to 30 seconds' : 'Fetched for this response'} · {evidence.source_count} source files</p>
    {!!evidence.facts.length && <div className="table-scroll ai-fact-table"><table><caption className="sr-only">Measurements for {evidence.id}</caption><thead><tr><th>Metric</th><th>Sensor / period</th><th>Value</th><th>Unit</th></tr></thead><tbody>{evidence.facts.map((f, i) => <tr key={i}><td>{f.label}</td><td>{f.sensor ?? '—'}<small>{f.period}</small></td><td>{evidenceValue(f.value)}</td><td>{f.unit ?? '—'}</td></tr>)}</tbody></table></div>}
    {!!evidence.charts.length && <><button className="button secondary" onClick={() => setShowCharts(!showCharts)} aria-expanded={showCharts}>{showCharts ? 'Hide evidence charts' : 'Show evidence charts'}</button>{showCharts && evidence.charts.map((chart, i) => <div className="ai-evidence-chart" key={i}><h4>{chart.title}</h4><ScientificChart {...chart} metadata={{ evidence_id: evidence.id, analysis_ids: evidence.analysis_ids, scope: evidence.scope, sources: evidence.sources }} /></div>)}</>}
    <details><summary>Sources, methods and limitations</summary><pre>{JSON.stringify({ scope: evidence.scope, analysis_ids: evidence.analysis_ids, details: evidence.data }, null, 2)}</pre>
      {evidence.sources.length > 0 && <ul className="ai-sources">{evidence.sources.map(source => <li key={source.id}><span>Source · {source.sensor_code}</span><small>Product {source.product_version ?? 'not recorded'}</small><code className="hash">SHA-256: {source.sha256}</code></li>)}</ul>}
      {evidence.source_list_truncated && <p>This list is truncated. The analysis includes all source files.</p>}
      <ul>{evidence.limitations.map((note, i) => <li key={i}>{note}</li>)}</ul>
    </details>
  </article>;
}

function Answer({ reply }: { reply: AIReply }) {
  const interpretation = reply.interpretation;
  return <div className="ai-answer"><div className="ai-answer-heading"><span><BrainCircuit size={16} /> AI response</span><small>{reply.model} · {reply.status.replaceAll('_', ' ')}</small></div>
    {reply.notices.map((note, i) => <p className="form-notice" key={i}>{note}</p>)}
    {interpretation ? <><h4>Summary</h4><Statements statements={interpretation.executive_summary} reportId={reply.report_id} />{!!interpretation.interpretations.length && <><h4>Analysis</h4><Statements statements={interpretation.interpretations} reportId={reply.report_id} /></>}</> : <p className="analysis-explanation">The AI response is unavailable. Retrieved data is shown below.</p>}
    <details className="ai-report-sections"><summary>Counts, comparisons and anomalies</summary>{[['historical_observations', 'Historical observations'], ['statistical_comparisons', 'Statistical comparisons'], ['anomalies', 'Anomalies']].map(([section, title]) => {
      const facts = reply.evidence.flatMap(e => e.facts.filter(f => f.section === section).map(f => ({ ...f, evidence_id: e.id })));
      return <div key={section}><h4>{title}</h4>{facts.length ? <ul>{facts.map((f, i) => <li key={i}>{f.label} · {f.sensor} {f.period}: <strong>{evidenceValue(f.value)}</strong> {f.unit} <a href={`#evidence-${reply.report_id}-${f.evidence_id}`}>{f.evidence_id}</a></li>)}</ul> : <p>No results available for this section.</p>}</div>;
    })}</details>
    <details className="ai-report-sections"><summary>Supporting data and limitations</summary><div className="ai-evidence-list">{reply.evidence.map(e => <EvidenceCard key={e.id} evidence={e} reportId={reply.report_id} />)}</div>
    {interpretation && <><h4>Data limitations</h4><Statements statements={interpretation.data_limitations} reportId={reply.report_id} /><h4>Suggested follow-up</h4><Statements statements={interpretation.recommendations} reportId={reply.report_id} /></>}
    </details>
  </div>;
}

export default function AIIntelligencePanel({ context, dateWindow }: { context: HistoryQuery; dateWindow?: DateWindow }) {
  const [connectionRevision, setConnectionRevision] = useState(0);
  const status = useResource('ai-status', signal => intelligence.status(signal), connectionRevision);
  const [question, setQuestion] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [fresh, setFresh] = useState(false), [conversationId, setConversationId] = useState<string>();
  const [turns, setTurns] = useState<{ question: string; reply: AIReply }[]>([]);
  const [scopeNotice, setScopeNotice] = useState('');
  const active = useRef<AbortController | null>(null), sequence = useRef(0), previousScope = useRef(JSON.stringify({ context, dateWindow }));
  const prompt = useRef<HTMLTextAreaElement>(null);
  const contextKey = JSON.stringify({ context, dateWindow });
  useEffect(() => {
    if (previousScope.current !== contextKey) {
      previousScope.current = contextKey; sequence.current += 1; active.current?.abort();
      setBusy(false); setTurns([]); setConversationId(undefined); setError('');
      setScopeNotice('Selection changed. Conversation cleared.');
    }
  }, [contextKey]);
  useEffect(() => () => { sequence.current += 1; active.current?.abort(); }, []);

  async function submit(report = false) {
    const message = question.trim() || (report ? 'Summarize detections, trends and data limitations for the selected area and dates.' : '');
    if (!message || busy || !status.data?.configured) return;
    const controller = new AbortController(); active.current = controller;
    const current = ++sequence.current; setBusy(true); setError(''); setScopeNotice('');
    try {
      const reply = await intelligence.ask(message, context, conversationId, report, controller.signal, fresh, dateWindow);
      if (current !== sequence.current) return;
      setConversationId(reply.conversation_id); setTurns(previous => [...previous.slice(-5), { question: message, reply }]); setQuestion('');
    } catch (e) { if (current === sequence.current && !controller.signal.aborted) setError(e instanceof Error ? e.message : 'Assistant unavailable.'); }
    finally { if (current === sequence.current) setBusy(false); }
  }
  function send(event: FormEvent) { event.preventDefault(); void submit(); }
  async function reset() {
    if (busy) return;
    try { if (conversationId) await intelligence.reset(conversationId); }
    catch { /* Local state can still be cleared after server expiration. */ }
    setTurns([]); setConversationId(undefined); setError(''); setQuestion(''); setScopeNotice('Conversation cleared.');
  }
  const enabled = !!status.data?.configured && !busy;
  const suggestions = ['Summarize detections in this area.', 'Which months have unusually high or low counts?', `Compare monthly counts in ${context.start_year} and ${context.end_year}.`, 'Which months have incomplete data?'];

  return <section className="panel ai-intelligence-panel" aria-label="AI assistant">
    <div className="panel-heading"><div className="panel-title"><span className="section-icon"><BrainCircuit size={20} /></span><div><h2>AI assistant</h2><p>Ask about detections and trends in the selected area.</p></div></div></div>
    <div className="ai-context-strip"><span>Selection: <strong>{dateWindow ? `${dateWindow.start_date} — ${dateWindow.end_date}` : `${context.start_year}–${context.end_year}`}</strong> · {context.polygon ? 'selected polygon' : 'bounding box'} · {context.sensors.join(', ')} · {dateWindow ? 'UTC · partial months excluded from comparisons' : 'full years · UTC'}</span></div>
    {status.loading ? <p className="ai-service-state" role="status">Connecting to Gemini…</p> : status.error ? <div className="ai-service-state" role="alert"><span>Cannot connect to the assistant. {status.error}</span><button className="button secondary" onClick={() => setConnectionRevision(n => n + 1)}><RefreshCw size={14} /> Retry</button></div> : !status.data?.configured ? <p className="ai-service-state">The assistant is not connected. Ask your administrator to configure Gemini.</p> : null}
    <div className="ai-conversation">{turns.length === 0 && <div className="ai-welcome"><div className="ai-suggestions">{suggestions.map(s => <button key={s} type="button" disabled={!enabled} onClick={() => { setQuestion(s); prompt.current?.focus(); }}>{s}</button>)}</div></div>}
      {turns.map(turn => <article className="ai-turn" key={turn.reply.report_id}><div className="ai-user-question"><span>Your question</span><p dir="auto">{turn.question}</p></div><Answer reply={turn.reply} /></article>)}
      {busy && <div className="ai-thinking" role="status"><span className="loading-orbit" /> Loading data and preparing a response…</div>}
    </div>
    {scopeNotice && <p className="ai-inline-note" role="status">{scopeNotice}</p>}{error && <p className="ai-error" role="alert">{error}</p>}
    <form onSubmit={send} className="ai-composer"><label htmlFor="scientific-question">Question<textarea id="scientific-question" ref={prompt} value={question} onChange={e => setQuestion(e.target.value)} maxLength={3000} rows={3} placeholder="e.g. Which months had the most detections?" disabled={!enabled} /></label><div className="ai-composer-actions"><label className="ai-fresh"><input type="checkbox" checked={fresh} onChange={e => setFresh(e.target.checked)} /> Refresh analysis</label><button className="icon-button" type="button" aria-label="Clear conversation" disabled={busy || !turns.length} onClick={reset}><Trash2 size={16} /></button><button className="button secondary" type="button" disabled={!enabled} onClick={() => submit(true)}><FileText size={14} /> Generate report</button><button className="button primary" type="submit" disabled={!enabled || !question.trim()}><Send size={14} /> Ask</button></div><p className="ai-privacy">Your question, selected area and summary data are sent to Google Gemini when you submit. Responses can contain errors; check the linked data.</p></form>
  </section>;
}
