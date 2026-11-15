import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import Sources from './Sources';
import { api, request } from '../api';
import * as echarts from 'echarts/core';
import { downloadArtifact } from '../history';

vi.mock('../history', () => ({ downloadArtifact: vi.fn() }));
vi.mock('../api', () => ({ api: { sources: vi.fn(), jobs: vi.fn() }, request: vi.fn() }));
vi.mock('echarts/core', () => ({
  use: vi.fn(),
  getInstanceByDom: vi.fn(),
  connect: vi.fn(),
  disconnect: vi.fn(),
}));
vi.mock('../components/ScientificChart', () => ({
  default: ({ title, series }: { title: string; series: unknown }) => (
    <div aria-label={title}>
      <div className="scientific-chart">{JSON.stringify(series)}</div>
    </div>
  ),
}));
// Isolated synthetic UI transport fixtures. Application results come from verified backend artifacts.
function validationFixture() {
  const score = { n: 1, mae: 0.04, rmse: 0.06, bias: 0.003 };
  return {
    version: 'harmonization-evidence-v1',
    analysis_id: 'synthetic-validation-id',
    study_id: 'synthetic-study',
    study: 'jordan',
    method: 'regression',
    model_version: 'synthetic-model',
    split: 'test_years',
    source_sensor: 'VIIRS_SNPP',
    reference_sensor: 'MODIS_AQUA',
    grid_size_m: 5000,
    daynight: 'D',
    units: 'reported flagged-cell days per 1,000 km² per month',
    paired_bins: 1,
    unpaired_bins: 1,
    protocol: {
      train_years: [2013, 2014, 2015],
      validation_years: [2020, 2021],
      test_years: [2022, 2023, 2024, 2025],
      heldout_regions: ['test-holdout'],
    },
    metrics: {
      baseline: { ...score, mae: 0.3 },
      candidate: score,
      candidate_intervals_95: { available: false },
    },
    regions: [
      {
        id: 'test-region',
        label: 'Test study region',
        labels: ['2024-01', '2024-02'],
        source: [0.3, null],
        reference: [0.04, null],
        candidate: [0.05, null],
        baseline: score,
        calibrated: score,
      },
    ],
    quarterly: [{ quarter: 1, baseline: score, candidate: score }],
    trend: { available: false, mean_slope_error: null, mean_baseline_slope_error: null },
    seasonal_profile: { available: false },
    limitations_or_rejection_reasons: ['test_years:trend_not_estimable'],
    limitations: ['Test-only evidence limitation.'],
    source_files: [],
    artifacts: [],
  };
}
function mockEngineResponse(value: unknown) {
  vi.mocked(request).mockImplementation((path) =>
    Promise.resolve(path.includes('/validation?') ? validationFixture() : value),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockEngineResponse({
    summary: { input_detections: 0, accepted_detections: 0, unified_cell_days: 0 },
    annual: [],
    monthly: [],
    cells: [],
    sources: [],
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.mocked(echarts.getInstanceByDom).mockReset();
});

const source = {
  id: 'test-source',
  sha256: 'a'.repeat(64),
  original_filename: 'test-firms.csv',
  sensor_code: 'MODIS',
  source_url: 'https://example.org/source',
  product_version: 'native',
  processing_level: 'standard',
  retrieved_at: '2025-01-01T00:00:00Z',
  imported_at: '2025-01-01T00:00:00Z',
  row_count: 1,
};

async function openArchive(writeText: ReturnType<typeof vi.fn>) {
  vi.mocked(api.sources).mockResolvedValue({ items: [source], has_more: false });
  vi.mocked(api.jobs).mockResolvedValue([]);
  vi.stubGlobal('navigator', { clipboard: { writeText } });
  render(<Sources />);
  fireEvent.click(screen.getByText('Source archive & processing history'));
  fireEvent.click(
    await screen.findByRole('button', { name: 'Copy SHA-256 for test-firms.csv' }, { timeout: 5000 }),
  );
}

it('confirms a successful source checksum copy', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  await openArchive(writeText);
  expect(await screen.findByText('Checksum copied for test-firms.csv.')).toBeTruthy();
  expect(writeText).toHaveBeenCalledWith(source.sha256);
});

it('offers the full selectable checksum when clipboard access is denied', async () => {
  await openArchive(vi.fn().mockRejectedValue(new DOMException('Denied', 'NotAllowedError')));
  expect(await screen.findByText(/Clipboard access is unavailable/)).toBeTruthy();
  expect(screen.getByText(source.sha256)).toBeTruthy();
  expect(
    screen.getByText(/Clipboard access is unavailable/).closest('[role="status"]')?.textContent,
  ).toContain(source.sha256);
});

it('uses native confidence defaults and refetches the same geographic area when controls change', async () => {
  render(<Sources />);
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      '/analytics/harmonization',
      expect.any(AbortSignal),
      expect.objectContaining({
        year: 2024,
        month: 7,
        sensor_family: 'both',
        modis_confidence_min: 50,
        viirs_confidence: 'nominal_high',
        bbox: [34, 29, 40, 34],
      }),
    ),
  );
  fireEvent.change(screen.getByLabelText('Sensor family'), { target: { value: 'VIIRS' } });
  fireEvent.change(screen.getByLabelText('Year'), { target: { value: '2020' } });
  fireEvent.change(screen.getByLabelText('Calendar month'), { target: { value: '3' } });
  fireEvent.change(screen.getByLabelText('MODIS minimum confidence'), { target: { value: '80' } });
  fireEvent.change(screen.getByLabelText('VIIRS confidence'), { target: { value: 'high' } });
  await waitFor(() =>
    expect(request).toHaveBeenLastCalledWith(
      '/analytics/harmonization',
      expect.any(AbortSignal),
      expect.objectContaining({
        year: 2020,
        month: 3,
        sensor_family: 'VIIRS',
        modis_confidence_min: 80,
        viirs_confidence: 'high',
        bbox: [34, 29, 40, 34],
      }),
    ),
  );
});

