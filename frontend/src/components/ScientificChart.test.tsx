import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import ScientificChart, { uncertaintyBandSeries } from './ScientificChart';
import { downloadArtifact } from '../history';

const state = vi.hoisted(() => ({ option: null as Record<string, unknown> | null }));
vi.mock('echarts/core', () => ({
  use: vi.fn(),
  init: (target: HTMLElement) => {
    target.append(document.createElementNS('http://www.w3.org/2000/svg', 'svg'));
    return { setOption: (option: Record<string, unknown>) => { state.option = option; }, resize: vi.fn(), dispose: vi.fn() };
  },
}));
vi.mock('../history', () => ({ downloadArtifact: vi.fn() }));
beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

it('recovers SVG download with its metadata and preserves original series and missing values', () => {
  const metadata = { analysis_id: 'synthetic-software-test', sources: [{ id: 'fixture-source' }] };
  render(<ScientificChart title="Test activity" labels={['2013-01','2013-02']} series={[{ name: 'Test observations', values: [2, null], color: '#F47A32' }]} metadata={metadata} />);
  fireEvent.click(screen.getByRole('button', { name: 'Export Test activity as SVG' }));
  const [payload, filename, type] = vi.mocked(downloadArtifact).mock.calls[0];
  expect(filename).toBe('firescope-chart.svg');
  expect(type).toBe('image/svg+xml');
  expect(payload).toContain('Thermal detections, not unique fires or risk forecasts');
  expect(payload).toContain(JSON.stringify(metadata));
  expect(state.option?.series).toMatchObject([{ data: [2, null], connectNulls: false }]);
  fireEvent.click(screen.getByText('View accessible data table'));
  expect(screen.getByRole('cell', { name: 'Unknown' })).toBeTruthy();
});

it('retains the empty chart state and withholds export when every value is missing', () => {
  render(<ScientificChart title="Unknown activity" labels={['2013-01']} series={[{ name: 'Test observations', values: [null], color: '#F47A32' }]} />);
  expect(screen.getByText('No comparable chart values')).toBeTruthy();
  expect(screen.queryByRole('button', { name: /as SVG/ })).toBeNull();
});

it('shades between absolute interval bounds and preserves unsupported gaps', () => {
  const result = uncertaintyBandSeries({ lower: [8, null, 20], upper: [12, null, 30], color: '#8CC4EE' });
  expect(result[0].data).toEqual([8, null, 20]);
  expect(result[1].data).toEqual([4, null, 10]);
  expect(result[1].areaStyle).toMatchObject({ opacity: 0.22 });
  expect(result.every(s => s.connectNulls === false)).toBe(true);
});
