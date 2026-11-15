import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import ObservationInspector from './ObservationInspector';
import { api } from '../api';

vi.mock('../api', () => ({ api: { detail: vi.fn(), detectionContext: vi.fn() } }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it('explains a detection and keeps source identifiers in a collapsed section', async () => {
  vi.mocked(api.detail).mockResolvedValue({ id: 549, raw_properties: {}, uncertainty: {}, source_url: 'https://example.com', source_sha256: 'abc', source_row: 530, product_version: '1' });
  render(<ObservationInspector close={() => {}} observation={{ id: 549, acquired_at: '2013-11-28T10:42:00Z', sensor_code: 'VIIRS_SNPP', confidence_native: 'n', confidence_class: 'nominal', frp_mw: 1.93, source_id: 'source', source_sha256: 'abc', source_row: 530, uncertainty: {}, coordinates: [35.5, 31.2] }} />);
  expect(screen.getByText('November 28, 2013 at 10:42 AM UTC')).toBeTruthy();
  expect(screen.getByText('31.2000° N, 35.5000° E')).toBeTruthy();
  expect(screen.getByText('VIIRS on Suomi NPP')).toBeTruthy();
  expect(screen.getByText('Nominal (standard)')).toBeTruthy();
  expect(screen.getByText(`${(1.93).toLocaleString()} megawatts`)).toBeTruthy();
  expect(screen.getByText('Sensor code')).toBeTruthy();
  expect(screen.getByText('2013-11-28T10:42:00.000Z')).toBeTruthy();
  expect(screen.getByText('Source and technical details').closest('details')?.open).toBe(false);
  expect(await screen.findByText('Open original data source ↗')).toBeTruthy();
});

it('does not assign units to a missing heat estimate', () => {
  vi.mocked(api.detail).mockResolvedValue({ id: 1, raw_properties: {}, uncertainty: {}, source_url: '', source_sha256: '', source_row: 1, product_version: '' });
  render(<ObservationInspector close={() => {}} observation={{ id: 1, acquired_at: 'bad date', sensor_code: 'UNKNOWN', confidence_native: '', confidence_class: '', frp_mw: null, source_id: '', source_sha256: '', source_row: 1, uncertainty: {} }} />);
  expect(screen.queryByText(/Not available megawatts/)).toBeNull();
  expect(screen.getAllByText('Not available').length).toBeGreaterThan(0);
});

it('checks archive evidence only on request and reports nearby detections', async () => {
  vi.mocked(api.detail).mockResolvedValue({ id: 1, raw_properties: {}, uncertainty: {}, source_url: '', source_sha256: '', source_row: 1, product_version: '' });
  vi.mocked(api.detectionContext).mockResolvedValue({ observation_id: 1, radius_meters: 2000,
    nearby: { start: '', end: '', detections: 3, utc_days: 2 },
    history: { start: '', end: '', detections: 8, utc_months: 4 },
    scope: '', coverage: '', interpretation: '', unavailable: ['Land cover', 'Independent fire reports'] });
  render(<ObservationInspector close={() => {}} observation={{ id: 1, acquired_at: '2024-01-01T00:00:00Z', sensor_code: 'VIIRS_SNPP', confidence_native: 'n', confidence_class: 'nominal', frp_mw: null, source_id: '', source_sha256: '', source_row: 1, uncertainty: {} }} />);
  expect(api.detectionContext).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Check this detection' }));
  expect(await screen.findByText('Other detections found nearby')).toBeTruthy();
  expect(screen.getByText(`${(3).toLocaleString()} other detections`)).toBeTruthy();
  expect(screen.getByText(`${(8).toLocaleString()} other detections`)).toBeTruthy();
  expect(screen.getByText(/Coverage is unknown/)).toBeTruthy();
  expect(screen.getByText(/land cover, independent fire reports/)).toBeTruthy();
});

it('reports a failed check and allows retry', async () => {
  vi.mocked(api.detail).mockResolvedValue({ id: 1, raw_properties: {}, uncertainty: {}, source_url: '', source_sha256: '', source_row: 1, product_version: '' });
  vi.mocked(api.detectionContext).mockRejectedValueOnce(new Error('Archive offline')).mockResolvedValueOnce({ observation_id: 1, radius_meters: 2000, nearby: { start: '', end: '', detections: 0, utc_days: 0 }, history: { start: '', end: '', detections: 0, utc_months: 0 }, scope: '', coverage: '', interpretation: '', unavailable: [] });
  render(<ObservationInspector close={() => {}} observation={{ id: 1, acquired_at: '2024-01-01T00:00:00Z', sensor_code: 'VIIRS_SNPP', confidence_native: 'n', confidence_class: 'nominal', frp_mw: null, source_id: '', source_sha256: '', source_row: 1, uncertainty: {} }} />);
  fireEvent.click(screen.getByRole('button', { name: 'Check this detection' }));
  expect(await screen.findByText(/Archive offline/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
  expect(await screen.findByText('No other detections found nearby')).toBeTruthy();
});