it('supports keyboard navigation through all pipeline stages and explains the approximate grid', async () => {
  render(<Sources />);
  const first = screen.getByRole('tab', { name: /Confidence filtering/ });
  fireEvent.keyDown(first, { key: 'ArrowRight' });
  expect(screen.getByRole('tab', { name: /Schema alignment/ }).getAttribute('aria-selected')).toBe('true');
  fireEvent.click(screen.getByRole('tab', { name: /Spatial harmonization/ }));
  expect(screen.getByText(/grid_lat = Math.round/).textContent).toContain(
    'Math.round(longitude * 100) / 100',
  );
  expect(screen.getByText(/Angular cell dimensions vary/)).toBeTruthy();
  fireEvent.keyDown(screen.getByRole('tab', { name: /Spatial harmonization/ }), { key: 'End' });
  expect(screen.getByRole('tab', { name: /Historical overlap/ }).getAttribute('aria-selected')).toBe('true');
  await screen.findByText(/No archived observations match/);
});

it('shows request failures and retries without filling scientific charts', async () => {
  vi.mocked(request).mockImplementation((path) =>
    path.includes('/validation?')
      ? Promise.resolve(validationFixture())
      : Promise.reject(new Error('Archive offline')),
  );
  render(<Sources />);
  expect((await screen.findByRole('alert')).textContent).toContain('Archive offline');
  expect(screen.getByLabelText('Before harmonization').textContent).toContain('"values":[]');
  expect(screen.getByLabelText('After harmonization').textContent).toContain('"values":[]');
  mockEngineResponse({
    summary: { input_detections: 0 },
    cells: [],
    sources: [],
    annual: [],
    monthly: [],
  });
  fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
  await screen.findByText(/No archived observations match/);
  expect(screen.queryByRole('alert')).toBeNull();
});

