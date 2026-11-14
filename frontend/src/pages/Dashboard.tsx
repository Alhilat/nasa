import { useMemo, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Activity, ArrowDownToLine, ArrowRight, CalendarDays, ChevronDown, Database, Flame, Info, Layers2, RefreshCw, Satellite, ShieldCheck, SlidersHorizontal } from 'lucide-react';
import { api, inclusiveEndDate } from '../api';
import { boundsRegion, compare, detectionCsv, formatCount, historySelection, parseBounds, useResource } from '../dashboard';
import type { Region, Resource } from '../dashboard';
import { downloadArtifact, historyCsv, historyRequest } from '../history';
import type { HistoryQuery } from '../history';
import { sensorCodes } from '../types';
import type { ObservationProperties, Query } from '../types';
import RegionMap from '../components/RegionMap';
import BurningCalendar from '../components/BurningCalendar';
import ScientificChart from '../components/ScientificChart';
import ObservationInspector from '../components/ObservationInspector';
import AIIntelligencePanel from '../components/AIIntelligencePanel';

const initialQuery: Query = { start: '2013-01-01T00:00:00Z', end: '2026-01-01T00:00:00Z', bbox: [34, 29, 40, 34], sensors: [...sensorCodes], limit: 2000 };
function State({ loading, error, empty = false, children, message = 'No archived observations match this selection.' }: {
  loading: boolean; error: string; empty?: boolean; children: ReactNode; message?: string;
}) {
  if (loading) return <div className="resource-state" role="status"><div className="loading-orbit" /><strong>Reading your archive</strong><span>Retrieving observations and their scientific context…</span></div>;
  if (error) return <div className="resource-state error-state" role="alert"><Info size={24} /><strong>Data unavailable</strong><span>{error}</span></div>;
  if (empty) return <div className="resource-state"><Database size={26} /><strong>No data to display</strong><span>{message}</span></div>;
  return <>{children}</>;
}
function Metric({ title, value, note, icon, loading }: { title: string; value: number | null | undefined; note: string; icon: ReactNode; loading: boolean }) {
  return <article className="metric"><div className="metric-label">{title}<span className="metric-icon">{icon}</span></div><strong aria-busy={loading}>{loading ? <span className="skeleton-value" aria-label="Loading" /> : formatCount(value)}</strong><small>{note}</small></article>;
}
function Panel({ title, subtitle, icon, action, children, id }: { title: string; subtitle: string; icon: ReactNode; action?: ReactNode; children: ReactNode; id?: string }) {
  return <section className="panel dashboard-panel" id={id}><div className="panel-heading"><div className="panel-title"><span className="section-icon">{icon}</span><div><h2>{title}</h2><p>{subtitle}</p></div></div>{action}</div>{children}</section>;
}
const validData = <T,>(resource: Resource<T>) => resource.data !== null && !resource.error && !resource.loading;

