import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import Sources from './Sources';
import { api, request } from '../api';
import * as echarts from 'echarts/core';

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
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(request).mockResolvedValue({
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
  vi.mocked(request).mockRejectedValue(new Error('Archive offline'));
  render(<Sources />);
  expect((await screen.findByRole('alert')).textContent).toContain('Archive offline');
  expect(screen.getByLabelText('Before harmonization').textContent).toContain('"values":[]');
  expect(screen.getByLabelText('After harmonization').textContent).toContain('"values":[]');
  vi.mocked(request).mockResolvedValue({
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
  vi.mocked(request).mockResolvedValue({
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
  vi.mocked(request).mockResolvedValue({
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