it('replays the explicitly illustrative transformation with reduced motion', async () => {
  vi.stubGlobal('matchMedia', () => ({ matches: true }));
  render(<Sources />);
  fireEvent.click(screen.getByRole('button', { name: 'Show the transformation' }));
  await screen.findByRole('button', { name: 'Replay grouping' });
  expect(screen.getByText('1 grid-cell day')).toBeTruthy();
  expect(screen.getByText(/Illustrative geometry/)).toBeTruthy();
});

it('renders backend evidence and switches raw, unified and radiative measurements without estimating gaps', async () => {
  // Synthetic transport fixture, isolated from the running application and scientific archive.
  const period = {
    label: '2024',
    raw_modis: 1,
    raw_viirs: 2,
    accepted_count: 3,
    unified_cell_days: 1,
    frp_before_modis: 4,
    frp_before_viirs: 8,
    frp_after_total: 12,
  };
  mockEngineResponse({
    analysis_id: 'synthetic-ui-test',
    algorithm_version: 'prototype-test',
    sources: [],
    summary: {
      input_detections: 3,
      accepted_detections: 3,
      unified_cell_days: 1,
      rejected_detections: 0,
      retention_percent: 100,
    },
    annual: [
      period,
      {
        ...period,
        label: '2025',
        raw_modis: null,
        raw_viirs: null,
        accepted_count: null,
        unified_cell_days: null,
        frp_after_total: null,
      },
    ],
    monthly: [{ ...period, label: '2024-07' }],
    cells: [
      {
        key: 'test-cell',
        acq_date: '2024-07-01',
        grid_id: '31.95_35.93',
        grid_lat: 31.95,
        grid_lon: 35.93,
        unified_fire_count: 1,
        raw_detections_count: 3,
        total_frp_mw: 12,
        mean_frp_mw: 4,
        frp_known_count: 3,
        max_temp_k: 350,
        temperature_known_count: 3,
        sensors_involved: ['MODIS_TERRA', 'VIIRS_SNPP'],
        day_detections: 2,
        night_detections: 1,
        members: [
          {
            id: 1,
            sensor_code: 'MODIS_TERRA',
            latitude: 31.951,
            longitude: 35.931,
            confidence_native: '80',
            frp_mw: 4,
            brightness_k: 350,
            brightness_field: 'brightness',
            source_id: 'test-source',
            source_row: 5,
          },
        ],
        members_truncated: false,
      },
    ],
  });
  render(<Sources />);
  await screen.findByText('MODIS_TERRA, VIIRS_SNPP');
  expect(screen.getByLabelText('After harmonization').textContent).toContain('"values":[1,null]');
  expect(screen.getByLabelText('Before harmonization').textContent).toContain('"values":[2,null]');
  fireEvent.click(screen.getByRole('button', { name: 'Raw hotspot counts' }));
  expect(screen.getByLabelText('After harmonization').textContent).toContain('"values":[3,null]');
  fireEvent.click(screen.getByRole('button', { name: 'Total FRP (MW)' }));
  expect(screen.getByLabelText('After harmonization').textContent).toContain('"values":[12,null]');
  expect(screen.getByLabelText('Before harmonization').textContent).toContain('MODIS FRP (MW)');
  fireEvent.change(screen.getByLabelText('Time scale'), { target: { value: 'monthly' } });
  expect(screen.getByLabelText('After harmonization').textContent).toContain('"values":[12]');
  fireEvent.click(screen.getByText('Inspect native observations and source rows'));
  expect(screen.getByRole('cell', { name: /test-source/ }).textContent).toContain('Row 5');
  fireEvent.click(screen.getByText('Reproducible analysis metadata & source checksums'));
  expect(screen.getByText(/"analysis_id": "synthetic-ui-test"/)).toBeTruthy();
});

