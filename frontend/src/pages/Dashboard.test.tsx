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
vi.mock('../components/ActivityChart', () => ({ default: () => <div>Daily activity chart</div> }));
vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), api: {
  observations: vi.fn(), summary: vi.fn(), jobs: vi.fn(), detail: vi.fn(),
} }));
vi.mock('../history', async original => ({ ...await original<typeof import('../history')>(), historyRequest: vi.fn() }));

beforeEach(() => {
  vi.mocked(api.observations).mockResolvedValue({ type: 'FeatureCollection', features: [], metadata: { returned: 0, has_more: false, limit: 2000, offset: 0 } });
  vi.mocked(api.summary).mockResolvedValue({ detection_count: 2, source_count: 1, frp_known_count: 0, frp_sum_mw: null, by_sensor: { MODIS_TERRA: 1, MODIS_AQUA: 1 }, daily: [], first_acquisition: '2013-01-02T02:08:00+03:00', last_acquisition: '2026-01-01T02:10:00+03:00', coverage_known: false, method: 'synthetic software fixture' });
  vi.mocked(api.jobs).mockResolvedValue([]);
  vi.mocked(historyRequest).mockImplementation(async query => ({
    query, analysis_id: 'synthetic-test-only', sources: [], metric_explanations: {},
    monthly: ['2013-01','2013-02'].map((month, index) => ({ sensor_code: 'MODIS_TERRA', month, count: index ? null : 2, completeness: 'unknown', historical_median: null, baseline_size: 0, lower_threshold: null, upper_threshold: null, anomaly_status: 'incomplete_period', robust_z: null, year_over_year: { percent_change: null } })),
  } as unknown as HistoryResult));
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const open = () => render(<MemoryRouter><Dashboard /></MemoryRouter>);

it('requests each map month within the applied date range and can return to the full period', async () => {
  open();
  await screen.findByLabelText('Start date');
  fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2013-01-15' } });
  fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2013-02-10' } });
  fireEvent.click(screen.getByRole('button', { name: /Apply filters/ }));
  fireEvent.change(screen.getByLabelText('Map period'), { target: { value: 'month' } });
  await waitFor(() => expect(vi.mocked(api.observations).mock.calls.at(-1)![0]).toMatchObject({ start: '2013-01-15T00:00:00.000Z', end: '2013-02-01T00:00:00.000Z' }));
  fireEvent.click(screen.getByRole('button', { name: 'Next month' }));
  await waitFor(() => expect(vi.mocked(api.observations).mock.calls.at(-1)![0]).toMatchObject({ start: '2013-02-01T00:00:00.000Z', end: '2013-02-11T00:00:00.000Z' }));
  expect(screen.getByRole('button', { name: 'Next month' }).hasAttribute('disabled')).toBe(true);
  fireEvent.change(screen.getByLabelText('Map period'), { target: { value: 'all' } });
  expect(screen.queryByLabelText('Map month')).toBeNull();
  expect(screen.getByText('The map shows the entire selected date range.')).toBeTruthy();
});

it('shows daily observation counts in the dashboard', async () => {
  const summary = await api.summary({ sensors: [], limit: 1 });
  vi.mocked(api.summary).mockResolvedValue({ ...summary, daily: [{ day: '2013-01-02', sensor_code: 'MODIS_TERRA', count: 2 }] });
  open();
  expect(await screen.findByText('Daily activity chart')).toBeTruthy();
  fireEvent.click(screen.getByText('View daily counts as a table'));
  expect(screen.getByRole('cell', { name: '2013-01-02' })).toBeTruthy();
  expect(screen.getByRole('cell', { name: 'MODIS_TERRA' })).toBeTruthy();
});

it('renders backend counts, missing months and withheld anomaly decisions without invented results', async () => {
  open();
  expect(await screen.findByText('Assessment withheld: month completeness is unknown. Add audited declarations in Analysis settings.')).toBeTruthy();
  expect(screen.getByRole('button', { name: /2013-02, MODIS_TERRA: unknown/ })).toBeTruthy();
  expect(screen.getByText(/No saved grid counts/)).toBeTruthy();
  expect(screen.getByText(/Counts represent satellite detections, not unique fires/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /2013-02, MODIS_TERRA: unknown/ }));
  expect(screen.getByRole('button', { name: /2013-02, MODIS_TERRA: unknown/ }).getAttribute('aria-pressed')).toBe('true');
});
it('applies a sensor and region to both exact-date observations and whole-year historical context', async () => {
  open();
  await screen.findByText(/Assessment withheld/);
  fireEvent.change(screen.getByLabelText('Area'), { target: { value: 'custom' } });
  fireEvent.change(screen.getByLabelText('Coordinates · west, south, east, north'), { target: { value: '35,30,39,33' } });
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
  expect((await screen.findAllByText('Archive unavailable')).length).toBeGreaterThan(0);
  expect(screen.queryByText('No detections match these filters')).toBeNull();
  const calls = vi.mocked(api.summary).mock.calls.length;
  fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
  await waitFor(() => expect(api.summary).toHaveBeenCalledTimes(calls + 1));
});
it('rejects malformed region fields before changing the applied selection', async () => {
  open();
  await screen.findByText(/Assessment withheld/);
  const calls = vi.mocked(api.summary).mock.calls.length;
  fireEvent.change(screen.getByLabelText('Area'), { target: { value: 'custom' } });
  fireEvent.change(screen.getByLabelText('Coordinates · west, south, east, north'), { target: { value: '34,,40,34' } });
  fireEvent.click(screen.getByRole('button', { name: /Apply filters/ }));
  expect(await screen.findByText('Enter four finite bounds: west, south, east, north.')).toBeTruthy();
  expect(api.summary).toHaveBeenCalledTimes(calls);
});

it('loads the full archive date range in UTC and excludes satellites without data by default', async () => {
  open();
  const start = await screen.findByLabelText('Start date');
  expect(start).toHaveProperty('value', '2013-01-01');
  expect(screen.getByLabelText('End date')).toHaveProperty('value', '2025-12-31');
  expect(start.getAttribute('min')).toBe('2013-01-01');
  expect(screen.getByLabelText('End date').getAttribute('max')).toBe('2025-12-31');
  expect(screen.getByLabelText('VIIRS NOAA20').hasAttribute('disabled')).toBe(true);
  const selection = vi.mocked(api.observations).mock.calls.at(-1)![0];
  expect(selection).toMatchObject({ start: '2013-01-01T00:00:00Z', end: '2026-01-01T00:00:00.000Z', sensors: ['MODIS_TERRA', 'MODIS_AQUA'] });
});

it('uses dates returned by the archive instead of fixed study years', async () => {
  vi.mocked(api.summary).mockResolvedValue({
    detection_count: 1, source_count: 1, by_sensor: { VIIRS_SNPP: 1 }, daily: [],
    first_acquisition: '2020-05-12T10:00:00Z', last_acquisition: '2024-09-22T11:00:00Z',
    frp_known_count: 0, frp_sum_mw: null, coverage_known: false, method: 'synthetic software fixture',
  });
  open();
  expect(await screen.findByLabelText('Start date')).toHaveProperty('value', '2020-05-12');
  expect(screen.getByLabelText('End date')).toHaveProperty('value', '2024-09-22');
  await waitFor(() => expect(historyRequest).toHaveBeenCalled());
  expect(vi.mocked(historyRequest).mock.calls.at(-1)![0]).toMatchObject({ start_year: 2020, end_year: 2024, sensors: ['VIIRS_SNPP'] });
});

it('applies date presets, named areas and analysis sliders to the actual requests', async () => {
  open();
  await screen.findByLabelText('Start date');
  fireEvent.click(screen.getByRole('button', { name: 'Latest 12 months' }));
  expect(screen.getByLabelText('Start date')).toHaveProperty('value', '2025-01-01');
  fireEvent.change(screen.getByLabelText('Area'), { target: { value: 'levant' } });
  fireEvent.click(screen.getByRole('button', { name: 'Advanced settings' }));
  fireEvent.change(screen.getByRole('slider', { name: 'Unusual activity threshold' }), { target: { value: '97' } });
  fireEvent.change(screen.getByRole('slider', { name: 'Earlier years needed' }), { target: { value: '7' } });
  fireEvent.click(screen.getByRole('button', { name: /Apply filters/ }));
  await waitFor(() => expect(vi.mocked(historyRequest).mock.calls.at(-1)![0]).toMatchObject({ start_year: 2025, end_year: 2025, bbox: [34,29,43,38], percentile: 97, min_baseline_years: 7 }));
  fireEvent.click(screen.getByRole('button', { name: 'All dates' }));
  expect(screen.getByLabelText('Start date')).toHaveProperty('value', '2013-01-01');
});

it('keeps the date slider handles ordered and includes a selected single day', async () => {
  open();
  await screen.findByLabelText('Start date');
  fireEvent.change(screen.getByRole('slider', { name: 'Range start date' }), { target: { value: '365' } });
  fireEvent.change(screen.getByRole('slider', { name: 'Range end date' }), { target: { value: '100' } });
  expect(screen.getByLabelText('Start date')).toHaveProperty('value', '2014-01-01');
  expect(screen.getByLabelText('End date')).toHaveProperty('value', '2014-01-01');
  fireEvent.click(screen.getByRole('button', { name: /Apply filters/ }));
  await waitFor(() => expect(vi.mocked(api.observations).mock.calls.at(-1)![0]).toMatchObject({ start: '2014-01-01T00:00:00Z', end: '2014-01-02T00:00:00.000Z' }));
});

it('does not invent a date range for an empty archive', async () => {
  vi.mocked(api.summary).mockResolvedValue({
    detection_count: 0, source_count: 0, by_sensor: {}, daily: [],
    first_acquisition: null, last_acquisition: null, frp_known_count: 0,
    frp_sum_mw: null, coverage_known: false, method: 'synthetic software fixture',
  });
  open();
  expect(await screen.findByText('No observations in the archive')).toBeTruthy();
  expect(screen.queryByLabelText('Start date')).toBeNull();
  expect(api.observations).not.toHaveBeenCalled();
});

it('allows a date field to be edited without breaking the range controls', async () => {
  open();
  const start = await screen.findByLabelText('Start date');
  fireEvent.change(start, { target: { value: '' } });
  expect(start).toHaveProperty('value', '');
  expect(screen.getByRole('slider', { name: 'Range start date' })).toHaveProperty('value', '0');
  fireEvent.change(start, { target: { value: '2024-02-29' } });
  fireEvent.click(screen.getByRole('button', { name: /Apply filters/ }));
  await waitFor(() => expect(vi.mocked(api.observations).mock.calls.at(-1)![0]).toMatchObject({ start: '2024-02-29T00:00:00Z' }));
});

it('clears coverage declarations when a date preset changes their selection', async () => {
  open();
  await screen.findByLabelText('Start date');
  fireEvent.click(screen.getByRole('button', { name: 'Advanced settings' }));
  const coverage = screen.getByLabelText('Verified complete-month declarations · JSON');
  fireEvent.change(coverage, { target: { value: '[{"sensor_code":"MODIS_TERRA","month":"2013-01","reference":"synthetic coverage test"}]' } });
  fireEvent.click(screen.getByRole('button', { name: 'Latest 12 months' }));
  expect(coverage).toHaveProperty('value', '[]');
  fireEvent.click(screen.getByRole('button', { name: /Apply filters/ }));
  await waitFor(() => expect(vi.mocked(historyRequest).mock.calls.at(-1)![0]).toMatchObject({ start_year: 2025, complete_months: [] }));
});
