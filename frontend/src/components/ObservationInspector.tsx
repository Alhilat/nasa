import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { api } from '../api';
import type { ObservationDetail, ObservationProperties } from '../types';

export default function ObservationInspector({ observation, close }: { observation: ObservationProperties; close: () => void }) {
  const [detail, setDetail] = useState<ObservationDetail | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setDetail(null); setError('');
    api.detail(observation.id, controller.signal).then(setDetail).catch(e => {
      if (!controller.signal.aborted) setError(e.message);
    });
    return () => controller.abort();
  }, [observation.id]);
  return <aside className="inspector" aria-label="Observation provenance">
    <div className="panel-heading"><h3>Observation #{observation.id}</h3><button className="icon-button" onClick={close} aria-label="Close observation"><X size={18} /></button></div>
    <p>{observation.sensor_code} · {new Date(observation.acquired_at).toISOString()}</p>
    <dl><dt>Native confidence</dt><dd>{observation.confidence_native} ({observation.confidence_class})</dd><dt>FRP</dt><dd>{observation.frp_mw ?? 'Unknown'} MW</dd><dt>Source data row</dt><dd>{observation.source_row}</dd><dt>SHA-256</dt><dd className="hash">{observation.source_sha256}</dd></dl>
    {error && <p role="alert">{error}</p>}
    {!detail && !error && <p role="status">Loading source fields and uncertainty…</p>}
    {detail && <><a href={detail.source_url} target="_blank" rel="noreferrer">View source location ↗</a><h4>Original source fields</h4><pre>{JSON.stringify(detail.raw_properties, null, 2)}</pre><h4>Uncertainty metadata</h4><pre>{JSON.stringify(detail.uncertainty, null, 2)}</pre></>}
  </aside>;
}
