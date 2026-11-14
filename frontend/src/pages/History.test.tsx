import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import History from './History';
import { historyRequest } from '../history';
import type { HistoryResult } from '../history';

vi.mock('../components/HistoryTrend', () => ({ default: () => <div>Historical trend chart</div> }));
vi.mock('../history', async importOriginal => ({
  ...await importOriginal<typeof import('../history')>(), historyRequest: vi.fn(),
}));
afterEach(() => cleanup());

it('runs an explicit area/sensor selection and renders unknown counts without zero filling', async () => {
  vi.mocked(historyRequest).mockImplementation(async query => ({
    query, analysis_id: 'synthetic-test-only', algorithm_version: 'test', sources: [],
    monthly: [{ sensor_code: query.sensors[0], month: '2013-01', count: null, completeness: 'unknown',
      historical_median: null, baseline_size: 0, lower_threshold: null, upper_threshold: null,
      anomaly_status: 'incomplete_period', year_over_year: { percent_change: null } }],
    yearly: [], seasonal_profiles: [], spatial: { features: [] }, concentration: [], metric_explanations: {},
  } as unknown as HistoryResult));
  render(<History />);
  fireEvent.click(screen.getByRole('button', { name: 'Analyze archive' }));
  expect(await screen.findByText('Monthly activity calendar and anomalies')).toBeTruthy();
  expect(screen.getAllByText('Unknown').length).toBeGreaterThan(0);
  expect(vi.mocked(historyRequest).mock.calls[0][0]).toMatchObject({
    bbox: [34, 29, 40, 34], sensors: ['MODIS_TERRA'], complete_months: [],
  });
  expect(screen.getByText('incomplete period')).toBeTruthy();
});

it('rejects malformed bounds before sending an analysis request', async () => {
  vi.mocked(historyRequest).mockClear();
  render(<History />);
  fireEvent.change(screen.getByLabelText(/Fixed bounding box/), { target: { value: '34,,40,34' } });
  fireEvent.click(screen.getByRole('button', { name: 'Analyze archive' }));
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Supply four finite bounds: west,south,east,north.');
  expect(historyRequest).not.toHaveBeenCalled();
});
