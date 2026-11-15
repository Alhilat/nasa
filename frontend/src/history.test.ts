import { afterEach, expect, it, vi } from 'vitest';
import { comparisonLabel, comparisonValue, historyCsv, historyRequest } from './history';
import type { HistoryMonth, HistoryResult, HistoryQuery } from './history';

afterEach(() => vi.unstubAllGlobals());
const query = { start_year: 2013, end_year: 2025, bbox: [34, 29, 40, 34] } as HistoryQuery;

it('preserves unknown months and fixed historical selection at the API boundary', async () => {
  const result = { monthly: [{ count: null, historical_median: null }], query };
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => result });
  vi.stubGlobal('fetch', fetchMock);
  expect(await historyRequest(query)).toEqual(result);
  expect(fetchMock.mock.calls[0][0]).toContain('/analytics/history');
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual(query);
});

it('refuses CSV from a changed archive rather than exporting mismatched analysis', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, headers: new Headers({ 'X-Analysis-ID': 'changed' }) }));
  await expect(historyCsv({ query, analysis_id: 'original' } as HistoryResult)).rejects.toThrow('archive changed');
});

it('downloads CSV only for the displayed analysis identity', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, headers: new Headers({ 'X-Analysis-ID': 'same' }), text: async () => 'month,count\n2013-01,\n' }));
  expect(await historyCsv({ query, analysis_id: 'same' } as HistoryResult)).toContain('2013-01,');
});

it('uses harmonized values consistently and preserves unavailable estimates', () => {
  const row = { count: 100, comparison_value: 50, comparison_series: 'validated_harmonized' } as HistoryMonth;
  expect(comparisonValue(row)).toBe(50);
  expect(comparisonValue({ ...row, comparison_value: null })).toBeNull();
  expect(comparisonLabel([row])).toContain('reference sensor equivalent');
  expect(comparisonValue({ ...row, comparison_series: 'native_sensor', comparison_value: undefined })).toBe(100);
});
