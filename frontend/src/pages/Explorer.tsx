import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { ArrowDownToLine, ArrowRight, Database, Flame, Globe2, Info, Layers2, RefreshCw, SlidersHorizontal } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api, inclusiveEndDate } from '../api';
import FireMap from '../components/FireMap';
import ActivityChart from '../components/ActivityChart';
import ObservationInspector from '../components/ObservationInspector';
import { sensorCodes } from '../types';
import type { ObservationProperties, Observations, Query, Summary } from '../types';

const initialQuery: Query = { sensors: [], limit: 2000 };
const format = (value: number | undefined) => value === undefined ? '—' : value.toLocaleString();

export default function Explorer() {
  const [query, setQuery] = useState<Query>(initialQuery);
  const [data, setData] = useState<Observations | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [instrument, setInstrument] = useState('all');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [bbox, setBbox] = useState('');
  const [polygon, setPolygon] = useState('');
  const [confidence, setConfidence] = useState('');
  const [advanced, setAdvanced] = useState(false);
  const [formError, setFormError] = useState('');
  const [selected, setSelected] = useState<ObservationProperties | null>(null);
  const filtersRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setBusy(true); setError(''); setData(null); setSummary(null); setSelected(null);
    Promise.all([api.observations(query, controller.signal), api.summary(query, controller.signal)])
      .then(([observations, stats]) => { if (!controller.signal.aborted) { setData(observations); setSummary(stats); } })
      .catch(e => { if (!controller.signal.aborted) setError(e.message); })
      .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [query, refresh]);

  function apply(event: FormEvent) {
    event.preventDefault(); setFormError('');
    try {
      if (start && end && start > end) throw new Error('Start date must precede the end date.');
      let bounds: Query['bbox'];
      if (bbox.trim()) {
        const parts = bbox.split(',').map(x => x.trim());
        const numbers = parts.map(Number);
        if (parts.some(x => !x) || numbers.length !== 4 || numbers.some(x => !Number.isFinite(x))) throw new Error('Enter four bounds: west, south, east, north.');
        bounds = numbers as Query['bbox'];
      }
      const geometry = polygon.trim() ? JSON.parse(polygon) : undefined;
      if (geometry && !['Polygon', 'MultiPolygon'].includes(geometry.type)) throw new Error('Paste a GeoJSON Polygon or MultiPolygon geometry.');
      setQuery({
        sensors: instrument === 'all' ? [] : sensorCodes.filter(x => x.startsWith(instrument)),
        start: start ? `${start}T00:00:00Z` : undefined, end: inclusiveEndDate(end),
        bbox: bounds, polygon: geometry, confidence: confidence ? confidence as Query['confidence'] : undefined,
        limit: 2000,
      });
    } catch (e) { setFormError(e instanceof Error ? e.message : 'Check your filters.'); }
  }

  function exportData() {
    if (!data) return;
    const payload = { ...data, metadata: { ...data.metadata, query, exported_at: new Date().toISOString(), science_note: 'Unadjusted thermal detections. Not burned area. Export includes displayed page only.' } };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/geo+json' }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'firescope-observations.geojson'; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const modis = Object.entries(summary?.by_sensor ?? {}).filter(([s]) => s.startsWith('MODIS')).reduce((sum, [, n]) => sum + n, 0);
  const viirs = Object.entries(summary?.by_sensor ?? {}).filter(([s]) => s.startsWith('VIIRS')).reduce((sum, [, n]) => sum + n, 0);

  return <>
    <header className="page-header"><div><div className="eyebrow">THE BIG PICTURE, WITH EVERY DETAIL</div><h1>Fire intelligence explorer<span>.</span></h1><p>Two sensor families. One transparent view of our changing planet.</p></div><button className="button secondary export" onClick={exportData} disabled={!data?.features.length}><ArrowDownToLine size={15} /> Export GeoJSON</button></header>
    <div className="workspace-status"><span><i className={`status-dot ${error ? 'offline' : busy ? 'waiting' : ''}`} />{busy ? 'Connecting to your archive' : error ? 'Archive disconnected' : 'Archive connected'}</span><span>Historical observations <b>·</b> All times UTC</span></div>
    <section className="metrics" aria-label="Observation summary">
      <article className="metric"><div className="metric-label">Total detections <span className="metric-icon orange"><Flame size={17} /></span></div><strong>{format(summary?.detection_count)}</strong><small>Unadjusted observation count</small></article>
      <article className="metric"><div className="metric-label">MODIS observations <span className="metric-icon amber"><Layers2 size={17} /></span></div><strong>{summary ? format(modis) : '—'}</strong><small><i className="dot modis" /> Terra & Aqua · 1 km nominal</small></article>
      <article className="metric"><div className="metric-label">VIIRS observations <span className="metric-icon violet"><Globe2 size={17} /></span></div><strong>{summary ? format(viirs) : '—'}</strong><small><i className="dot viirs" /> S-NPP & NOAA · 375 m nominal</small></article>
      <article className="metric"><div className="metric-label">Source files <span className="metric-icon green"><Database size={17} /></span></div><strong>{format(summary?.source_count)}</strong><small>Original files, traceable by SHA-256</small></article>
    </section>
    <section className="panel explorer-panel">
      <div className="panel-heading"><div><h2>Explore observations <span className="pill">MODIS + VIIRS</span></h2><p>Filter the archive by location, date and sensor.</p></div><button className={`icon-button ${advanced ? 'active' : ''}`} aria-label="Toggle spatial and confidence filters" aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}><SlidersHorizontal size={18} /></button></div>
      <div ref={filtersRef}><form onSubmit={apply} className="filter-form">
        <div className="primary-filters"><label>Sensor family<select value={instrument} onChange={e => setInstrument(e.target.value)}><option value="all">All sensors</option><option value="MODIS">MODIS</option><option value="VIIRS">VIIRS</option></select></label><label>Start date<input aria-label="Start date" type="date" value={start} onChange={e => setStart(e.target.value)} /></label><span className="date-arrow">→</span><label>End date (inclusive)<input aria-label="End date" type="date" value={end} onChange={e => setEnd(e.target.value)} /></label><div className="filter-region"><Globe2 size={15} /><span>{query.polygon ? 'Polygon region' : query.bbox ? 'Bounding box' : 'Global extent'}</span></div><button className="button primary" type="submit" disabled={busy}>Apply filters <ArrowRight size={14} /></button></div>
        {advanced && <div className="advanced-filters"><label>Bounding box · west, south, east, north<input value={bbox} onChange={e => setBbox(e.target.value)} placeholder="e.g. 34, 29, 40, 34" /></label><label>Native confidence class<select value={confidence} onChange={e => setConfidence(e.target.value)}><option value="">All confidence classes</option><option value="low">Low</option><option value="nominal">Nominal</option><option value="high">High</option></select></label><label className="polygon-input">GeoJSON Polygon / MultiPolygon geometry<textarea value={polygon} onChange={e => setPolygon(e.target.value)} rows={3} placeholder='{"type":"Polygon","coordinates":[...]}' /></label><small>WGS84 longitude, latitude. Bounds and polygons intersect when both are supplied. Split polygons at the antimeridian.</small></div>}
        {formError && <p role="alert" className="form-error">{formError}</p>}
      </form></div>
      <div className="map-wrap"><FireMap data={data} onBounds={bounds => { setBbox(bounds.map(v => v.toFixed(5)).join(', ')); setAdvanced(true); filtersRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }} onSelect={setSelected} />{selected && <ObservationInspector observation={selected} close={() => setSelected(null)} />}</div>
      <div className="map-footer"><span><i className="status-dot waiting" />{busy ? 'Loading observations…' : data ? `${format(data.metadata.returned)} displayed${data.metadata.has_more ? ' · result capped at 2,000; narrow filters for more detail' : ''}` : 'Waiting for archive connection'}</span><span>WGS84 / EPSG:4326</span></div>
    </section>
    {error && <div className="connection-notice" role="alert"><Info size={18} /><div><strong>Your exploration starts with a connected archive</strong><p>{error}</p></div><button className="button secondary" onClick={() => setRefresh(n => n + 1)}><RefreshCw size={14} /> Retry</button></div>}
    {!busy && summary?.detection_count === 0 && <div className="connection-notice"><Database size={18} /><div><strong>No observations match this view</strong><p>Import a real NASA FIRMS CSV using the documented pipeline, or broaden your filters.</p></div><Link className="text-link" to="/sources">View data sources <ArrowRight size={14} /></Link></div>}
    <div className="lower-grid"><section className="panel activity-panel"><div className="panel-heading"><div><h2>Activity over time</h2><p>Daily detections, separated by sensor</p></div><span className="subtle-tag">UTC · DAILY</span></div><ActivityChart summary={summary} /><div className="chart-footnote">Missing days are omitted; gaps do not mean zero fire activity.</div>{!!summary?.daily.length && <details className="chart-table"><summary>View daily counts as a table</summary><table><thead><tr><th>Date (UTC)</th><th>Sensor</th><th>Detections</th></tr></thead><tbody>{summary.daily.map(row => <tr key={`${row.day}-${row.sensor_code}`}><td>{row.day}</td><td>{row.sensor_code}</td><td>{row.count}</td></tr>)}</tbody></table></details>}</section><section className="panel science-card"><div className="science-icon"><Layers2 size={21} /></div><span className="eyebrow">UNDERSTAND THE SIGNAL</span><h2>Different sensors.<br />Shared perspective.</h2><p>MODIS and VIIRS see fire differently. Explore them together while keeping their resolution, confidence and source context intact.</p><Link to="/methodology" className="text-link">How harmonization works <ArrowRight size={15} /></Link></section></div>
    <div className="science-note"><Info size={15} /><p>Thermal detections are not unique fire events or burned area. Sensor coverage and bias are not corrected in this foundation. Forecasts and anomaly detection are not enabled.</p></div>
  </>;
}