it('links chart instances and annotates the sensor transition even when one chart is unavailable', async () => {
  const chart = { group: '', setOption: vi.fn() };
  vi.mocked(echarts.getInstanceByDom).mockImplementation((node) =>
    node.parentElement?.getAttribute('aria-label') === 'Before harmonization'
      ? (chart as unknown as echarts.ECharts)
      : undefined,
  );
  mockEngineResponse({
    summary: { input_detections: 1 },
    cells: [],
    sources: [],
    monthly: [],
    annual: [
      {
        label: '2012',
        raw_modis: 1,
        raw_viirs: null,
        accepted_count: 0,
        unified_cell_days: 0,
        frp_before_modis: 5,
        frp_before_viirs: null,
        frp_after_total: null,
      },
    ],
  });
  const view = render(<Sources />);
  await waitFor(() =>
    expect(chart.setOption).toHaveBeenCalledWith(
      expect.objectContaining({
        series: [
          expect.objectContaining({
            markLine: expect.objectContaining({
              data: [expect.objectContaining({ xAxis: '2012' })],
            }),
          }),
        ],
      }),
    ),
  );
  expect(echarts.connect).toHaveBeenCalledWith(chart.group);
  view.unmount();
  expect(echarts.disconnect).toHaveBeenCalledWith(chart.group);
});

it('loads the Levant regional holdouts and exports the displayed scientific evidence', async () => {
  mockEngineResponse({ summary: { input_detections: 0 }, annual: [], monthly: [], cells: [], sources: [] });
  render(<Sources />);
  await screen.findByRole('table', { name: /Agreement to MODIS Aqua/ });
  expect(screen.getByLabelText('Regional activity after candidate calibration').textContent).toContain(
    '"values":[0.05,null]',
  );
  fireEvent.change(screen.getByLabelText('Validation study'), { target: { value: 'levant' } });
  fireEvent.change(screen.getByLabelText('Held-out evaluation'), { target: { value: 'test_regions' } });
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      '/analytics/harmonization/validation?study=levant&split=test_regions',
      expect.any(AbortSignal),
    ),
  );
  const button = await screen.findByRole('button', { name: /Export validation evidence/ });
  fireEvent.click(button);
  expect(downloadArtifact).toHaveBeenCalledWith(
    expect.stringContaining('synthetic-validation-id'),
    'pirx-validation-levant-test_regions.json',
    'application/json',
  );
  const payload = JSON.parse(vi.mocked(downloadArtifact).mock.calls[0][0]);
  expect(payload.metrics.candidate.mae).toBe(0.04);
  expect(payload.model_version).toBe('synthetic-model');
});

it('requests the wider live archive extent and retains equivalent-area chart comparisons', async () => {
  render(<Sources />);
  fireEvent.change(screen.getByLabelText('Study area'), { target: { value: 'levant' } });
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      '/analytics/harmonization',
      expect.any(AbortSignal),
      expect.objectContaining({ bbox: [34, 29, 43, 38] }),
    ),
  );
  expect(screen.getByText(/Levant study area · 34°–43°/)).toBeTruthy();
});

it('keeps a failed validation bundle separate from live observations and supports retry', async () => {
  let unavailable = true;
  vi.mocked(request).mockImplementation((path) => {
    if (path.includes('/validation?'))
      return unavailable
        ? Promise.reject(new Error('Bundle verification failed'))
        : Promise.resolve(validationFixture());
    return Promise.resolve({
      summary: { input_detections: 0 },
      annual: [],
      monthly: [],
      cells: [],
      sources: [],
    });
  });
  render(<Sources />);
  expect((await screen.findByRole('alert')).textContent).toContain('Validation evidence unavailable');
  unavailable = false;
  fireEvent.click(screen.getByRole('button', { name: 'Refresh evidence' }));
  await screen.findByRole('table', { name: /Agreement to MODIS Aqua/ });
  expect(screen.queryByRole('alert')).toBeNull();
});
