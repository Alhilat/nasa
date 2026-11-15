import { useMemo, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Activity, ArrowRight, CalendarDays, ChevronDown, Database, Info, Layers2, RefreshCw, ShieldCheck, SlidersHorizontal } from 'lucide-react';
import { api, inclusiveEndDate } from '../api';
import { archiveDates, boundsRegion, compare, formatCount, historySelection, parseBounds } from '../dashboard';
import type { Region } from '../dashboard';
import { useResource } from '../useResource';
import { comparisonLabel, comparisonValue, downloadArtifact, formatMissingDataStatus, historyCsv, historyRequest } from '../history';
import type { HistoryQuery } from '../history';
import { sensorCodes } from '../types';
import type { ObservationProperties, Query, Summary } from '../types';
import RegionMap from '../components/RegionMap';
import ActivityChart from '../components/ActivityChart';
import BurningCalendar from '../components/BurningCalendar';
import ScientificChart from '../components/ScientificChart';
import ObservationInspector from '../components/ObservationInspector';
import AIIntelligencePanel from '../components/AIIntelligencePanel';
import DateRangeControl, { displayDate } from '../components/DateRangeControl';
import SelectionOverview from '../components/SelectionOverview';

const studyAreas: { id: string; label: string; bounds: [number, number, number, number] }[] = [
  { id: 'jordan', label: 'Jordan study area', bounds: [34, 29, 40, 34] },
  { id: 'levant', label: 'Levant study area', bounds: [34, 29, 43, 38] },
];
const satelliteNames: Record<string, string> = {
  MODIS_TERRA: 'Terra', MODIS_AQUA: 'Aqua', VIIRS_SNPP: 'Suomi NPP',
  VIIRS_NOAA20: 'NOAA-20', VIIRS_NOAA21: 'NOAA-21',
};
function State({ loading, error, empty = false, children, message = 'No archived observations match this selection.' }: {
  loading: boolean; error: string; empty?: boolean; children: ReactNode; message?: string;
}) {
  if (loading) return <div className="resource-state" role="status"><div className="loading-orbit" /><strong>Loading observations…</strong></div>;
  if (error) return <div className="resource-state error-state" role="alert"><Info size={24} /><strong>Data unavailable</strong><span>{error}</span></div>;
  if (empty) return <div className="resource-state"><Database size={26} /><strong>No data to display</strong><span>{message}</span></div>;
  return <>{children}</>;
}
function Panel({ title, subtitle, icon, action, children, id }: { title: string; subtitle: string; icon: ReactNode; action?: ReactNode; children: ReactNode; id?: string }) {
  return <section className="panel dashboard-panel" id={id}><div className="panel-heading"><div className="panel-title"><span className="section-icon">{icon}</span><div><h2>{title}</h2><p>{subtitle}</p></div></div>{action}</div>{children}</section>;
}

export default function Dashboard() {
  const [attempt, setAttempt] = useState(0);
  const archive = useResource('archive-date-range', signal => api.summary({ sensors: [], limit: 1 }, signal), attempt);
  const dates = archive.data && archiveDates(archive.data);
  if (archive.data && dates) return <DashboardView archive={archive.data} dates={dates} />;
  return <><header className="page-header"><div><h1>Fire activity</h1><p>Filter satellite detections by area, date and sensor.</p></div></header>
    <section className="panel archive-loading">
      {archive.loading ? <div className="resource-state" role="status"><div className="loading-orbit" /><strong>Loading available dates…</strong></div>
        : archive.error ? <div className="resource-state error-state" role="alert"><Info size={24} /><strong>Archive unavailable</strong><span>{archive.error}</span></div>
          : <div className="resource-state"><Database size={26} /><strong>No observations in the archive</strong><span>No archive data is available yet. Contact your administrator.</span><Link className="text-link" to="/sources">View data sources</Link></div>}
      {!archive.loading && <button className="button secondary" onClick={() => setAttempt(n => n + 1)}><RefreshCw size={15} /> Refresh</button>}
    </section></>;
}

