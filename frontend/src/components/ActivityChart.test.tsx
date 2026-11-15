import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import ActivityChart from './ActivityChart';
import type { Summary } from '../types';
import { sensorColor } from '../colorScales';

const state = vi.hoisted(() => ({ option: {} as { series?: { name: string; symbol: string; itemStyle: { color: string }; data: (number | null)[] }[] } }));
vi.mock('echarts/core', () => ({ use: vi.fn(), init: () => ({ setOption: (option: typeof state.option) => { state.option = option; }, resize: vi.fn(), dispose: vi.fn() }) }));
beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it('shares sensor colors, uses distinct marker shapes, and preserves unknown sensor-day gaps', () => {
  render(<ActivityChart summary={{ daily: [
    { day: '2024-01-01', sensor_code: 'MODIS_TERRA', count: 2 },
    { day: '2024-01-02', sensor_code: 'VIIRS_SNPP', count: 5 },
  ] } as Summary} />);
  const [modis, viirs] = state.option.series!;
  expect(modis.itemStyle.color).toBe(sensorColor('MODIS_TERRA'));
  expect(viirs.itemStyle.color).toBe(sensorColor('VIIRS_SNPP'));
  expect(modis.symbol).not.toBe(viirs.symbol);
  expect(modis.data).toEqual([2, null]); expect(viirs.data).toEqual([null, 5]);
});
