import type { HistoryMonth } from '../history';
import { formatCount } from '../dashboard';

const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export default function BurningCalendar({ rows, sensor, selected, onSelect }: {
  rows: HistoryMonth[]; sensor: string; selected: string; onSelect: (month: string) => void;
}) {
  const data = rows.filter(r => r.sensor_code === sensor);
  const years = [...new Set(data.map(r => r.month.slice(0, 4)))];
  const index = new Map(data.map(r => [r.month, r]));
  const maximum = Math.max(1, ...data.map(r => r.count ?? 0));
  return <><div className="calendar-scroll"><table className="burning-calendar"><caption className="sr-only">Year-by-month thermal detections for {sensor}. Unknown completeness is not an anomaly decision.</caption><thead><tr><th scope="col">Year</th>{months.map(m => <th key={m} scope="col">{m}</th>)}</tr></thead><tbody>{years.map(y => <tr key={y}><th scope="row">{y}</th>{months.map((m, i) => {
    const label = `${y}-${String(i + 1).padStart(2, '0')}`, row = index.get(label);
    const value = row?.count ?? null;
    const level = value === null ? 'missing' : `level-${value === 0 ? 0 : Math.max(1, Math.ceil(value / maximum * 4))}`;
    const explanation = `${label}, ${sensor}: ${value === null ? 'unknown' : `${formatCount(value)} archived detections`}; completeness ${row?.completeness ?? 'unknown'}; ${row?.anomaly_status.replaceAll('_', ' ') ?? 'not assessed'}`;
    return <td key={m}><button className={`calendar-cell ${level} ${selected === label ? 'selected' : ''}`} aria-label={explanation} aria-pressed={selected === label} title={explanation} onClick={() => onSelect(label)}>{value === null ? '—' : value}{row?.completeness !== 'complete' && value !== null && <span aria-hidden="true">*</span>}</button></td>;
  })}</tr>)}</tbody></table></div><div className="calendar-legend"><span><i className="swatch missing" /> Unknown</span><span>Lower <i className="swatch level-1" /><i className="swatch level-2" /><i className="swatch level-3" /><i className="swatch level-4" /> Higher count</span><span>* Completeness unknown</span></div><p className="chart-footnote">Color describes archived count within this sensor, not fire risk. Select a month to inspect its anomaly assessment.</p></>;
}
