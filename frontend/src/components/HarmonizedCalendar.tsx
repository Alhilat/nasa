import { useMemo, useState } from 'react';
import type { HistoryResult } from '../history';
import { downloadArtifact } from '../history';
import { formatCount } from '../dashboard';
import { harmonizedCalendarCsv } from '../calendar';
import { visualTheme as theme } from '../visualTheme';
import BurningCalendar from './BurningCalendar';
import ScientificChart from './ScientificChart';

type View = 'Harmonized' | 'MODIS' | 'VIIRS';
export default function HarmonizedCalendar({ result, sensor, selected, onSelect }: {
  result: HistoryResult; sensor: string; selected: string; onSelect: (month: string) => void;
}) {
  const [view, setView] = useState<View>('Harmonized');
  const [nativeChoice, setNativeChoice] = useState('');
  const [colorMode, setColorMode] = useState<'activity' | 'median'>('activity');
  const calendar = result.harmonized_calendar;
  const nativeSensors = result.query.sensors.filter(s => s.startsWith(view));
  const preferredSensor = view === 'MODIS' ? calendar?.reference_sensor : calendar?.source_sensor;
  const nativeSensor = nativeSensors.includes(nativeChoice) ? nativeChoice
    : preferredSensor && nativeSensors.includes(preferredSensor) ? preferredSensor : nativeSensors[0];
  const unified = view === 'Harmonized';
  const displaySensor = unified ? 'Harmonized' : nativeSensor ?? view;
  const rows = useMemo(() => unified ? (calendar?.monthly ?? []).map(r => ({
    sensor_code: 'Harmonized', month: r.month, count: r.value, comparison_value: r.value,
    completeness: r.completeness, anomaly_status: r.validation_status,
    median_comparison: r.median_comparison,
    details: `${r.origin.replaceAll('_', ' ')}; ${r.reason}; ${r.lower_95 === null ? r.uncertainty_reason : `95% parameter interval ${r.lower_95} to ${r.upper_95}`}`,
  })) : result.monthly.filter(r => r.sensor_code === nativeSensor).map(r => ({
    ...r, comparison_series: 'native_sensor', comparison_value: r.count,
  })), [unified, calendar, result.monthly, nativeSensor]);
  const labels = useMemo(() => rows.map(r => r.month), [rows]);
  const hasMappedOverlap = Boolean(
    unified && calendar?.monthly.some(r => r.origin === 'modis_reference' && r.mapped_value != null)
  );
  const series = useMemo(() => [
    { name: unified ? calendar?.units ?? 'MODIS-equivalent detections' : `${displaySensor} archived detections`,
      values: rows.map(r => r.count), color: theme.orange },
    ...(hasMappedOverlap ? [{
      name: `Mapped ${calendar?.source_sensor ?? 'VIIRS'} (${calendar?.model?.method.replaceAll('_', ' ') ?? 'calibrated'})`,
      values: calendar?.monthly.map(r => r.mapped_value ?? (r.origin === 'mapped_viirs' ? r.value : null)) ?? [],
      color: theme.viirs,
    }] : []),
    ...(unified ? [
      { name: '95% parameter lower', values: calendar?.monthly.map(r => r.lower_95 ?? r.mapped_lower_95 ?? null) ?? [], color: theme.reference, dashed: true },
      { name: '95% parameter upper', values: calendar?.monthly.map(r => r.upper_95 ?? r.mapped_upper_95 ?? null) ?? [], color: theme.reference, dashed: true },
    ] : []),
  ], [rows, unified, hasMappedOverlap, calendar, displaySensor]);
  const band = useMemo(() => unified && calendar ? {
    lower: calendar.monthly.map(r => r.lower_95 ?? r.mapped_lower_95 ?? null),
    upper: calendar.monthly.map(r => r.upper_95 ?? r.mapped_upper_95 ?? null),
    color: theme.reference,
  } : undefined, [unified, calendar]);
  const inspected = calendar?.monthly.find(r => r.month === selected)
    ?? [...calendar?.monthly ?? []].reverse().find(r => r.value !== null);
  // Older server/fixture responses retain the existing native calendar.
  if (!calendar) return <BurningCalendar rows={result.monthly} sensor={sensor} selected={selected} onSelect={onSelect} />;

  function exportCalendar() {
    if (!calendar) return;
    downloadArtifact(harmonizedCalendarCsv(result), 'pirx-harmonized-calendar.csv', 'text/csv');
  }

  return <div className="harmonized-calendar">
    <div className="calendar-controls"><div role="group" aria-label="Calendar series" className="calendar-toggle">
      {(['Harmonized', 'MODIS', 'VIIRS'] as const).map(item => <button key={item} type="button" aria-pressed={view === item} onClick={() => { setView(item); setNativeChoice(''); }}>{item}</button>)}
    </div>{!unified && nativeSensors.length > 1 && <label>Calendar satellite<select aria-label="Calendar satellite" value={nativeSensor} onChange={e => setNativeChoice(e.target.value)}>{nativeSensors.map(s => <option key={s}>{s}</option>)}</select></label>}
      {unified && <span className={`calibration-status ${calendar.status}`}>{calendar.status === 'validated' ? 'Validated' : calendar.status === 'experimental' ? 'Experimental' : 'Unavailable'}</span>}
      <label className="calendar-color-control">Calendar colors<select aria-label="Calendar colors" value={colorMode} onChange={e => setColorMode(e.target.value as 'activity' | 'median')}><option value="activity">Activity intensity</option><option value="median">Departure from historical median</option></select></label>
    </div>
    <p className="chart-footnote">{unified ? `${calendar.units}. ${calendar.reason}` : `${displaySensor} · native archived counts; sensors are shown separately.`}</p>
    {!rows.length ? <p className="chart-footnote">No {view} sensor is selected. Include it in the analysis filters.</p> : <BurningCalendar rows={rows} sensor={displaySensor} selected={selected} onSelect={onSelect} valueLabel={unified ? calendar.units : 'Archived detections'} colorMode={colorMode} footnote="Select a month for context. Color shows relative activity within this view, not fire risk. * Archive completeness unknown." />}
    {unified && inspected && <div className="calendar-inspection" aria-label="Harmonized month details">
      <strong>{inspected.month} · {formatCount(inspected.value)} {calendar.units}</strong>
      <span>{inspected.origin === 'modis_reference' ? 'Native MODIS reference' : inspected.validation_status} · {inspected.sensor_code ?? 'No sensor'}</span>
      <p>{inspected.reason}</p><p>{inspected.lower_95 === null ? inspected.uncertainty_reason : `95% parameter interval: ${formatCount(inspected.lower_95)}–${formatCount(inspected.upper_95)}.`}</p>
      {inspected.origin === 'modis_reference' && inspected.mapped_value != null && <p>Mapped {calendar.source_sensor ?? 'VIIRS'} estimate: {formatCount(inspected.mapped_value)} {calendar.units}{inspected.mapped_lower_95 != null && inspected.mapped_upper_95 != null ? ` (95% parameter interval: ${formatCount(inspected.mapped_lower_95)}–${formatCount(inspected.mapped_upper_95)})` : ''}{inspected.mapped_extrapolated ? ' · outside training support' : ''}.</p>}
      {colorMode === 'median' && <><p>{inspected.median_comparison?.reason ?? 'Historical median context is unavailable.'}</p>{inspected.median_comparison?.status === 'assessed' && <p>Prior median: {formatCount(inspected.median_comparison.historical_median)} · departure: {formatCount(inspected.median_comparison.departure)} · reference years: {inspected.median_comparison.baseline_years.join(', ')}.</p>}</>}
    </div>}
    <ScientificChart title={`${displaySensor} calendar trend`} labels={labels} series={series} band={band} metadata={{ analysis_id: result.analysis_id, query: result.query, calendar: unified ? calendar : undefined, sources: result.sources }} />
    {unified && <><p className="chart-footnote">Shading shows 95% fitted-parameter uncertainty where available. Native reference observations and values outside training support have no band. These are not prediction intervals.</p>
      <button className="button secondary calendar-download" type="button" onClick={exportCalendar}>Export harmonized calendar CSV</button>
      <details className="history-details"><summary>Calibration method, validation and limitations</summary><p>{calendar.selection_policy}</p><p>{calendar.uncertainty_method}</p>{calendar.model && <p>{calendar.model.method.replaceAll('_', ' ')} · model <code>{calendar.model.model_version}</code> · {calendar.model.approval.replaceAll('_', ' ')} · {calendar.model.bootstrap_successes} successful bootstrap fits</p>}{calendar.candidates.map(c => <p key={c.method}>{c.method.replaceAll('_', ' ')}: {c.validation_mae === null ? c.reason : `latest-year selection MAE ${formatCount(c.validation_mae)}`}</p>)}<ul>{calendar.limitations.map(l => <li key={l}>{l}</li>)}</ul></details></>}
  </div>;
}
