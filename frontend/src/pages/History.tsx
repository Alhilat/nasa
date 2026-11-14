import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { useLocation } from 'react-router-dom';
import { sensorCodes } from '../types';
import { historyRequest } from '../history';
import type { HistoryQuery, HistoryResult } from '../history';
import HistoryTrend from '../components/HistoryTrend';

const display = (value: number | null) => value === null ? 'Unknown' : value.toLocaleString(undefined, { maximumFractionDigits: 2 });

export default function History() {
  const selected = (useLocation().state as { historyQuery?: HistoryQuery } | null)?.historyQuery;
  const [start, setStart] = useState(selected?.start_year ?? 2013), [end, setEnd] = useState(selected?.end_year ?? 2025);
  const [baselineStart, setBaselineStart] = useState(selected?.baseline_start_year ?? 2013), [baselineEnd, setBaselineEnd] = useState(selected?.baseline_end_year ?? 2024);
  const [bbox, setBbox] = useState(selected?.bbox?.join(',') ?? (selected ? '' : '34,29,40,34')), [polygon, setPolygon] = useState(selected?.polygon ? JSON.stringify(selected.polygon) : '');
  const [sensor, setSensor] = useState<string>(selected?.sensors[0] ?? sensorCodes[0]);
  const [confidence, setConfidence] = useState(selected?.confidence ?? '');
  const [percentile, setPercentile] = useState(selected?.percentile ?? 95), [minimum, setMinimum] = useState(selected?.min_baseline_years ?? 5);
  const [grid, setGrid] = useState(selected?.grid_size_deg ?? 1), [coverage, setCoverage] = useState(JSON.stringify(selected?.complete_months ?? []));
  const [result, setResult] = useState<HistoryResult | null>(null);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  async function run(event: FormEvent) {
    event.preventDefault(); controller.current?.abort();
    const current = new AbortController(); controller.current = current;
    setError(''); setResult(null); setBusy(true);
    try {
      const parts = bbox.split(',').map(v => v.trim());
      if (bbox.trim() && (parts.length !== 4 || parts.some(v => !v || !Number.isFinite(Number(v)))))
        throw new Error('Supply four finite bounds: west,south,east,north.');
      const query: HistoryQuery = {
        start_year: start, end_year: end, baseline_start_year: baselineStart, baseline_end_year: baselineEnd,
        bbox: bbox.trim() ? parts.map(Number) : undefined,
        polygon: polygon.trim() ? JSON.parse(polygon) : undefined,
        sensors: [sensor], confidence: confidence || undefined,
        percentile, min_baseline_years: minimum, grid_size_deg: grid, complete_months: JSON.parse(coverage),
      };
      const data = await historyRequest(query, current.signal);
      if (!current.signal.aborted) setResult(data);
    } catch (e) { if (!current.signal.aborted) setError(e instanceof Error ? e.message : 'Analysis failed.'); }
    finally { if (!current.signal.aborted) setBusy(false); }
  }

  const selectedSensor = result?.query.sensors[0] ?? sensor;
  return <>
    <header className="page-header"><div><h1>Historical analysis</h1><p>Compare monthly and yearly detections for one sensor and area.</p></div></header>
    <section className="panel prose-panel"><h2>Analysis filters</h2>
      <form className="history-form" onSubmit={run}>
        <label>Sensor<select value={sensor} onChange={e => setSensor(e.target.value)}>{sensorCodes.map(s => <option key={s}>{s}</option>)}</select></label>
        <label>First year<input type="number" min="1900" max="2099" required value={start} onChange={e => setStart(Number(e.target.value))} /></label>
        <label>Last year<input type="number" min="1900" max="2099" required value={end} onChange={e => setEnd(Number(e.target.value))} /></label>
        <details className="history-wide advanced-history"><summary>Advanced analysis settings</summary><div className="history-form">
        <label>Baseline first year<input type="number" required value={baselineStart} onChange={e => setBaselineStart(Number(e.target.value))} /></label>
        <label>Baseline last year<input type="number" required value={baselineEnd} onChange={e => setBaselineEnd(Number(e.target.value))} /></label>
        <label>Upper percentile<input type="number" min="50" max="99.99" step="0.01" required value={percentile} onChange={e => setPercentile(Number(e.target.value))} /></label>
        <label>Minimum reference years<input type="number" min="3" max="30" required value={minimum} onChange={e => setMinimum(Number(e.target.value))} /></label>
        <label>Angular cell size<select value={grid} onChange={e => setGrid(Number(e.target.value))}>{[0.25, 0.5, 1, 2, 5].map(v => <option key={v} value={v}>{v}°</option>)}</select></label>
        <label>Confidence<select value={confidence} onChange={e => setConfidence(e.target.value)}><option value="">All</option>{['low', 'nominal', 'high'].map(v => <option key={v}>{v}</option>)}</select></label>
        <label className="history-wide">Fixed bounding box · west,south,east,north<input value={bbox} onChange={e => setBbox(e.target.value)} /></label>
        <label className="history-wide">Optional GeoJSON Polygon / MultiPolygon<textarea rows={3} value={polygon} onChange={e => setPolygon(e.target.value)} /></label>
        <label className="history-wide">Complete-month declarations (JSON)<textarea rows={4} value={coverage} onChange={e => setCoverage(e.target.value)} /></label>
        <p className="history-wide">Only declare months whose archive completeness you have audited for this exact area, sensor and confidence selection. Example: <code>{'[{"sensor_code":"MODIS_TERRA","month":"2013-01","reference":"your coverage audit"}]'}</code>. Without declarations, observed counts remain available; comparisons and anomaly decisions are withheld. Empty months remain unknown. Bounding boxes and polygons intersect when both are supplied.</p>
        </div></details>
        <button className="button primary" disabled={busy}>{busy ? 'Analyzing…' : 'Analyze archive'}</button>
      </form>
    </section>
    {error && <p className="connection-notice" role="alert">{error}</p>}
    {result && <>
      <div className="history-actions"><span>{result.sources.length} source files · {result.algorithm_version}</span></div>
      <section className="panel history-panel"><div className="panel-heading"><div><h2>Historical trend · {selectedSensor}</h2><p>Monthly detections for the selected sensor.</p></div></div><HistoryTrend result={result} sensor={selectedSensor} /><p className="chart-footnote">Unknown months break the line. Archived counts can be incomplete; thresholds use complete earlier years only.</p></section>
      <section className="panel history-panel"><div className="panel-heading"><h2>Monthly activity calendar and anomalies</h2></div><div className="table-scroll history-months"><table><thead><tr><th>Month</th><th>Detections</th><th>Completeness</th><th>Prior median</th><th>Reference years</th><th>Lower / upper</th><th>Anomaly</th><th>Year-on-year %</th></tr></thead><tbody>{result.monthly.map(r => <tr key={r.month}><td>{r.month}</td><td>{display(r.count)}</td><td>{r.completeness}</td><td>{display(r.historical_median)}</td><td>{r.baseline_size}</td><td>{display(r.lower_threshold)} / {display(r.upper_threshold)}</td><td>{r.anomaly_status.replaceAll('_', ' ')}</td><td>{display(r.year_over_year.percent_change)}</td></tr>)}</tbody></table></div></section>
      <section className="panel history-panel"><div className="panel-heading"><h2>Yearly activity calendar</h2></div><div className="table-scroll"><table><thead><tr><th>Year</th><th>Complete-year count</th><th>Observed archive total</th><th>Complete months</th><th>Matched months for YoY</th><th>Matched-month change %</th></tr></thead><tbody>{result.yearly.map(r => <tr key={r.year}><td>{r.year}</td><td>{display(r.count)}</td><td>{display(r.observed_count)}</td><td>{r.complete_months.length}/12</td><td>{r.year_over_year.matched_months.join(', ') || 'None'}</td><td>{display(r.year_over_year.percent_change)}</td></tr>)}</tbody></table></div></section>
      <section className="panel history-panel"><div className="panel-heading"><h2>Seasonal profile · complete baseline months</h2></div><div className="table-scroll"><table><thead><tr><th>Calendar month</th><th>Median detections</th><th>Reference years</th></tr></thead><tbody>{result.seasonal_profiles.map(r => <tr key={r.calendar_month}><td>{r.calendar_month}</td><td>{display(r.median)}</td><td>{r.sample_size}</td></tr>)}</tbody></table></div></section>
      <section className="panel history-panel"><div className="panel-heading"><div><h2>Spatial hotspot concentration</h2><p>Fixed angular cells · detection shares, without exposure or physical-area correction</p></div></div><div className="table-scroll"><table><thead><tr><th>Sensor</th><th>Occupied cells</th><th>Concentration index (0–1)</th><th>Top 10 cells share</th></tr></thead><tbody>{result.concentration.map(r => <tr key={r.sensor_code}><td>{r.sensor_code}</td><td>{r.occupied_cells}</td><td>{display(r.herfindahl_index)}</td><td>{display(r.top_10_cells_share)}</td></tr>)}</tbody></table></div><details className="history-details"><summary>View occupied grid cells</summary><div className="table-scroll history-months"><table><thead><tr><th>Grid X / Y</th><th>Detections</th><th>Share</th></tr></thead><tbody>{result.spatial.features.map(f => <tr key={`${f.properties.grid_x}-${f.properties.grid_y}`}><td>{f.properties.grid_x} / {f.properties.grid_y}</td><td>{f.properties.count}</td><td>{display(f.properties.share)}</td></tr>)}</tbody></table></div></details></section>
      <section className="panel prose-panel"><h2>How to interpret these metrics</h2>{Object.entries(result.metric_explanations).map(([key, value]) => <div key={key}><h3>{key.replaceAll('_', ' ')}</h3><p>{value}</p></div>)}<p className="hash">Analysis ID: {result.analysis_id}</p></section>
    </>}
  </>;
}
