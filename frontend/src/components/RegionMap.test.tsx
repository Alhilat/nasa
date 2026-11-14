import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import RegionMap from './RegionMap';
import { boundsRegion } from '../dashboard';
import type { Observations } from '../types';
const state = vi.hoisted(() => ({
  handlers: {} as Record<string, (event: unknown) => void>,
  sources: new Set<string>(), setStyle: vi.fn(), fitBounds: vi.fn(), addSource: vi.fn(),
}));
vi.mock('maplibre-gl', () => ({ default: {
  Map: class {
    doubleClickZoom = { enable: vi.fn(), disable: vi.fn() };
    listeners: Record<string, ((event: unknown) => void)[]> = {};
    addControl() {} addLayer() {} remove() {} resize() {}
    addSource(id: string, source: unknown) { state.sources.add(id); state.addSource(id, source); }
    getCanvas() { return { style: {} }; }
    getSource(id: string) { return state.sources.has(id) ? { setData: vi.fn() } : undefined; }
    getStyle() { return { sources: { 'esri-imagery': {}, 'esri-reference': {} } }; }
    getLayer() { return null; }
    fitBounds(...args: unknown[]) { state.fitBounds(...args); }
    setStyle(...args: unknown[]) { state.setStyle(...args); state.sources.clear(); state.handlers['style.load']({}); }
    on(event: string, handler: (event: unknown) => void) {
      (this.listeners[event] ??= []).push(handler);
      state.handlers[event] = data => this.listeners[event]?.forEach(listener => listener(data));
      if (event === 'style.load') handler({});
    }
    off(event: string, handler: (event: unknown) => void) {
      this.listeners[event] = this.listeners[event]?.filter(listener => listener !== handler);
    }
  }, NavigationControl: class {},
} }));

beforeEach(() => {
  vi.clearAllMocks(); state.sources.clear(); state.handlers = {};
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('keeps detections and the selected area through a tile failure and explicit basemap retry', () => {
  const region = boundsRegion([34,29,40,34]);
  const data: Observations = { type: 'FeatureCollection', features: [], metadata: { returned: 0, has_more: false, limit: 2000, offset: 0 } };
  render(<RegionMap data={data} region={region} loading={false} onSelect={vi.fn()} />);
  expect(state.fitBounds).toHaveBeenCalledTimes(1);
  act(() => state.handlers.error({ sourceId: 'esri-imagery', error: new Error('Temporary tile failure') }));
  expect(state.setStyle).not.toHaveBeenCalled();
  expect(state.sources.has('observations')).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Retry basemap' }));
  expect(state.setStyle).toHaveBeenCalledTimes(1);
  expect(state.sources.has('observations')).toBe(true);
  expect(state.sources.has('selection')).toBe(true);
  expect(state.addSource.mock.calls.filter(([id]) => id === 'observations').at(-1)?.[1].data).toEqual(data);
  expect(state.fitBounds).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('button', { name: 'Draw polygon' })).toBeNull();
});
