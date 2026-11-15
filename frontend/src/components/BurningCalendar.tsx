import { comparisonLabel, comparisonValue } from '../history';
import type { HistoryMonth } from '../history';
import { formatCount } from '../dashboard';
import { activityColor, departureColor, readableText, scientificColors } from '../colorScales';
import type { MedianComparison } from '../calendar.types';

const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
type CalendarRow = Pick<HistoryMonth, 'sensor_code' | 'month' | 'count' | 'completeness' | 'anomaly_status' | 'comparison_series' | 'comparison_value'> & { details?: string; median_comparison?: MedianComparison };
export default function BurningCalendar({ rows, sensor, selected, onSelect, valueLabel, footnote, colorMode = 'activity' }: {
  rows: CalendarRow[]; sensor: string; selected: string; onSelect: (month: string) => void;
  valueLabel?: string; footnote?: string;
  colorMode?: 'activity' | 'median';
}) {
  const data = rows.filter(r => r.sensor_code === sensor);
  const years = [...new Set(data.map(r => r.month.slice(0, 4)))];
  const index = new Map(data.map(r => [r.month, r]));
  const maximum = Math.max(1, ...data.map(r => comparisonValue(r) ?? 0));
  const maximumDeparture = Math.max(0, ...data.map(r => Math.abs(r.median_comparison?.departure ?? 0)));
  const medianMode = colorMode === 'median';
  const signed = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${formatCount(Math.abs(v))}`;
  return <><div className="calendar-scroll"><table className="burning-calendar"><caption className="sr-only">Year-by-month thermal detections for {sensor}. Unknown completeness is not an anomaly decision.</caption><thead><tr><th scope="col">Year</th>{months.map(m => <th key={m} scope="col">{m}</th>)}</tr></thead><tbody>{years.map(y => <tr key={y}><th scope="row">{y}</th>{months.map((m, i) => {
    const label = `${y}-${String(i + 1).padStart(2, '0')}`, row = index.get(label);
    const value = row ? comparisonValue(row) : null;
    const assessment = row?.median_comparison;
    const departure = assessment?.status === 'assessed' ? assessment.departure : null;
    const unknown = medianMode ? departure === null : value === null;
    const background = unknown ? scientificColors.unknown.background : medianMode
      ? departureColor(departure!, maximumDeparture) : activityColor(value!, maximum);
    const explanation = `${label}, ${sensor}: ${value === null ? 'unknown' : `${formatCount(value)} ${(valueLabel ?? comparisonLabel(data)).toLowerCase()}`}; completeness ${row?.completeness ?? 'unknown'}; ${row?.anomaly_status.replaceAll('_', ' ') ?? 'not assessed'}${row?.details ? `; ${row.details}` : ''}${medianMode ? `; ${departure === null ? `median departure unassessed: ${assessment?.reason ?? 'No eligible historical baseline'}` : `${signed(departure)} from historical median ${formatCount(assessment?.historical_median)}; ${assessment?.baseline_size} prior reference years (${assessment?.baseline_years.join(', ')})`}` : ''}`;
    return <td key={m}><button type="button" className={`calendar-cell ${unknown ? 'missing' : ''} ${selected === label ? 'selected' : ''}`} style={{ backgroundColor: background, color: unknown ? scientificColors.unknown.foreground : readableText(background) }} aria-label={explanation} aria-pressed={selected === label} title={explanation} onClick={() => onSelect(label)}>{unknown ? '—' : medianMode ? signed(departure!) : formatCount(value)}{!medianMode && row?.completeness !== 'complete' && value !== null && <span aria-hidden="true">*</span>}</button></td>;
  })}</tr>)}</tbody></table></div><div className="calendar-legend"><span><i className="swatch missing" style={{ background: scientificColors.unknown.background }} /> {medianMode ? 'Unassessed' : 'Unknown'}</span><span>{medianMode ? 'Below median' : 'Lower'} {(medianMode ? scientificColors.departure : scientificColors.activity).map((color, i) => <i className="swatch" key={color} style={{ background: color }} title={medianMode && i === 3 ? 'At median' : undefined} />)} {medianMode ? 'Above median' : 'Higher count'}</span><span>{medianMode ? `0 = at median · scale ±${formatCount(maximumDeparture)}` : '* Completeness unknown'}</span></div><p className="chart-footnote">{medianMode ? 'Signed values show detections above (+) or below (−) the median of complete earlier instances of the same calendar month. Darker colors are farther from the median. Hatched — cells are unassessed, not zero. This is descriptive context, not fire risk.' : footnote ?? `${valueLabel ?? comparisonLabel(data)} · color shows relative activity within this series; it does not indicate fire risk. Select a month to inspect its anomaly assessment.`}</p></>;
}