export default function Dashboard() {
  const [query, setQuery] = useState<Query>(initialQuery);
  const [historyQuery, setHistoryQuery] = useState<HistoryQuery>(() => historySelection(initialQuery, 95, 5, '[]'));
  const [start, setStart] = useState('2013-01-01'), [end, setEnd] = useState('2025-12-31');
  const [sensors, setSensors] = useState([...sensorCodes]);
  const [bbox, setBbox] = useState('34, 29, 40, 34'), [geometry, setGeometry] = useState('');
  const [confidence, setConfidence] = useState<Query['confidence']>();
  const [coverage, setCoverage] = useState('[]'), [percentile, setPercentile] = useState(95), [minimum, setMinimum] = useState(5);
  const [draftRegion, setDraftRegion] = useState<Region | null>(() => boundsRegion(initialQuery.bbox!));
  const [formError, setFormError] = useState(''), [notice, setNotice] = useState(''), [advanced, setAdvanced] = useState(false);
  const [revision, setRevision] = useState(0), [activeSensor, setActiveSensor] = useState(sensorCodes[0]);
  const [selectedMonth, setSelectedMonth] = useState(''), [selected, setSelected] = useState<ObservationProperties | null>(null);
  const [jobOverride, setJobOverride] = useState(''), [draftJobId, setDraftJobId] = useState('');
  const [exporting, setExporting] = useState(false), [exportError, setExportError] = useState('');
  const key = JSON.stringify(query);
  const observations = useResource(key, signal => api.observations(query, signal), revision);
  const summary = useResource(key, signal => api.summary(query, signal), revision);
  const history = useResource(JSON.stringify(historyQuery), signal => historyRequest(historyQuery, signal), revision);
  const jobs = useResource('processing-jobs', signal => api.jobs(signal), revision);
  const successfulJobs = jobs.data?.filter(j => j.kind === 'aggregate' && j.status === 'succeeded') ?? [];
  const jobId = jobOverride || successfulJobs[0]?.id || '';
  const comparison = useResource(jobId ? `${key}:${jobId}` : null, signal => compare(jobId, query, signal), revision);
  const busy = observations.loading || summary.loading || history.loading;
  const rows = useMemo(() => history.data?.monthly.filter(r => r.sensor_code === activeSensor) ?? [], [history.data, activeSensor]);
  const inspectedMonth = rows.find(r => r.month === selectedMonth) ?? [...rows].reverse().find(r => r.count !== null) ?? rows.at(-1);
  const flagged = rows.filter(r => ['unusually_high', 'unusually_low'].includes(r.anomaly_status));
  const eligible = rows.filter(r => !['incomplete_period', 'insufficient_history'].includes(r.anomaly_status)).length;
  const trendLabels = useMemo(() => rows.map(r => r.month), [rows]);
  const trendSeries = useMemo(() => [
    { name: 'Archived detections', values: rows.map(r => r.count), color: '#f5af4d' },
    { name: 'Prior-year median', values: rows.map(r => r.historical_median), color: '#78c8c0', dashed: true },
    { name: 'Upper percentile', values: rows.map(r => r.upper_threshold), color: '#b99df2', dashed: true },
  ], [rows]);
  const comparisonSensors = useMemo(() => [...new Set(comparison.data?.daily.map(d => d.sensor_code) ?? [])], [comparison.data]);
  const comparisonSeries = useMemo(() => [
    { name: 'Raw normalized detections', color: '#e7b967', values: comparisonSensors.map(s => comparison.data!.daily.filter(d => d.sensor_code === s).reduce((n, d) => n + d.raw_count, 0)) },
    { name: 'Stored common-grid counts', color: '#73b4c0', values: comparisonSensors.map(s => comparison.data!.daily.filter(d => d.sensor_code === s).reduce((n, d) => n + d.grid_count, 0)) },
  ], [comparison.data, comparisonSensors]);

  function clearCoverage() { setCoverage('[]'); setNotice('Selection changed. Reattach completeness declarations audited for this exact area, sensor and confidence selection.'); }
  function drawn(region: Region) { clearCoverage(); setDraftRegion(region); setGeometry(JSON.stringify(region)); setBbox(''); setNotice('Region selected. Apply filters to update the map and analysis.'); }
  function clearRegion() { clearCoverage(); setDraftRegion(boundsRegion([34, 29, 40, 34])); setGeometry(''); setBbox('34, 29, 40, 34'); setNotice('Reset to the Jordan study envelope. Apply filters to update results.'); }
  function apply(event: FormEvent) {
    event.preventDefault(); setFormError(''); setExportError('');
    try {
      if (!start || !end || !/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end) || start > end) throw new Error('Choose an ordered start and end date.');
      if (!sensors.length) throw new Error('Select at least one sensor.');
      if (draftJobId && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(draftJobId)) throw new Error('Use a complete UUID for the aggregate job, or leave it blank.');
      const bounds = bbox.trim() ? parseBounds(bbox) : undefined;
      const polygon = geometry.trim() ? JSON.parse(geometry) : undefined;
      if (!bounds && !polygon) throw new Error('Draw a region or supply bounds / GeoJSON.');
      if (polygon && !['Polygon', 'MultiPolygon'].includes(polygon.type)) throw new Error('Supply a GeoJSON Polygon or MultiPolygon geometry.');
      const selection: Query = { start: `${start}T00:00:00Z`, end: inclusiveEndDate(end), sensors, bbox: bounds, polygon, confidence, limit: 2000 };
      const historical = historySelection(selection, percentile, minimum, coverage);
      setQuery(selection); setHistoryQuery(historical); setJobOverride(draftJobId); setActiveSensor(sensors.includes(activeSensor) ? activeSensor : sensors[0]);
      setDraftRegion(polygon ?? (bounds ? boundsRegion(bounds) : null)); setSelected(null); setSelectedMonth(''); setNotice(''); setRevision(n => n + 1);
    } catch (error) { setFormError(error instanceof Error ? error.message : 'Check your filters.'); }
  }
  async function exportData(kind: 'detections' | 'calendar' | 'json') {
    setExporting(true); setExportError('');
    try {
      if (kind === 'detections') downloadArtifact(await detectionCsv(query), 'firescope-detections.csv', 'text/csv');
      else if (history.data) {
        if (kind === 'calendar') downloadArtifact(await historyCsv(history.data), 'firescope-calendar.csv', 'text/csv');
        else downloadArtifact(JSON.stringify(history.data, null, 2), 'firescope-analysis.json', 'application/json');
      }
    } catch (error) { setExportError(error instanceof Error ? error.message : 'Export failed.'); }
    finally { setExporting(false); }
  }
  const sensorControl = <label className="inline-select">Analysis sensor<select aria-label="Analysis sensor" value={activeSensor} onChange={e => { setActiveSensor(e.target.value); setSelectedMonth(''); }}>{historyQuery.sensors.map(s => <option key={s}>{s}</option>)}</select></label>;

  return <div className="dashboard">
    <header className="page-header"><div><div className="eyebrow flex items-center gap-2"><Satellite size={14} /> SATELLITE OBSERVATION WORKSPACE</div><h1>Historical fire intelligence<span>.</span></h1><p>Explore the signal. Understand the context.</p></div><div className="header-actions"><button className="button secondary" onClick={() => { setSelected(null); setRevision(n => n + 1); }} disabled={busy}><RefreshCw size={15} /> Refresh</button><button className="button primary" disabled={!validData(summary) || exporting} onClick={() => exportData('detections')}><ArrowDownToLine size={15} /> {exporting ? 'Exporting…' : 'Export detections CSV'}</button></div></header>
    <form className="panel dashboard-filters" onSubmit={apply} aria-label="Dashboard filters">
      <div className="filter-title"><SlidersHorizontal size={16} /><strong>Observation filters</strong><span className="subtle-tag">UTC</span></div>
      <div className="filter-controls"><label>Start date<input type="date" required value={start} onChange={e => setStart(e.target.value)} /></label><label>End date · inclusive<input type="date" required value={end} onChange={e => setEnd(e.target.value)} /></label><label className="region-field">Study area · west, south, east, north<input value={bbox} onChange={e => { setBbox(e.target.value); setGeometry(''); clearCoverage(); }} placeholder="Draw a region or enter coordinates" /></label><button type="button" className="button secondary" aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}>Analysis settings <ChevronDown size={14} /></button><button className="button primary" type="submit">Apply filters <ArrowRight size={14} /></button></div>
      <fieldset className="sensor-filters"><legend>Native sensors</legend>{sensorCodes.map(s => <label key={s}><input type="checkbox" checked={sensors.includes(s)} onChange={e => { setSensors(e.target.checked ? [...sensors, s] : sensors.filter(code => code !== s)); clearCoverage(); }} /><i className={`dot ${s.startsWith('MODIS') ? 'modis' : 'viirs'}`} />{s.replaceAll('_', ' ')}</label>)}</fieldset>
      {advanced && <div className="advanced-settings"><label>Confidence class<select value={confidence ?? ''} onChange={e => { setConfidence(e.target.value ? e.target.value as Query['confidence'] : undefined); clearCoverage(); }}><option value="">All classes</option><option value="low">Low</option><option value="nominal">Nominal</option><option value="high">High</option></select></label><label>Upper percentile<input type="number" min="50" max="99.99" step="0.01" value={percentile} onChange={e => setPercentile(Number(e.target.value))} required /></label><label>Minimum baseline years<input type="number" min="3" max="30" value={minimum} onChange={e => setMinimum(Number(e.target.value))} required /></label><label>Aggregate job ID · optional<input value={draftJobId} onChange={e => setDraftJobId(e.target.value.trim())} placeholder="Latest successful job by default" /></label><label className="history-wide">GeoJSON geometry · equivalent to map drawing<textarea rows={3} value={geometry} onChange={e => { setGeometry(e.target.value); clearCoverage(); }} placeholder='{"type":"Polygon","coordinates":[…]}' /></label><label className="history-wide">Audited complete-month declarations · JSON<textarea rows={3} value={coverage} onChange={e => setCoverage(e.target.value)} /></label><p className="history-wide">Only declare months whose archive completeness you have audited for this exact selection. Format: <code>{'[{"sensor_code":"MODIS_TERRA","month":"2013-01","reference":"your audit"}]'}</code>. Declarations are caller-attested. Missing coverage is never inferred from detections.</p></div>}
      {formError && <p className="form-error" role="alert">{formError}</p>}{notice && <p className="form-notice" role="status">{notice}</p>}
    </form>
    {exportError && <p className="connection-notice" role="alert">{exportError}</p>}
    <div className="workspace-status"><span><i className={`status-dot ${summary.error ? 'offline' : summary.loading ? 'waiting' : ''}`} />{summary.loading ? 'Connecting to archive' : summary.error ? 'Archive unavailable' : 'Archive connected'}</span><span>{query.start?.slice(0, 10)} — {new Date(new Date(query.end!).getTime() - 1).toISOString().slice(0, 10)} · {query.polygon ? 'Selected polygon' : 'Study envelope, not a country boundary'}</span></div>
    <section className="metrics" aria-label="Activity summary">
      <Metric title="Archived detections" value={summary.data?.detection_count} note="Selected dates · all selected sensors" icon={<Flame size={18} />} loading={summary.loading} />
      <Metric title="Common-grid activity" value={comparison.data?.grid_count} note="Stored job · matched full-cell/day scope" icon={<Layers2 size={18} />} loading={comparison.loading} />
      <Metric title="Original source files" value={summary.data?.source_count} note="All linked source copies retained" icon={<Database size={18} />} loading={summary.loading} />
      <Metric title="Summed observed FRP · MW" value={summary.data?.frp_sum_mw} note={`${formatCount(summary.data?.frp_known_count)} records with FRP · not fire energy`} icon={<Activity size={18} />} loading={summary.loading} />
    </section>
    {summary.error && <div className="connection-notice" role="alert"><Info size={18} /><div><strong>Connect your scientific archive</strong><p>{summary.error} Refresh after starting FastAPI and PostGIS.</p></div></div>}
    {!summary.loading && summary.data?.detection_count === 0 && <div className="connection-notice"><Database size={20} /><div><strong>No detections match these filters</strong><p>Broaden your selection or ingest official FIRMS observations. No demonstration observations are substituted.</p></div><Link className="text-link" to="/sources">Data & provenance <ArrowRight size={14} /></Link></div>}
    <div className="dashboard-map-grid"><Panel title="Observation map" subtitle="Native thermal detections · WGS84 / EPSG:4326" icon={<Layers2 size={18} />} action={<span className="subtle-tag">INTERACTIVE</span>}><div className="map-wrap"><RegionMap data={observations.data} region={draftRegion} loading={observations.loading} scopeLabel={`Applied dates: ${query.start} to ${query.end} (end exclusive). Applied area: ${query.polygon ? 'selected polygon; see analysis JSON for geometry' : JSON.stringify(query.bbox)}`} onRegion={drawn} onClear={clearRegion} onSelect={setSelected} />{selected && <ObservationInspector observation={selected} close={() => setSelected(null)} />}</div>{observations.error && <p className="panel-message" role="alert">{observations.error}</p>}<div className="map-footer"><span>Map: {formatCount(observations.data?.metadata.returned)} observations{observations.data?.metadata.has_more ? ' · capped page; exports and totals cover the full selection' : ''}</span><span>Click a detection for its provenance</span></div></Panel>
      <aside className="panel context-panel"><span className="eyebrow">READ THE SIGNAL</span><h2>Observations.<br />With their context.</h2><p>MODIS and VIIRS see the same landscape at different resolutions and overpass times.</p><div className="sensor-totals">{query.sensors.map(s => <div key={s}><span><i className={`dot ${s.startsWith('MODIS') ? 'modis' : 'viirs'}`} />{s.replaceAll('_', ' ')}</span><strong>{summary.data ? formatCount(summary.data.by_sensor[s] ?? 0) : '—'}</strong></div>)}</div><div className="context-warning"><ShieldCheck size={17} /><span>Detections are not unique fire events. Operational sensor calibration and risk forecasting are not enabled.</span></div><Link className="text-link" to="/methodology">Explore the methodology <ArrowRight size={14} /></Link></aside></div>
    <div className="section-divider"><div><h2>Historical intelligence</h2><p>Full-year context: {historyQuery.start_year}–{historyQuery.end_year} · same area and confidence selection. Each sensor is assessed separately.</p></div>{sensorControl}</div>
    <div className="dashboard-analysis-grid"><Panel title="Burning activity calendar" subtitle={`${activeSensor} · year-by-month archived detections`} icon={<CalendarDays size={18} />} action={<button className="icon-button" aria-label="Export monthly calendar CSV" disabled={!validData(history) || exporting} onClick={() => exportData('calendar')}><ArrowDownToLine size={16} /></button>}><State {...history} empty={!history.data?.monthly.some(r => r.count !== null)}><BurningCalendar rows={history.data?.monthly ?? []} sensor={activeSensor} selected={inspectedMonth?.month ?? ''} onSelect={setSelectedMonth} /></State></Panel>
      <Panel title="Anomaly analysis" subtitle="Unusual archived activity · no fire-risk forecasts" icon={<Activity size={18} />}><State {...history} empty={!rows.length}>{inspectedMonth && <div className="anomaly-content"><div className="anomaly-heading"><span className="eyebrow">{inspectedMonth.month} · {activeSensor}</span><span className={`assessment ${inspectedMonth.anomaly_status}`}>{inspectedMonth.anomaly_status.replaceAll('_', ' ')}</span></div><dl className="anomaly-metrics"><div><dt>Archived detections</dt><dd>{formatCount(inspectedMonth.count)}</dd></div><div><dt>Historical median</dt><dd>{formatCount(inspectedMonth.historical_median)}</dd></div><div><dt>Lower / upper threshold</dt><dd>{formatCount(inspectedMonth.lower_threshold)} / {formatCount(inspectedMonth.upper_threshold)}</dd></div><div><dt>Prior reference years</dt><dd>{inspectedMonth.baseline_size}</dd></div><div><dt>Robust z-score</dt><dd>{formatCount(inspectedMonth.robust_z)}</dd></div><div><dt>Year-on-year change</dt><dd>{inspectedMonth.year_over_year.percent_change === null ? 'Unavailable' : `${formatCount(inspectedMonth.year_over_year.percent_change)}%`}</dd></div></dl><p className="analysis-explanation">{inspectedMonth.anomaly_status === 'incomplete_period' ? 'Assessment withheld: month completeness is unknown. Add audited declarations in Analysis settings.' : inspectedMonth.anomaly_status === 'insufficient_history' ? `Assessment withheld: fewer than ${historyQuery.min_baseline_years} complete earlier instances of this calendar month.` : 'Compared with complete earlier instances of the same calendar month, sensor and area. Percentile flags are descriptive, not probabilities.'}</p><div className="assessment-summary"><strong>{flagged.length}</strong> flagged / {eligible} assessed months <small>Full historical context · selected sensor</small></div></div>}</State></Panel></div>
    <div className="dashboard-chart-grid"><Panel title="Historical activity trend" subtitle={`${activeSensor} · monthly observations and earlier-year reference`} icon={<Activity size={18} />}><State {...history} empty={!rows.some(r => r.count !== null)}><ScientificChart title={`${activeSensor} historical activity trend`} labels={trendLabels} series={trendSeries} metadata={{ analysis_id: history.data?.analysis_id, query: history.data?.query, sources: history.data?.sources }} /><p className="chart-footnote">Gaps remain unknown. Positive counts may be incomplete. Reference thresholds require audited complete months.</p></State></Panel>
      <Panel title="Raw vs harmonized" subtitle="Normalized observations vs persisted common-grid aggregation" icon={<Layers2 size={18} />} action={<span className="subtle-tag">BIAS UNCORRECTED</span>}><State loading={jobs.loading || comparison.loading} error={jobs.error || comparison.error} empty={!comparison.data?.daily.length} message={jobId ? 'No full days and wholly contained occupied cells overlap this selection and the saved aggregate job.' : 'No recent successful aggregate job is available. Ingest data and run the documented aggregate pipeline, or enter an existing job ID in Analysis settings.'}><ScientificChart title="Matched raw and common-grid counts by sensor" kind="bar" labels={comparisonSensors} series={comparisonSeries} metadata={comparison.data} />{comparison.data && <div className="comparison-context"><p>{comparison.data.scope}</p><p>{comparison.data.method}</p>{comparison.data.archive_counts_match === false && <p className="form-error">Counts differ from the saved snapshot. Inspect job provenance before interpreting changes.</p>}<details><summary>Processing version & provenance</summary><pre>{JSON.stringify({ job_id: comparison.data.job_id, algorithm_version: comparison.data.algorithm_version, parameters: comparison.data.parameters, provenance: comparison.data.provenance }, null, 2)}</pre></details></div>}</State></Panel></div>
    <Panel title="Data provenance & uncertainty" subtitle="Trace every result back to its archive and analytical assumptions" icon={<ShieldCheck size={18} />} action={<button className="button secondary" disabled={!validData(history) || exporting} onClick={() => exportData('json')}><ArrowDownToLine size={14} /> Analysis JSON</button>}><State {...history} empty={!history.data?.sources.length} message="No source files are associated with the full-year historical selection."><div className="provenance-intro"><p>Full-year historical context · <strong>{history.data?.sources.length} source files</strong>. Source checksums identify archived content. They do not establish authenticity or complete observation coverage.</p><Link className="text-link" to="/sources">Full provenance archive <ArrowRight size={14} /></Link></div><div className="table-scroll provenance-table"><table><thead><tr><th>Original file</th><th>Sensor / product</th><th>Source SHA-256</th><th>Retrieved (UTC)</th></tr></thead><tbody>{history.data?.sources.slice(0, 5).map(s => <tr key={s.id}><td><a href={s.source_url} target="_blank" rel="noreferrer">{s.original_filename ?? s.id}</a></td><td>{s.sensor_code ?? 'See source'}<small>{s.product_version} · {s.processing_level}</small></td><td><code title={s.sha256}>{s.sha256.slice(0, 16)}…</code></td><td>{s.retrieved_at ?? 'Not recorded'}</td></tr>)}</tbody></table></div>{(history.data?.sources.length ?? 0) > 5 && <p className="chart-footnote">Showing five files; all selected source metadata is retained in the JSON export.</p>}<div className="uncertainty-grid"><div><h3>Observation uncertainty</h3><p>Native confidence is not a cross-sensor probability. Cloud cover, overpass timing, product revisions and sensor sensitivity affect detections. Select a map observation for its exact uncertainty metadata.</p></div><div><h3>Historical reference</h3><p>{history.data?.metric_explanations.baseline}</p></div><div><h3>Coverage & interpretation</h3><p>{history.data?.metric_explanations.coverage}</p></div></div><details className="history-details"><summary>All metric definitions & analysis identity</summary><p className="hash">{history.data?.analysis_id}</p>{Object.entries(history.data?.metric_explanations ?? {}).map(([name, description]) => <p key={name}><strong>{name.replaceAll('_', ' ')}:</strong> {description}</p>)}</details></State></Panel>
    <AIIntelligencePanel context={historyQuery} dateWindow={{ start_date: query.start!.slice(0, 10), end_date: new Date(new Date(query.end!).getTime() - 1).toISOString().slice(0, 10) }} />
    <div className="science-note"><Info size={16} /><p>Thermal detections are not unique fires, burned area or forecasts. The calendar and historical charts use complete-year context; map totals and detection CSV respect the exact date filters. Common-grid comparisons use their disclosed matched scope.</p></div>
  </div>;
}
