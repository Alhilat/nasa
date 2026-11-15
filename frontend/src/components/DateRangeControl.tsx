import type { CSSProperties } from 'react';

const day = 86400000;
const timestamp = (date: string) => Date.parse(`${date}T00:00:00Z`);
export const displayDate = (date: string) => new Date(timestamp(date)).toLocaleDateString(undefined, {
  day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
});

export default function DateRangeControl({ first, last, start, end, onChange, archiveDatesKnown = true }: {
  first: string; last: string; start: string; end: string;
  onChange: (start: string, end: string) => void;
  archiveDatesKnown?: boolean;
}) {
  const origin = timestamp(first), total = Math.round((timestamp(last) - origin) / day);
  const offset = (date: string) => Math.round((timestamp(date) - origin) / day);
  const dateAt = (index: number) => new Date(origin + index * day).toISOString().slice(0, 10);
  const startOffset = offset(start || first), endOffset = offset(end || last);
  function recent(years: number) {
    const date = new Date(timestamp(last) + day);
    date.setUTCFullYear(date.getUTCFullYear() - years);
    return date.toISOString().slice(0, 10) < first ? first : date.toISOString().slice(0, 10);
  }
  const presets = [
    { label: 'All dates', start: first },
    { label: 'Latest 12 months', start: recent(1) },
    { label: 'Latest 5 years', start: recent(5) },
  ];
  return <fieldset className="date-range-control">
    <legend>Date range</legend>
    <p className="filter-help">{archiveDatesKnown ? 'Available data' : 'Original filter bounds'} · {displayDate(first)} – {displayDate(last)} · UTC</p>
    <div className="date-presets" aria-label="Date presets">{presets.map((preset, i) => <button
      key={preset.label} type="button" className="filter-chip"
      disabled={i > 0 && preset.start === first}
      aria-pressed={start === preset.start && end === last && (i === 0 || preset.start !== first)}
      onClick={() => onChange(preset.start, last)}>{preset.label}</button>)}</div>
    <div className="date-inputs">
      <label>Start date<input type="date" required min={first} max={end || last} value={start}
        onChange={event => onChange(event.target.value, end)} /></label>
      <span aria-hidden="true">→</span>
      <label>End date<input type="date" required min={start || first} max={last} value={end}
        onChange={event => onChange(start, event.target.value)} /></label>
    </div>
    <div className="date-slider" style={{ '--range-start': `${total ? startOffset / total * 100 : 0}%`, '--range-end': `${total ? endOffset / total * 100 : 100}%` } as CSSProperties}>
      <span className="date-slider-track" aria-hidden="true" />
      <input type="range" aria-label="Range start date" aria-valuetext={displayDate(start || first)}
        min={0} max={total} value={startOffset} disabled={total === 0}
        onChange={event => onChange(dateAt(Math.min(Number(event.target.value), endOffset)), end || last)} />
      <input type="range" aria-label="Range end date" aria-valuetext={displayDate(end || last)}
        min={0} max={total} value={endOffset} disabled={total === 0}
        onChange={event => onChange(start || first, dateAt(Math.max(Number(event.target.value), startOffset)))} />
    </div>
    <div className="range-endpoints"><span>{displayDate(first)}</span><span>{displayDate(last)}</span></div>
  </fieldset>;
}
