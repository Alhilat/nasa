import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Explorer from './Explorer';
import { api } from '../api';
import type { Observations } from '../types';

vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), api: { observations: vi.fn(), summary: vi.fn() } }));
vi.mock('../components/FireMap', () => ({ default: () => <div>Existing explorer map</div> }));
vi.mock('../components/ActivityChart', () => ({ default: () => <div>Existing daily chart</div> }));
const observations = {
  type: 'FeatureCollection',
  features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [35,31] }, properties: { id: 1, source_id: 'synthetic-test-source', source_sha256: 'synthetic-test-checksum' } }],
  metadata: { returned: 1, limit: 2000, offset: 0, has_more: false },
} as unknown as Observations;
beforeEach(() => {
  vi.mocked(api.observations).mockResolvedValue(observations);
  vi.mocked(api.summary).mockResolvedValue({ detection_count: 1, source_count: 1, by_sensor: { MODIS_TERRA: 1 }, daily: [], frp_sum_mw: null, frp_known_count: 0, first_acquisition: null, last_acquisition: null, coverage_known: false, method: 'synthetic software fixture' });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

it('restores the GeoJSON download with the original page, query, source fields and scientific caveat', async () => {
  let exported: Blob | undefined;
  const revoke = vi.fn();
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL(blob: Blob) { exported = blob; return 'blob:synthetic-test'; }
    static revokeObjectURL = revoke;
  });
  const clicked = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  render(<MemoryRouter initialEntries={[{ pathname: '/explorer', state: { query: { sensors: ['MODIS_TERRA'], bbox: [34,29,40,34], limit: 2000 } } }]}><Explorer /></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Export GeoJSON' }).hasAttribute('disabled')).toBe(false));
  fireEvent.click(screen.getByRole('button', { name: 'Export GeoJSON' }));
  expect(clicked).toHaveBeenCalledTimes(1);
  expect(exported?.type).toBe('application/geo+json');
  const text = await new Promise<string>(resolve => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.readAsText(exported!);
  });
  const payload = JSON.parse(text);
  expect(payload.features).toEqual(observations.features);
  expect(payload.metadata.query.bbox).toEqual([34,29,40,34]);
  expect(payload.metadata.science_note).toContain('Export includes displayed page only');
  expect(screen.getByText('Existing explorer map')).toBeTruthy();
  expect(screen.getByText('Existing daily chart')).toBeTruthy();
  await waitFor(() => expect(revoke).toHaveBeenCalled(), { timeout: 2000 });
});

it('retains the original spatial, date and confidence filters on the recovered route', async () => {
  render(<MemoryRouter><Explorer /></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole('button', { name: /Apply filters/ }).hasAttribute('disabled')).toBe(false));
  fireEvent.click(screen.getByRole('button', { name: 'Toggle spatial and confidence filters' }));
  fireEvent.change(screen.getByLabelText('Bounding box · west, south, east, north'), { target: { value: '34,29,40,34' } });
  fireEvent.change(screen.getByLabelText('Sensor family'), { target: { value: 'VIIRS' } });
  fireEvent.change(screen.getByLabelText('Native confidence class'), { target: { value: 'high' } });
  fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2013-01-01' } });
  fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2013-01-31' } });
  fireEvent.click(screen.getByRole('button', { name: /Apply filters/ }));
  await waitFor(() => expect(vi.mocked(api.observations).mock.calls.at(-1)?.[0]).toMatchObject({ bbox: [34,29,40,34], confidence: 'high', start: '2013-01-01T00:00:00Z', end: '2013-02-01T00:00:00.000Z' }));
  expect(vi.mocked(api.observations).mock.calls.at(-1)![0].sensors.every(sensor => sensor.startsWith('VIIRS'))).toBe(true);
});
