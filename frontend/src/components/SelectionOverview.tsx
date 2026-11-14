import { ArrowRight, Satellite } from 'lucide-react';
import { Link } from 'react-router-dom';
import { displayDate } from './DateRangeControl';
import { formatCount } from '../dashboard';
import type { Summary } from '../types';
import type { Resource } from '../useResource';

export default function SelectionOverview({ summary, start, end }: {
  summary: Resource<Summary>; start: string; end: string;
}) {
  const data = !summary.loading && !summary.error ? summary.data : null;
  const latest = data?.last_acquisition ? new Date(data.last_acquisition).toISOString().slice(0, 10) : null;
  return <section className="panel selection-overview" aria-labelledby="selection-overview-title">
    <div className="overview-heading"><Satellite size={21} aria-hidden="true" /><div>
      <h2 id="selection-overview-title">What the satellites saw</h2>
      <p>Saved records · {displayDate(start)} – {displayDate(end)} · UTC</p>
    </div></div>
    {summary.loading ? <p className="overview-lead" role="status">Looking up records for this area…</p>
      : summary.error ? <p className="overview-lead">We couldn’t load the records. Try Refresh to check this area again.</p>
        : data && data.detection_count > 0 ? <>
          <p className="overview-lead">Satellites recorded unusually hot spots in this area.</p>
          <p className="overview-explanation">These may be fires or other sources of heat. Select a point on the map to see when and where it was recorded.</p>
          <div className="overview-actions"><a className="button secondary" href="#observation-map">See locations on the map <ArrowRight size={15} /></a>
            {latest && <span>Latest record: <time dateTime={latest}>{displayDate(latest)}</time></span>}
          </div>
        </> : data ? <>
          <p className="overview-lead">No hot spots were found in the selected records.</p>
          <p className="overview-explanation">Try another area or date range. Missing records don’t prove that no fires occurred.</p>
          <Link className="text-link" to="/sources">Check the available data <ArrowRight size={14} /></Link>
        </> : <p className="overview-lead">No records are available for this selection.</p>}
    {data && <details className="overview-details"><summary>Show the underlying data</summary>
      <dl><div><dt>Satellite readings</dt><dd>{formatCount(data.detection_count)}</dd><p>A single fire or location may be recorded more than once. This is not a count of separate fires.</p></div>
        <div><dt>Original data files</dt><dd>{formatCount(data.source_count)}</dd><p>Source files used for the selected area, dates and satellites.</p></div>
        <div><dt>Radiative power sum · MW</dt><dd>{formatCount(data.frp_sum_mw)}</dd><p>Sum across {formatCount(data.frp_known_count)} readings with power measurements; not current fire power or total energy.</p></div>
      </dl>
    </details>}
  </section>;
}
