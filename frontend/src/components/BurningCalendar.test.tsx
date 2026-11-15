import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import BurningCalendar from './BurningCalendar';
import type { HistoryMonth } from '../history';
import { departureColor, readableText, scientificColors } from '../colorScales';

afterEach(cleanup);
const rows = [-20, 0, 20, null].map((departure, i) => ({
  sensor_code: 'MODIS_TERRA', month: `201${6 + i}-01`, count: departure === null ? 5 : 20 + departure,
  completeness: departure === null ? 'unknown' : 'complete', anomaly_status: 'within_range',
  median_comparison: { historical_median: 20, departure, departure_percent: departure === null ? null : departure * 5,
    baseline_size: 3, baseline_years: [2013,2014,2015], status: departure === null ? 'incomplete_archive' : 'assessed', reason: 'Synthetic baseline context.' },
})) as HistoryMonth[];

it('renders signed departures, an explicit zero center, and unassessed cells without color-only meaning', () => {
  const onSelect = vi.fn();
  render(<BurningCalendar rows={rows} sensor="MODIS_TERRA" selected="" onSelect={onSelect} colorMode="median" />);
  const low = screen.getByRole('button', { name: /2016-01, MODIS_TERRA:/ });
  const neutral = screen.getByRole('button', { name: /2017-01, MODIS_TERRA:/ });
  const high = screen.getByRole('button', { name: /2018-01, MODIS_TERRA:/ });
  expect(low.textContent).toBe('−20'); expect(neutral.textContent).toBe('0'); expect(high.textContent).toBe('+20');
  expect(low.style.backgroundColor).not.toBe(high.style.backgroundColor);
  expect(low.style.color).toBe(readableText(departureColor(-20,20)) === '#FFFFFF' ? 'rgb(255, 255, 255)' : 'rgb(0, 0, 0)');
  expect(screen.getByRole('button', { name: /2019-01, MODIS_TERRA:/ }).textContent).toBe('—');
  expect(high.getAttribute('aria-label')).toContain('historical median 20; 3 prior reference years');
  fireEvent.click(high); expect(onSelect).toHaveBeenCalledWith('2018-01');
});
it('retains counts in activity mode and gives missing data a separate fill', () => {
  render(<BurningCalendar rows={rows} sensor="MODIS_TERRA" selected="" onSelect={vi.fn()} />);
  expect(screen.getByRole('button', { name: /2018-01, MODIS_TERRA:/ }).textContent).toBe('40');
  expect(screen.getByRole('button', { name: /2016-02, MODIS_TERRA:/ }).style.backgroundColor).toBe('rgb(24, 35, 52)');
  expect(scientificColors.activity).toHaveLength(5);
});