function DashboardView({ archive, dates }: { archive: Summary; dates: { first: string; last: string } }) {
  const availableSensors = sensorCodes.filter(sensor => (archive.by_sensor[sensor] ?? 0) > 0);
  const initialQuery: Query = { start: `${dates.first}T00:00:00Z`, end: inclusiveEndDate(dates.last), bbox: studyAreas[0].bounds, sensors: availableSensors, limit: 2000 };
  const [query, setQuery] = useState<Query>(initialQuery);
  const [historyQuery, setHistoryQuery] = useState<HistoryQuery>(() => historySelection(initialQuery, 95, 5, '[]'));
  const [start, setStart] = useState(dates.first), [end, setEnd] = useState(dates.last);
  const [sensors, setSensors] = useState(availableSensors);
  const [areaChoice, setAreaChoice] = useState('jordan');
  const [bbox, setBbox] = useState('34, 29, 40, 34'), [geometry, setGeometry] = useState('');
  const [confidence, setConfidence] = useState<Query['confidence']>();
  const [coverage, setCoverage] = useState('[]'), [percentile, setPercentile] = useState(95), [minimum, setMinimum] = useState(5);
  const [draftRegion, setDraftRegion] = useState<Region | null>(() => boundsRegion(initialQuery.bbox!));
  const [formError, setFormError] = useState(''), [notice, setNotice] = useState(''), [advanced, setAdvanced] = useState(false);
  const [revision, setRevision] = useState(0), [activeSensor, setActiveSensor] = useState(availableSensors[0]);
  const [selectedMonth, setSelectedMonth] = useState(''), [selected, setSelected] = useState<ObservationProperties | null>(null);
  const [mapMode, setMapMode] = useState<'all' | 'month'>('all');
  const [mapMonth, setMapMonth] = useState(dates.first.slice(0, 7));
  const [jobOverride, setJobOverride] = useState(''), [draftJobId, setDraftJobId] = useState('');
  const key = JSON.stringify(query);
  const observations = useResource(key, signal => api.observations(query, signal), revision);
  const firstMonth = query.start!.slice(0, 7);
  const lastMonth = new Date(new Date(query.end!).getTime() - 1).toISOString().slice(0, 7);
  const activeMapMonth = mapMonth < firstMonth ? firstMonth : mapMonth > lastMonth ? lastMonth : mapMonth;
  const nextMonth = new Date(`${activeMapMonth}-01T00:00:00Z`);
  nextMonth.setUTCMonth(nextMonth.getUTCMonth() + 1);
  const monthStart = `${activeMapMonth}-01T00:00:00.000Z`;
  const monthEnd = nextMonth.toISOString();
  const monthlyMapQuery: Query = { ...query, start: new Date(Math.max(Date.parse(query.start!), Date.parse(monthStart))).toISOString(), end: new Date(Math.min(Date.parse(query.end!), Date.parse(monthEnd))).toISOString() };
  const monthlyObservations = useResource(mapMode === 'month' ? JSON.stringify(monthlyMapQuery) : null, signal => api.observations(monthlyMapQuery, signal), revision);
  const mapObservations = mapMode === 'month' ? monthlyObservations : observations;
  const summary = useResource(key, signal => api.summary(query, signal), revision);
  const history = useResource(JSON.stringify(historyQuery), signal => historyRequest(historyQuery, signal), revision);
  const jobs = useResource('processing-jobs', signal => api.jobs(signal), revision);
  const successfulJobs = jobs.data?.filter(j => j.kind === 'aggregate' && j.status === 'succeeded') ?? [];
  const jobId = jobOverride || successfulJobs[0]?.id || '';
  const comparison = useResource(jobId ? `${key}:${jobId}` : null, signal => compare(jobId, query, signal), revision);
  const busy = observations.loading || summary.loading || history.loading;
  const rows = useMemo(() => history.data?.monthly.filter(r => r.sensor_code === activeSensor) ?? [], [history.data, activeSensor]);
  const inspectedMonth = rows.find(r => r.month === selectedMonth) ?? [...rows].reverse().find(r => r.completeness === 'complete' && r.count !== null) ?? [...rows].reverse().find(r => r.count !== null) ?? rows.at(-1);
  const flagged = rows.filter(r => ['unusually_high', 'unusually_low'].includes(r.anomaly_status));
  const eligible = rows.filter(r => !['incomplete_period', 'insufficient_history'].includes(r.anomaly_status)).length;
  const trendLabels = useMemo(() => rows.map(r => r.month), [rows]);
  const trendSeries = useMemo(() => [
    { name: comparisonLabel(rows), values: rows.map(comparisonValue), color: '#f5af4d' },
    { name: 'Prior-year median', values: rows.map(r => r.historical_median), color: '#78c8c0', dashed: true },
    { name: 'Upper percentile', values: rows.map(r => r.upper_threshold), color: '#b99df2', dashed: true },
  ], [rows]);
  const comparisonSensors = useMemo(() => [...new Set(comparison.data?.daily.map(d => d.sensor_code) ?? [])], [comparison.data]);
  const comparisonSeries = useMemo(() => [
    { name: 'Detections', color: '#e7b967', values: comparisonSensors.map(s => comparison.data!.daily.filter(d => d.sensor_code === s).reduce((n, d) => n + d.raw_count, 0)) },
    { name: 'Grid counts', color: '#73b4c0', values: comparisonSensors.map(s => comparison.data!.daily.filter(d => d.sensor_code === s).reduce((n, d) => n + d.grid_count, 0)) },
  ], [comparison.data, comparisonSensors]);

  function clearCoverage() {
    if (coverage !== '[]') { setCoverage('[]'); setNotice('Coverage declarations cleared because the selection changed.'); }
  }
  function chooseArea(value: string) {
    setAreaChoice(value); clearCoverage();
    const area = studyAreas.find(item => item.id === value);
    if (area) { setBbox(area.bounds.join(', ')); setGeometry(''); setDraftRegion(boundsRegion(area.bounds)); }
  }
  function apply(event: FormEvent) {
    event.preventDefault(); setFormError('');
    try {
      if (!start || !end || !/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end) || start > end) throw new Error('Choose an ordered start and end date.');
      if (start < dates.first || end > dates.last) throw new Error('Choose dates within the available archive range.');
      if (!sensors.length) throw new Error('Select at least one sensor.');
      if (draftJobId && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(draftJobId)) throw new Error('Use a complete UUID for the aggregate job, or leave it blank.');
      const bounds = bbox.trim() ? parseBounds(bbox) : undefined;
      const polygon = geometry.trim() ? JSON.parse(geometry) : undefined;
      if (!bounds && !polygon) throw new Error('Choose an area or provide a GeoJSON geometry.');
      if (polygon && !['Polygon', 'MultiPolygon'].includes(polygon.type)) throw new Error('Supply a GeoJSON Polygon or MultiPolygon geometry.');
      const selection: Query = { start: `${start}T00:00:00Z`, end: inclusiveEndDate(end), sensors, bbox: bounds, polygon, confidence, limit: 2000 };
      const historical = historySelection(selection, percentile, minimum, coverage);
      setQuery(selection); setHistoryQuery(historical); setJobOverride(draftJobId); setActiveSensor(sensors.includes(activeSensor) ? activeSensor : sensors[0]);
      setDraftRegion(polygon ?? (bounds ? boundsRegion(bounds) : null)); setSelected(null); setSelectedMonth(''); setNotice(''); setRevision(n => n + 1);
    } catch (error) { setFormError(error instanceof Error ? error.message : 'Check your filters.'); }
  }
  const sensorControl = <label className="inline-select">Analysis sensor<select aria-label="Analysis sensor" value={activeSensor} onChange={e => { setActiveSensor(e.target.value); setSelectedMonth(''); }}>{historyQuery.sensors.map(s => <option key={s}>{s}</option>)}</select></label>;
  function moveMapMonth(offset: number) {
    const date = new Date(`${activeMapMonth}-01T00:00:00Z`);
    date.setUTCMonth(date.getUTCMonth() + offset);
    setMapMonth(date.toISOString().slice(0, 7));
    setSelected(null);
  }

  return <div className="dashboard">
    <header className="page-header"><div><h1>Fire activity</h1><p>Filter satellite detections by area, date and sensor.</p></div><div className="header-actions"><button className="button secondary" onClick={() => { setSelected(null); setRevision(n => n + 1); }} disabled={busy}><RefreshCw size={15} /> Refresh</button></div></header>
    <form className="panel dashboard-filters" onSubmit={apply} aria-label="Dashboard filters">
      <div className="filter-title"><SlidersHorizontal size={16} /><strong>Observation filters</strong><span className="subtle-tag">UTC</span></div>
      <div className="filter-main-grid">
        <DateRangeControl first={dates.first} last={dates.last} start={start} end={end} onChange={(first, last) => { setStart(first); setEnd(last); if (first !== start || last !== end) clearCoverage(); }} />
        <div className="area-control">
          <label htmlFor="study-area">Area</label>
          <p className="filter-help" id="area-help">Choose a study area or enter coordinates.</p>
          <select id="study-area" value={areaChoice} aria-describedby="area-help" onChange={e => chooseArea(e.target.value)}>
            {studyAreas.map(area => <option key={area.id} value={area.id}>{area.label}</option>)}
            <option value="custom">Enter coordinates</option>
            {areaChoice === 'geometry' && <option value="geometry">Imported GeoJSON</option>}
          </select>
          {areaChoice !== 'custom' && areaChoice !== 'geometry' && <p className="filter-help">Study areas include nearby territory; they are not country borders.</p>}
          {areaChoice === 'custom' && <label className="custom-bounds">Coordinates · west, south, east, north<input value={bbox} onChange={e => { setBbox(e.target.value); setGeometry(''); clearCoverage(); }} placeholder="34, 29, 40, 34" /></label>}
        </div>
      </div>
      <fieldset className="satellite-picker"><legend>Satellites</legend>
        <div className="satellite-picker-heading"><p className="filter-help">Choose which satellites to include. Pixel size and overpass times differ.</p><button type="button" className="text-link" onClick={() => { setSensors(availableSensors); clearCoverage(); }}>Select all with data</button></div>
        <div className="satellite-options">{sensorCodes.map(s => {
          const count = archive.by_sensor[s] ?? 0;
          return <label key={s} className={'satellite-option ' + (sensors.includes(s) ? 'is-selected' : '') + (!count ? ' is-unavailable' : '')}>
            <input type="checkbox" aria-label={s.replaceAll('_', ' ')} disabled={!count} checked={sensors.includes(s)}
              onChange={e => { setSensors(e.target.checked ? [...sensors, s] : sensors.filter(code => code !== s)); clearCoverage(); }} />
            <span><strong>{satelliteNames[s]}</strong><small>{s.startsWith('MODIS') ? 'MODIS · 1 km pixels' : 'VIIRS · 375 m pixels'}</small><small>{count ? formatCount(count) + ' in archive' : 'No archived data'}</small></span>
          </label>;
        })}</div>
      </fieldset>
      <div className="filter-actions"><button type="button" className="button secondary" aria-expanded={advanced} aria-controls="analysis-options" onClick={() => setAdvanced(!advanced)}>Advanced settings <ChevronDown size={14} /></button><span>Changes take effect when you apply filters.</span><button className="button primary" type="submit">Apply filters <ArrowRight size={14} /></button></div>
      {advanced && <div className="analysis-options" id="analysis-options">
        <div className="analysis-controls">
          <label>Detection confidence<select aria-label="Detection confidence" value={confidence ?? ''} onChange={e => { setConfidence(e.target.value ? e.target.value as Query['confidence'] : undefined); clearCoverage(); }}><option value="">All confidence classes</option><option value="high">High only</option><option value="nominal">Nominal only</option><option value="low">Low only</option></select><small className="filter-help">Use the confidence class reported by each sensor. These classes are not probabilities.</small></label>
          <label>Unusual activity threshold<output>{percentile}th percentile</output><input type="range" min="50" max="99" step="1" value={percentile} aria-label="Unusual activity threshold" aria-describedby="threshold-help" aria-valuetext={percentile + 'th percentile'} onChange={e => setPercentile(Number(e.target.value))} /><span className="range-endpoints"><span>50th</span><span>99th</span></span><small id="threshold-help" className="filter-help">Flags counts above this percentile or below the matching lower percentile. A higher value flags fewer months.</small></label>
          <label>Earlier years needed<output>{minimum} years</output><input type="range" min="3" max="30" step="1" value={minimum} aria-label="Earlier years needed" aria-describedby="years-help" aria-valuetext={minimum + ' earlier complete years'} onChange={e => setMinimum(Number(e.target.value))} /><span className="range-endpoints"><span>3 years</span><span>30 years</span></span><small id="years-help" className="filter-help">Require this many complete earlier years of the same month before assessing unusual activity.</small></label>
          <label>Saved grid comparison<select aria-label="Saved grid comparison" value={draftJobId} disabled={!successfulJobs.length} onChange={e => setDraftJobId(e.target.value)}><option value="">{successfulJobs.length ? 'Latest saved grid' : 'No saved grids available'}</option>{successfulJobs.map(job => {
            const created = new Date(job.started_at).toISOString(), size = job.parameters.grid_size_deg;
            return <option key={job.id} value={job.id}>{displayDate(created.slice(0, 10)) + ' · ' + created.slice(11, 16) + ' UTC' + (typeof size === 'number' ? ' · ' + size + '° cells' : '')}</option>;
          })}{draftJobId && !successfulJobs.some(job => job.id === draftJobId) && <option value={draftJobId}>Other saved grid</option>}</select><small className="filter-help">Choose a processed grid to compare with detections. This does not correct sensor bias.</small></label>
        </div>
        <details className="technical-options"><summary>Advanced data options</summary><p className="filter-help">For imported geometries, older processing runs and verified archive coverage.</p>
          <div className="technical-fields"><label>Saved grid job ID · optional<input value={draftJobId} onChange={e => setDraftJobId(e.target.value.trim())} placeholder="Leave blank to use the latest grid" /></label>
            <label className="history-wide">GeoJSON geometry<textarea rows={3} value={geometry} onChange={e => { setGeometry(e.target.value); setBbox(''); setAreaChoice('geometry'); clearCoverage(); }} placeholder='{"type":"Polygon","coordinates":[…]}' /></label>
            <label className="history-wide">Verified complete-month declarations · JSON<textarea rows={3} value={coverage} onChange={e => setCoverage(e.target.value)} /></label>
            <p className="history-wide filter-help">Only declare months whose archive completeness you have verified for this area, sensor and confidence selection. Format: <code>{'[{"sensor_code":"MODIS_TERRA","month":"2013-01","reference":"your audit"}]'}</code>. Without declarations, monthly counts remain available, but anomaly assessments are withheld.</p>
          </div>
        </details>
      </div>}
      {formError && <p className="form-error" role="alert">{formError}</p>}{notice && <p className="form-notice" role="status">{notice}</p>}
    </form>
    <div className="workspace-status"><span><i className={`status-dot ${summary.error ? 'offline' : summary.loading ? 'waiting' : ''}`} />{summary.loading ? 'Connecting to archive' : summary.error ? 'Archive unavailable' : 'Archive connected'}</span><span>{query.start?.slice(0, 10)} — {new Date(new Date(query.end!).getTime() - 1).toISOString().slice(0, 10)} · {query.polygon ? 'Selected polygon' : 'Study envelope, not a country boundary'}</span></div>
    <SelectionOverview summary={summary} start={query.start!.slice(0, 10)} end={new Date(new Date(query.end!).getTime() - 1).toISOString().slice(0, 10)} />
    {summary.error && <div className="connection-notice" role="alert"><Info size={18} /><div><strong>Archive unavailable</strong><p>{summary.error} Try refreshing the data.</p></div></div>}
    <div className="dashboard-map-grid"><Panel id="observation-map" title="Map of recorded heat" subtitle="Select a point to see its date and source" icon={<Layers2 size={18} />}>
      <div className="map-period-controls"><label>Map period<select aria-label="Map period" value={mapMode} onChange={e => { setMapMode(e.target.value as 'all' | 'month'); setSelected(null); }}><option value="all">Entire selected period</option><option value="month">Month by month</option></select></label>{mapMode === 'month' && <div className="map-month-controls"><button type="button" className="button secondary" disabled={activeMapMonth <= firstMonth} onClick={() => moveMapMonth(-1)}>Previous month</button><label>Month<input type="month" aria-label="Map month" min={firstMonth} max={lastMonth} value={activeMapMonth} onChange={e => { if (e.target.value >= firstMonth && e.target.value <= lastMonth) { setMapMonth(e.target.value); setSelected(null); } }} /></label><button type="button" className="button secondary" disabled={activeMapMonth >= lastMonth} onClick={() => moveMapMonth(1)}>Next month</button></div>}<p>{mapMode === 'month' ? 'The map shows this month within your selected date range. Other charts and totals still cover the full selection.' : 'The map shows the entire selected date range.'}</p></div>
      <div className="map-wrap"><RegionMap data={mapObservations.data} region={draftRegion} loading={mapObservations.loading} onSelect={setSelected} />{selected && <ObservationInspector observation={selected} close={() => setSelected(null)} />}</div>{mapObservations.error && <p className="panel-message" role="alert">{mapObservations.error}</p>}<div className="map-footer"><span>Map: {formatCount(mapObservations.data?.metadata.returned)} observations{mapObservations.data?.metadata.has_more ? ' · map display is limited to 2,000' : ''}</span><span>Select a detection to view its source</span></div></Panel>
      <aside className="panel context-panel"><h2>Detections by sensor</h2><p>Counts cover the entire selected date range. Sensor resolution and overpass times affect detection counts.</p><div className="sensor-totals">{query.sensors.map(s => <div key={s}><span><i className={`dot ${s.startsWith('MODIS') ? 'modis' : 'viirs'}`} />{s.replaceAll('_', ' ')}</span><strong>{summary.data ? formatCount(summary.data.by_sensor[s] ?? 0) : '—'}</strong></div>)}</div><div className="context-warning"><ShieldCheck size={17} /><span>Counts represent satellite detections, not unique fires.</span></div><Link className="text-link" to="/methodology">View methods <ArrowRight size={14} /></Link></aside></div>
    <div className="section-divider"><div><h2>Historical analysis</h2><p>Full-year context: {historyQuery.start_year}–{historyQuery.end_year} · same area and confidence selection. Each sensor is assessed separately.</p></div>{sensorControl}<Link className="text-link" to="/history" state={{ historyQuery }}>Open detailed history <ArrowRight size={14} /></Link></div>
    <Panel title="Daily detections" subtitle="Daily counts by sensor for the selected dates and area" icon={<Activity size={18} />}><State {...summary}><ActivityChart summary={summary.data} /><p className="chart-footnote">Missing days are omitted; gaps do not mean zero fire activity.</p>{!!summary.data?.daily.length && <details className="chart-table"><summary>View daily counts as a table</summary><table><thead><tr><th>Date (UTC)</th><th>Sensor</th><th>Detections</th></tr></thead><tbody>{summary.data.daily.map(row => <tr key={`${row.day}-${row.sensor_code}`}><td>{row.day}</td><td>{row.sensor_code}</td><td>{row.count}</td></tr>)}</tbody></table></details>}</State></Panel>
    <div className="dashboard-analysis-grid"><Panel title="Monthly detections" subtitle={`${activeSensor} · year-by-month archived detections`} icon={<CalendarDays size={18} />}><State {...history} empty={!history.data?.monthly.some(r => r.count !== null)}><BurningCalendar rows={history.data?.monthly ?? []} sensor={activeSensor} selected={inspectedMonth?.month ?? ''} onSelect={setSelectedMonth} /></State></Panel>
      <Panel title="Unusual activity" subtitle="Monthly counts compared with earlier years" icon={<Activity size={18} />} action={!!rows.length && <label className="inline-select">Comparison month<select aria-label="Comparison month" value={inspectedMonth?.month ?? ''} onChange={e => setSelectedMonth(e.target.value)}>{rows.map(r => <option key={r.month} value={r.month}>{r.month}</option>)}</select></label>}><State {...history} empty={!rows.length}>{inspectedMonth && <div className="anomaly-content"><div className="anomaly-heading"><span className="eyebrow">{inspectedMonth.month} · {activeSensor}</span><span className={`assessment ${inspectedMonth.anomaly_status}`}>{inspectedMonth.anomaly_status.replaceAll('_', ' ')}</span></div><dl className="anomaly-metrics"><div><dt>Archived detections</dt><dd>{formatCount(inspectedMonth.count)}</dd></div>{inspectedMonth.comparison_series === 'validated_harmonized' && <div><dt>Harmonized comparison value</dt><dd>{formatCount(comparisonValue(inspectedMonth))}<small>{inspectedMonth.comparison_units}</small></dd></div>}<div><dt>Historical median</dt><dd>{formatCount(inspectedMonth.historical_median)}</dd></div><div><dt>Lower / upper threshold</dt><dd>{formatCount(inspectedMonth.lower_threshold)} / {formatCount(inspectedMonth.upper_threshold)}</dd></div><div><dt>Baseline period</dt><dd>{inspectedMonth.baseline_period ?? inspectedMonth.baseline_window ?? `${historyQuery.baseline_start_year}–${historyQuery.baseline_end_year}`}</dd></div><div><dt>Prior reference years</dt><dd>{inspectedMonth.baseline_size} (min {inspectedMonth.min_baseline_years ?? historyQuery.min_baseline_years})</dd></div><div><dt>Missing-data status</dt><dd>{formatMissingDataStatus(inspectedMonth.missing_data_status, inspectedMonth.completeness)}</dd></div><div><dt>Observation coverage</dt><dd>{inspectedMonth.observation_coverage ?? 'unknown'}</dd></div><div><dt>Comparison series</dt><dd>{inspectedMonth.comparison_series === 'validated_harmonized' ? 'Validated harmonized' : 'Native sensor'}</dd></div><div><dt>Robust z-score</dt><dd>{formatCount(inspectedMonth.robust_z)}</dd></div><div><dt>Year-on-year change</dt><dd>{inspectedMonth.year_over_year.percent_change === null ? 'Unavailable' : `${formatCount(inspectedMonth.year_over_year.percent_change)}%`}</dd></div></dl><p className="analysis-explanation">{inspectedMonth.anomaly_status === 'incomplete_period' ? 'Assessment withheld: month completeness is unknown. Add audited declarations in Analysis settings.' : inspectedMonth.anomaly_status === 'insufficient_history' ? `Assessment withheld: fewer than ${historyQuery.min_baseline_years} complete earlier instances of this calendar month.` : 'Compared with complete earlier instances of the same calendar month, sensor and area. Percentile flags are descriptive, not probabilities.'}</p>{inspectedMonth.missing_data_reason && <p className="chart-footnote">{inspectedMonth.missing_data_reason}</p>}{(inspectedMonth.limitations?.length || history.data?.limitations?.length) ? <details className="history-details"><summary>Comparison limitations and harmonization status</summary><ul>{(inspectedMonth.limitations ?? history.data?.limitations ?? []).map(item => <li key={item}>{item}</li>)}</ul></details> : null}<div className="assessment-summary"><strong>{flagged.length}</strong> flagged / {eligible} assessed months <small>Full historical context · selected sensor</small>{history.data && <span className="header-actions"><button type="button" className="button secondary" onClick={async () => { try { downloadArtifact(await historyCsv(history.data!), 'pirx-history.csv', 'text/csv'); } catch (e) { setFormError(e instanceof Error ? e.message : 'Export failed.'); } }}>Export CSV</button><button type="button" className="button secondary" onClick={() => downloadArtifact(JSON.stringify(history.data, null, 2), 'pirx-history-analysis.json', 'application/json')}>Export JSON</button></span>}</div></div>}</State></Panel></div>
    <div className="dashboard-chart-grid"><Panel title="Monthly trend" subtitle={`${activeSensor} · monthly observations and earlier-year reference`} icon={<Activity size={18} />}><State {...history} empty={!rows.some(r => r.count !== null)}><ScientificChart title={`${activeSensor} historical activity trend`} labels={trendLabels} series={trendSeries} metadata={{ analysis_id: history.data?.analysis_id, query: history.data?.query, sources: history.data?.sources }} /><p className="chart-footnote">Gaps remain unknown. Positive counts may be incomplete. Reference thresholds require audited complete months.</p></State></Panel>
      <Panel title="Detections and grid counts" subtitle="Saved grid counts; sensor bias is uncorrected" icon={<Layers2 size={18} />}><State loading={jobs.loading || comparison.loading} error={jobs.error || comparison.error} empty={!comparison.data?.daily.length} message={jobId ? 'The saved job has no full days and grid cells within this selection.' : 'No saved grid counts are available. Choose a processing job in Analysis settings or create one with the data pipeline.'}><ScientificChart title="Matched raw and common-grid counts by sensor" kind="bar" labels={comparisonSensors} series={comparisonSeries} metadata={comparison.data} />{comparison.data && <div className="comparison-context"><p>{comparison.data.scope}</p><p>{comparison.data.method}</p>{comparison.data.archive_counts_match === false && <p className="form-error">Counts differ from the saved snapshot. Inspect job provenance before interpreting changes.</p>}<details><summary>Processing details</summary><pre>{JSON.stringify({ job_id: comparison.data.job_id, algorithm_version: comparison.data.algorithm_version, parameters: comparison.data.parameters, provenance: comparison.data.provenance }, null, 2)}</pre></details></div>}</State></Panel></div>
    <Panel title="Sources and limitations" subtitle="Source files and assumptions used in the historical analysis" icon={<ShieldCheck size={18} />}><State {...history} empty={!history.data?.sources.length} message="No source files are associated with the full-year historical selection."><div className="provenance-intro"><p>Full-year historical context · <strong>{history.data?.sources.length} source files</strong>. Source checksums identify archived content. They do not establish authenticity or complete observation coverage.</p><Link className="text-link" to="/sources">View all source files <ArrowRight size={14} /></Link></div><div className="table-scroll provenance-table"><table><thead><tr><th>Original file</th><th>Sensor / product</th><th>Source SHA-256</th><th>Retrieved (UTC)</th></tr></thead><tbody>{history.data?.sources.slice(0, 5).map(s => <tr key={s.id}><td><span>{s.original_filename ?? s.id}</span></td><td>{s.sensor_code ?? 'See source'}<small>{s.product_version} · {s.processing_level}</small></td><td><code title={s.sha256}>{s.sha256.slice(0, 16)}…</code></td><td>{s.retrieved_at ?? 'Not recorded'}</td></tr>)}</tbody></table></div>{(history.data?.sources.length ?? 0) > 5 && <p className="chart-footnote">Showing five files. View all source files for more detail.</p>}<div className="uncertainty-grid"><div><h3>Observation uncertainty</h3><p>Native confidence is not a cross-sensor probability. Cloud cover, overpass timing, product revisions and sensor sensitivity affect detections. Select a map observation for its exact uncertainty metadata.</p></div><div><h3>Historical reference</h3><p>{history.data?.metric_explanations.baseline}</p></div><div><h3>Coverage & interpretation</h3><p>{history.data?.metric_explanations.coverage}</p></div></div><details className="history-details"><summary>Metric definitions and analysis ID</summary><p className="hash">{history.data?.analysis_id}</p>{Object.entries(history.data?.metric_explanations ?? {}).map(([name, description]) => <p key={name}><strong>{name.replaceAll('_', ' ')}:</strong> {description}</p>)}</details></State></Panel>
    <AIIntelligencePanel context={historyQuery} dateWindow={{ start_date: query.start!.slice(0, 10), end_date: new Date(new Date(query.end!).getTime() - 1).toISOString().slice(0, 10) }} />
    <div className="science-note"><Info size={16} /><p>Thermal detections are not unique fires, burned area or forecasts. The calendar and historical charts use complete-year context; map totals respect the exact date filters. Common-grid comparisons use their disclosed matched scope.</p></div>
  </div>;
}
