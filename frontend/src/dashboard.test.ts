import { expect, it } from 'vitest';
import { boundsRegion, historySelection, parseBounds } from './dashboard';
import type { Query } from './types';

it('preserves wrapped geographic bounds without creating a globe-spanning polygon', () => {
  const bounds = parseBounds('170,-10,-170,10');
  const area = boundsRegion(bounds);
  expect(area.type).toBe('MultiPolygon');
  expect(area.coordinates).toHaveLength(2);
});
it.each(['34,,40,34', 'nan,29,40,34', '-190,29,40,34', '34,34,40,29', '34,29,34,34'])('rejects invalid bounds %s', value => {
  expect(() => parseBounds(value)).toThrow();
});
it('uses equivalent whole-year context without leaking an exclusive January boundary into the next year', () => {
  const query = { start: '2024-02-10T00:00:00Z', end: '2025-01-01T00:00:00Z', bbox: [34,29,40,34], sensors: ['VIIRS_SNPP'], limit: 2000 } as Query;
  expect(historySelection(query, 95, 5, '[]')).toMatchObject({ start_year: 2024, end_year: 2024, sensors: ['VIIRS_SNPP'], complete_months: [] });
  expect(() => historySelection(query, 100, 5, '[]')).toThrow();
  expect(() => historySelection(query, 95, 2, '[]')).toThrow();
  expect(() => historySelection(query, 95, 5, '{}')).toThrow();
});
