import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { api } from '../api';
import type { DetectionContext, ObservationDetail, ObservationProperties } from '../types';

const satellites: Record<string, string> = {
  MODIS_TERRA: 'MODIS on Terra', MODIS_AQUA: 'MODIS on Aqua',
  VIIRS_SNPP: 'VIIRS on Suomi NPP', VIIRS_NOAA20: 'VIIRS on NOAA-20', VIIRS_NOAA21: 'VIIRS on NOAA-21',
};

export default function ObservationInspector({ observation, close }: { observation: ObservationProperties; close: () => void }) {
  const [detail, setDetail] = useState<ObservationDetail | null>(null);
  const [error, setError] = useState('');
  const [checkId, setCheckId] = useState<number | null>(null);
  const [context, setContext] = useState<DetectionContext | null>(null);
  const [contextError, setContextError] = useState('');
  const [checking, setChecking] = useState(false);
  const [checkAttempt, setCheckAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setDetail(null); setError('');
    api.detail(observation.id, controller.signal).then(setDetail).catch(e => {
      if (!controller.signal.aborted) setError(e.message);
    });
    return () => controller.abort();
  }, [observation.id]);
  useEffect(() => {
    setContext(null); setContextError('');
    if (checkId !== observation.id) { setChecking(false); return; }
    const controller = new AbortController();
    setChecking(true);
    api.detectionContext(observation.id, controller.signal).then(result => { if (!controller.signal.aborted) setContext(result); }).catch(e => {
      if (!controller.signal.aborted) setContextError(e.message);
    }).finally(() => { if (!controller.signal.aborted) setChecking(false); });
    return () => controller.abort();
  }, [checkId, observation.id, checkAttempt]);
  const date = new Date(observation.acquired_at);
  const when = Number.isNaN(date.getTime()) ? 'Not available' : `${new Intl.DateTimeFormat('en', { dateStyle: 'long', timeStyle: 'short', timeZone: 'UTC' }).format(date)} UTC`;
  const confidence = observation.confidence_class?.toLowerCase();
  const confidenceLabel = confidence === 'nominal' ? 'Nominal (standard)' : confidence === 'high' ? 'High' : confidence === 'low' ? 'Low' : 'Not available';
  const coordinates = observation.coordinates;
  return <aside className="inspector" aria-label="Detection details">
    <div className="panel-heading"><h3>Heat detection</h3><button className="icon-button" onClick={close} aria-label="Close observation"><X size={18} /></button></div>
    <p className="inspector-intro">A satellite detected an unusually hot spot at this location. This is a detection, not necessarily a separate fire.</p>
    <dl className="inspector-facts">
      <dt>Detected on</dt><dd>{when}</dd>
      <dt>Location</dt><dd>{coordinates ? `${Math.abs(coordinates[1]).toFixed(4)}° ${coordinates[1] < 0 ? 'S' : 'N'}, ${Math.abs(coordinates[0]).toFixed(4)}° ${coordinates[0] < 0 ? 'W' : 'E'}` : 'Not available'}</dd>
      <dt>Satellite and instrument</dt><dd>{satellites[observation.sensor_code] ?? observation.sensor_code}</dd>
      <dt>Detection confidence</dt><dd>{confidenceLabel}<small>The sensor’s quality category; it is not a probability that a fire occurred.</small></dd>
      <dt>Estimated heat released</dt><dd>{observation.frp_mw == null ? 'Not available' : `${observation.frp_mw.toLocaleString()} megawatts`}<small>Fire radiative power estimates heat emitted at the time of the satellite pass. It does not measure burned area.</small></dd>
    </dl>
    <section className="detection-check" aria-label="Detection evidence">
      <h4>Can we tell if it is a fire?</h4>
      <p>Check the archive for other satellite detections near this point.</p>
      {checkId !== observation.id && <button className="button secondary" type="button" onClick={() => setCheckId(observation.id)}>Check this detection</button>}
      {checking && <p role="status">Checking nearby detections…</p>}
      {contextError && <><p role="alert">Could not check nearby detections: {contextError}</p><button className="button secondary" type="button" onClick={() => setCheckAttempt(n => n + 1)}>Try again</button></>}
      {context && <div className="detection-evidence">
        <strong>{context.nearby.detections > 0 ? 'Other detections found nearby' : 'No other detections found nearby'}</strong>
        <p>Within {context.radius_meters / 1000} km and 24 hours before or after this detection, the archive contains <b>{context.nearby.detections.toLocaleString()} other detections</b> across {context.nearby.utc_days} UTC days.</p>
        <p>In the 365 days before and after, excluding that 48-hour window, it contains <b>{context.history.detections.toLocaleString()} other detections</b> across {context.history.utc_months} calendar months.</p>
        <p>{context.history.detections > 0 ? 'Heat was also detected nearby at other times in the wider period.' : 'No detections were recorded nearby at other times in the wider period.'} These are satellite records, not counts of separate fires. Repeated heat can have several causes. The selected point is excluded; all archived sensors and confidence classes are included.</p>
        <p>Source: the local NASA FIRMS observation archive. Coverage is unknown, so no detections do not prove there was no fire.</p>
        <p>Whether this was a fire cannot be determined from these records alone. Not checked: {context.unavailable.join(', ').toLowerCase()}. These sources are not connected.</p>
      </div>}
    </section>
    <details className="inspector-technical"><summary>Source and technical details</summary>
      <dl><dt>Observation ID</dt><dd>{observation.id}</dd><dt>Original confidence value</dt><dd>{observation.confidence_native || 'Not available'}</dd><dt>Source data row</dt><dd>{observation.source_row}</dd><dt>Source file checksum (SHA-256)</dt><dd className="hash">{observation.source_sha256}</dd></dl>
      {error && <p role="alert">Source details could not be loaded: {error}</p>}
      {!detail && !error && <p role="status">Loading source details…</p>}
      {detail && <><a href={detail.source_url} target="_blank" rel="noreferrer">Open original data source ↗</a><h4>Original source fields</h4><pre>{JSON.stringify(detail.raw_properties, null, 2)}</pre><h4>Uncertainty metadata</h4><pre>{JSON.stringify(detail.uncertainty, null, 2)}</pre></>}
    </details>
  </aside>;
}
