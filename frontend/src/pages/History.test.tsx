import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import History from './History';
import { MemoryRouter } from 'react-router-dom';
import { historyRequest, jordanBoundary } from '../history';
import type { HistoryResult } from '../history';

vi.mock('../components/HistoryTrend', () => ({ default: () => <div>Historical trend chart</div> }));
vi.mock('../history', async importOriginal => ({
  ...await importOriginal<typeof import('../history')>(), historyRequest: vi.fn(), jordanBoundary: vi.fn(),
}));
afterEach(() => cleanup());

it('keeps equal months, years and grid cells distinct and names sensors in every comparison table', async () => {
  const errors = vi.spyOn(console, 'error').mockImplementation(() => {});
  const sensors = ['MODIS_TERRA', 'MODIS_AQUA'];
  vi.mocked(historyRequest).mockImplementation(async query => ({
    query: { ...query, sensors }, analysis_id: 'synthetic-multisensor', algorithm_version: 'test',
    sources: [], metric_explanations: {}, concentration: [],
    monthly: sensors.map(sensor_code => ({ sensor_code, month: '2013-01', count: 1,
      completeness: 'unknown', historical_median: null, baseline_size: 0, lower_threshold: null,
      upper_threshold: null, anomaly_status: 'incomplete_period', robust_z: null,
      year_over_year: { difference: null, percent_change: null } })),
    yearly: sensors.map(sensor_code => ({ sensor_code, year: 2013, count: null, observed_count: 1,
      complete_months: [], year_over_year: { difference: null, percent_change: null, matched_months: [] } })),
    seasonal_profiles: sensors.map(sensor_code => ({ sensor_code, calendar_month: 1, median: 1, sample_size: 1 })),
    spatial: { type: 'FeatureCollection', features: sensors.map(sensor_code => ({
      geometry: { type: 'Point', coordinates: [35,31] },
      properties: { sensor_code, grid_x: 215, grid_y: 122, count: 1, share: 1 },
    })) },
  } as unknown as HistoryResult));
  render(<MemoryRouter><History /></MemoryRouter>);
  fireEvent.click(screen.getByRole('button', { name: 'Analyze archive' }));
  await screen.findByText('Monthly activity calendar and anomalies');
  for (const sensor of sensors) expect(screen.getAllByRole('cell', { name: sensor })).toHaveLength(4);
  expect(errors.mock.calls.some(args => args.some(v => String(v).includes('same key')))).toBe(false);
});

it('lets the user select the audited Jordan boundary after a scope mismatch', async () => {
  const boundary = { type: 'Polygon', coordinates: [[[35, 30], [36, 30], [35, 31], [35, 30]]] };
  vi.mocked(jordanBoundary).mockResolvedValue(boundary);
  vi.mocked(historyRequest).mockImplementation(async query => ({
    query, sources: [], monthly: [{ sensor_code: query.sensors[0], month: '2013-01', count: null,
      completeness: 'unknown', missing_data_status: 'spatial_scope_mismatch', historical_median: null,
      baseline_size: 0, lower_threshold: null, upper_threshold: null, anomaly_status: 'incomplete_period',
      year_over_year: { percent_change: null } }], yearly: [], seasonal_profiles: [],
    spatial: { features: [] }, concentration: [], metric_explanations: {},
  } as unknown as HistoryResult));
  render(<MemoryRouter initialEntries={[{ pathname: '/history', state: { historyQuery: { sensors: ['MODIS_TERRA', 'VIIRS_SNPP'], complete_months: [{ sensor_code: 'MODIS_TERRA', month: '2013-01', reference: 'old area' }] } } }]}><History /></MemoryRouter>);
  fireEvent.click(screen.getByRole('button', { name: 'Analyze archive' }));
  expect(vi.mocked(historyRequest).mock.lastCall?.[0].sensors).toEqual(['MODIS_TERRA', 'VIIRS_SNPP']);
  expect((await screen.findByRole('status')).textContent).toContain('extends beyond');
  fireEvent.click(screen.getByRole('status').querySelector('button')!);
  await screen.findByDisplayValue(JSON.stringify(boundary));
  fireEvent.click(screen.getByRole('button', { name: 'Analyze archive' }));
  expect(vi.mocked(historyRequest).mock.lastCall?.[0]).toMatchObject({ polygon: boundary, bbox: undefined, complete_months: [], sensors: ['MODIS_TERRA', 'VIIRS_SNPP'] });
});

