import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import type { HistoryResult } from '../history';
import HistoryTrend from './HistoryTrend';

vi.mock('./ScientificChart', () => ({ default: ({ series }: { series: unknown }) => <pre data-testid="series">{JSON.stringify(series)}</pre> }));

it('plots the comparison measure against its median and never substitutes a native count', () => {
  const result = { monthly: [
    { sensor_code: 'VIIRS_SNPP', month: '2024-01', count: 100, comparison_series: 'validated_harmonized', comparison_value: 50, historical_median: 20, upper_threshold: 40 },
    { sensor_code: 'VIIRS_SNPP', month: '2024-02', count: 200, comparison_series: 'validated_harmonized', comparison_value: null, historical_median: null, upper_threshold: null },
  ] } as HistoryResult;
  render(<HistoryTrend result={result} sensor="VIIRS_SNPP" />);
  const series = JSON.parse(screen.getByTestId('series').textContent!);
  expect(series[0].values).toEqual([50, null]);
  expect(series[0].name).toContain('reference sensor equivalent');
  expect(series[1].values).toEqual([20, null]);
});
