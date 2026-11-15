import { useState } from 'react';
import type { FormEvent } from 'react';
import { boundsRegion, parseBounds } from '../dashboard';
import type { Region } from '../dashboard';

export default function CoordinateRegionForm({ onRegion }: { onRegion: (region: Region) => void }) {
  const [values, setValues] = useState({ west: '', south: '', east: '', north: '' });
  const [error, setError] = useState('');
  function submit(event: FormEvent) {
    event.preventDefault(); setError('');
    try {
      const bounds = parseBounds([values.west, values.south, values.east, values.north].join(','));
      onRegion(boundsRegion(bounds));
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Enter valid coordinates.'); }
  }
  return <details className="coordinate-region"><summary>Enter latitude / longitude</summary>
    <form aria-label="Region coordinates" className="coordinate-region-form" onSubmit={submit}>
      {([
        ['south', 'South latitude', -90, 90], ['north', 'North latitude', -90, 90],
        ['west', 'West longitude', -180, 180], ['east', 'East longitude', -180, 180],
      ] as const).map(([field, label, min, max]) => <label key={field}>{label}<input type="number" step="any" required min={min} max={max} value={values[field]} onChange={event => { setError(''); setValues({ ...values, [field]: event.target.value }); }} /></label>)}
      <button className="button secondary" type="submit">Use coordinates</button>
      <p>WGS84 decimal degrees. West greater than east crosses the antimeridian. Apply filters after selecting the region.</p>
      {error && <p role="alert" className="form-error">{error}</p>}
    </form>
  </details>;
}