it('runs an explicit area/sensor selection and renders unknown counts without zero filling', async () => {
  vi.mocked(historyRequest).mockImplementation(async query => ({
    query, analysis_id: 'synthetic-test-only', algorithm_version: 'test', sources: [],
    monthly: [{ sensor_code: query.sensors[0], month: '2013-01', count: null, completeness: 'unknown',
      historical_median: null, baseline_size: 0, lower_threshold: null, upper_threshold: null,
      anomaly_status: 'incomplete_period', year_over_year: { percent_change: null } }],
    yearly: [], seasonal_profiles: [], spatial: { features: [] }, concentration: [], metric_explanations: {},
  } as unknown as HistoryResult));
  render(<MemoryRouter><History /></MemoryRouter>);
  fireEvent.click(screen.getByRole('button', { name: 'Analyze archive' }));
  expect(await screen.findByText('Monthly activity calendar and anomalies')).toBeTruthy();
  expect(screen.getAllByText('Unknown').length).toBeGreaterThan(0);
  expect(vi.mocked(historyRequest).mock.calls[0][0]).toMatchObject({
    bbox: [34, 29, 40, 34], sensors: ['MODIS_TERRA', 'MODIS_AQUA', 'VIIRS_SNPP', 'VIIRS_NOAA20', 'VIIRS_NOAA21'], complete_months: [],
  });
  expect(screen.getByText('incomplete period')).toBeTruthy();
});

it('rejects malformed bounds before sending an analysis request', async () => {
  vi.mocked(historyRequest).mockClear();
  render(<MemoryRouter><History /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText(/Fixed bounding box/), { target: { value: '34,,40,34' } });
  fireEvent.click(screen.getByRole('button', { name: 'Analyze archive' }));
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Supply four finite bounds: west,south,east,north.');
  expect(historyRequest).not.toHaveBeenCalled();
});

it('shows baseline period, reference years, missing-data status, harmonized series, and limitations in History view', async () => {
  vi.mocked(historyRequest).mockImplementation(async query => ({
    query,
    analysis_id: 'synthetic-history-comparison',
    algorithm_version: 'historical-activity-v1',
    baseline_period: '2013–2024',
    min_baseline_years: 5,
    observation_coverage: 'unknown',
    harmonization: {
      available: true,
      applied: true,
      status: 'supported_for_scope',
      comparison_series: 'validated_harmonized',
      model_version: 'abc1234567890',
      method: 'quantile_mapping',
      source_sensor: 'VIIRS_SNPP',
      reference_sensor: 'MODIS_AQUA',
      reason: 'Validated quantile_mapping model applied for VIIRS_SNPP -> MODIS_AQUA.',
    },
    sensor_transitions: [
      {
        sensor_code: 'VIIRS_SNPP',
        transition_type: 'sensor_operational_start',
        note: 'VIIRS_SNPP operational archive began 2012-01-20; 2012-01 is a partial start month.',
      },
    ],
    sources: [],
    monthly: [
      {
        sensor_code: query.sensors[0],
        month: '2014-07',
        count: 8,
        completeness: 'complete',
        archive_completeness: 'complete',
        observation_coverage: 'unknown',
        missing_data_status: 'complete_insufficient_baseline',
        missing_data_reason: 'Only 1 of 5 required prior complete reference years available.',
        comparison_series: 'validated_harmonized',
        comparison_value: 4,
        harmonized_value: 4,
        historical_median: null,
        baseline_size: 1,
        baseline_period: '2013–2013',
        min_baseline_years: 5,
        lower_threshold: null,
        upper_threshold: null,
        anomaly_status: 'insufficient_history',
        robust_z: null,
        year_over_year: { difference: 0, percent_change: 0 },
        limitations: ['Only 1 of 5 required prior complete reference years available.'],
      },
      {
        sensor_code: query.sensors[0],
        month: '2018-07',
        count: 60,
        completeness: 'complete',
        archive_completeness: 'complete',
        observation_coverage: 'unknown',
        missing_data_status: 'complete_assessed',
        missing_data_reason: 'Archive month is complete with 5 prior complete reference years (2013–2017).',
        comparison_series: 'validated_harmonized',
        comparison_value: 30,
        harmonized_value: 30,
        historical_median: 12,
        baseline_size: 5,
        baseline_period: '2013–2017',
        min_baseline_years: 5,
        lower_threshold: 6,
        upper_threshold: 22,
        anomaly_status: 'unusually_high',
        robust_z: 2.9,
        year_over_year: { difference: 15, percent_change: 100 },
        limitations: ['Archive completeness is distinct from satellite observation coverage (swath, cloud, smoke), which is unknown.'],
      },
    ],
    yearly: [],
    seasonal_profiles: [],
    spatial: { features: [] },
    concentration: [],
    metric_explanations: {},
  } as unknown as HistoryResult));
  render(<MemoryRouter><History /></MemoryRouter>);
  fireEvent.click(screen.getByRole('button', { name: 'Analyze archive' }));
  expect(await screen.findByText('Selected month comparison · 2018-07')).toBeTruthy();
  expect(screen.getAllByText('2013–2017').length).toBeGreaterThan(0);
  expect(screen.getByText('5 (min 5)')).toBeTruthy();
  expect(screen.getByText(`Validated harmonized (${(30).toLocaleString()})`)).toBeTruthy();
  expect(screen.getByText(/Validated quantile_mapping model applied/)).toBeTruthy();
  expect(screen.getByText(/VIIRS_SNPP operational archive began 2012-01-20/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Selected comparison month'), { target: { value: '2014-07' } });
  expect(screen.getByText('Selected month comparison · 2014-07')).toBeTruthy();
  expect(screen.getAllByText('Archive complete · insufficient baseline').length).toBeGreaterThan(0);
});
