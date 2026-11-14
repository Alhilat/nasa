import { useEffect, useState } from 'react';
import { Database, FileCheck2, RefreshCw } from 'lucide-react';
import { api } from '../api';
import type { Job, Source } from '../types';

export default function Sources() {
  const [sources, setSources] = useState<Source[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setBusy(true); setError(''); setSources([]); setJobs([]);
    Promise.all([api.sources(controller.signal, offset), api.jobs(controller.signal)])
      .then(([sourceData, jobData]) => { if (!controller.signal.aborted) { setSources(sourceData.items); setHasMore(sourceData.has_more); setJobs(jobData); } })
      .catch(e => { if (!controller.signal.aborted) setError(e.message); })
      .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [refresh, offset]);

  return <><header className="page-header"><div><h1>Data sources</h1><p>Imported files and processing history.</p></div><button className="button secondary" onClick={() => setRefresh(n => n + 1)} disabled={busy}><RefreshCw size={15} /> Refresh</button></header>
    {error && <div role="alert" className="connection-notice">{error}</div>}
    <section className="panel"><div className="panel-heading"><div><h2>Source archive</h2><p>Original files with retrieval dates and SHA-256 checksums.</p></div><FileCheck2 size={21} className="muted" /></div>
      {busy ? <div className="empty-state" role="status">Loading source archive…</div> : sources.length ? <div className="table-scroll"><table><thead><tr><th>Source file</th><th>Sensor</th><th>Product</th><th>Rows</th><th>SHA-256</th></tr></thead><tbody>{sources.map(s => <tr key={s.id}><td><span>{s.original_filename}</span><small>Retrieved {new Date(s.retrieved_at).toISOString()}</small></td><td>{s.sensor_code}</td><td>{s.product_version}<small>{s.processing_level}</small></td><td>{s.row_count.toLocaleString()}</td><td><code title={s.sha256}>{s.sha256.slice(0, 12)}…</code><button className="copy-button" onClick={() => navigator.clipboard.writeText(s.sha256)}>Copy</button></td></tr>)}</tbody></table></div> : <div className="empty-state"><Database size={30} strokeWidth={1.3} /><h3>{error ? 'Archive unavailable' : 'No source files'}</h3><p>No archive data is available yet. Contact your administrator.</p></div>}
      <div className="pagination"><button className="button secondary" disabled={offset === 0 || busy} onClick={() => setOffset(n => Math.max(0, n - 50))}>Previous</button><span>Page {offset / 50 + 1}</span><button className="button secondary" disabled={!hasMore || busy || !!error} onClick={() => setOffset(n => n + 50)}>Next</button></div>
    </section>
    <section className="panel jobs-panel"><div className="panel-heading"><div><h2>Processing history</h2><p>The latest 50 jobs, with method versions and results.</p></div></div>{jobs.length ? <div className="table-scroll"><table><thead><tr><th>Job</th><th>Method</th><th>Started (UTC)</th><th>Status</th><th>Details</th></tr></thead><tbody>{jobs.map(j => <tr key={j.id}><td>{j.kind}<small>{j.id.slice(0, 8)}</small></td><td><code>{j.algorithm_version}</code></td><td>{new Date(j.started_at).toISOString()}</td><td><span className={`job-status ${j.status}`}>{j.status}</span></td><td><details><summary>View metadata</summary><pre>{JSON.stringify(j.output_metadata, null, 2)}</pre>{j.error_message && <p>{j.error_message}</p>}</details></td></tr>)}</tbody></table></div> : <div className="empty-state compact">{busy ? 'Loading processing history…' : error ? 'Processing history unavailable.' : 'No processing jobs yet.'}</div>}</section>
    <div className="science-note"><FileCheck2 size={16} /><p>Source hashes establish file identity, not authenticity. User-supplied NASA exports retain their attribution; exact payload duplicates share a normalized record; changed fields and NRT/standard revisions remain distinct, with all raw copies retained.</p></div>
  </>;
}
