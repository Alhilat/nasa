import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from './Dashboard';
import { api } from '../api';
import { historyRequest } from '../history';
import type { HistoryResult } from '../history';
vi.mock('../components/AIIntelligencePanel', () => ({ default: () => <div>AI scientific intelligence</div> }));

vi.mock('../components/RegionMap', () => ({ default: () => <div>Interactive region map</div> }));
vi.mock('../components/ScientificChart', () => ({ default: () => <div>Scientific chart</div> }));
vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), api: {
  observations: vi.fn(), summary: vi.fn(), jobs: vi.fn(), detail: vi.fn(),
} }));
vi.mock('../history', async original => ({ ...await original<typeof import('../history')>(), historyRequest: vi.fn() }));

beforeEach(() => {
  vi.mocked(api.observations).mockResolvedValue({ type: 'FeatureCollection', features: [], metadata: { returned: 0, has_more: false, limit: 2000, offset: 0 } });
  vi.mocked(api.summary).mockResolvedValue({ detection_count: 2, source_count: 1, frp_known_count: 0, frp_sum_mw: null, by_sensor: { MODIS_TERRA: 2 }, daily: [], first_acquisition: null, last_acquisition: null, coverage_known: false, method: 'synthetic software fixture' });
  vi.mocked(api.jobs).mockResolvedValue([]);
  vi.mocked(historyRequest).mockImplementation(async query => ({
    query, analysis_id: 'synthetic-test-only', sources: [], metric_explanations: {},
    monthly: ['2013-01','2013-02'].map((month, index) => ({ sensor_code: 'MODIS_TERRA', month, count: index ? null : 2, completeness: 'unknown', historical_median: null, baseline_size: 0, lower_threshold: null, upper_threshold: null, anomaly_status: 'incomplete_period', robust_z: null, year_over_year: { percent_change: null } })),
  } as unknown as HistoryResult));
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const open = () => render(<MemoryRouter><Dashboard /></MemoryRouter>);

it('renders backend counts, missing months and withheld anomaly decisions without invented results', async () => {
  open();
  expect(await screen.findByText('Assessment withheld: month completeness is unknown. Add audited declarations in Analysis settings.')).toBeTruthy();
  expect(screen.getByRole('button', { name: /2013-02, MODIS_TERRA: unknown/ })).toBeTruthy();
  expect(screen.getByText(/No recent successful aggregate job/)).toBeTruthy();
  expect(screen.getByText(/Operational sensor calibration and risk forecasting are not enabled/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /2013-02, MODIS_TERRA: unknown/ }));
  expect(screen.getByRole('button', { name: /2013-02, MODIS_TERRA: unknown/ }).getAttribute('aria-pressed')).toBe('true');
});
it('applies a sensor and region to both exact-date observations and whole-year historical context', async () => {
  open();
  await screen.findByText(/Assessment withheld/);
  fireEvent.change(screen.getByLabelText('Study area · west, south, east, north'), { target: { value: '35,30,39,33' } });
  fireEvent.click(screen.getByLabelText('MODIS TERRA'));
  fireEvent.click(screen.getByRole('button', { name: /Apply filters/ }));
  await waitFor(() => expect(vi.mocked(api.summary).mock.calls.at(-1)?.[0].bbox).toEqual([35,30,39,33]));
  const exact = vi.mocked(api.summary).mock.calls.at(-1)![0];
  const historical = vi.mocked(historyRequest).mock.calls.at(-1)![0];
  expect(exact.sensors).not.toContain('MODIS_TERRA');
  expect(historical.bbox).toEqual(exact.bbox);
  expect(historical.sensors).toEqual(exact.sensors);
  expect(historical.end_year).toBe(2025);
});
it('reports backend failures and retries without replacing missing totals with zero', async () => {
  vi.mocked(api.summary).mockRejectedValue(new Error('Archive connection failed'));
  vi.mocked(historyRequest).mockRejectedValue(new Error('Archive connection failed'));
  open();
  expect(await screen.findByText('Connect your scientific archive')).toBeTruthy();
  expect(screen.queryByText('No detections match these filters')).toBeNull();
  const calls = vi.mocked(api.summary).mock.calls.length;
  fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
  await waitFor(() => expect(api.summary).toHaveBeenCalledTimes(calls + 1));
});
it('rejects malformed region fields before changing the applied selection', async () => {
  open();
  await screen.findByText(/Assessment withheld/);
  const calls = vi.mocked(api.summary).mock.calls.length;
  fireEvent.change(screen.getByLabelText('Study area · west, south, east, north'), { target: { value: '34,,40,34' } });
  fireEvent.click(screen.getByRole('button', { name: /Apply filters/ }));
  expect(await screen.findByText('Enter four finite bounds: west, south, east, north.')).toBeTruthy();
  expect(api.summary).toHaveBeenCalledTimes(calls);
});
