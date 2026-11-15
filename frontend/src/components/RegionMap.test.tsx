import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import RegionMap from './RegionMap';
import { boundsRegion } from '../dashboard';
import type { Observations } from '../types';
const state = vi.hoisted(() => ({
  handlers: {} as Record<string, (event: unknown) => void>,
  sources: new Set<string>(), addLayer: vi.fn(), queryRenderedFeatures: vi.fn(), canvas: null as HTMLCanvasElement | null, setStyle: vi.fn(), fitBounds: vi.fn(), addSource: vi.fn(),
}));
vi.mock('maplibre-gl', () => ({ default: {
  Map: class {
    doubleClickZoom = { enable: vi.fn(), disable: vi.fn() };
    listeners: Record<string, ((event: unknown) => void)[]> = {};
    addControl() {} addLayer(layer: unknown) { state.addLayer(layer); } remove() {} resize() {}
    addSource(id: string, source: unknown) { state.sources.add(id); state.addSource(id, source); }
    getCanvas() { return state.canvas!; }
    getSource(id: string) { return state.sources.has(id) ? { setData: vi.fn() } : undefined; }
    getStyle() { return { sources: { 'esri-imagery': {}, 'esri-reference': {} } }; }
    getLayer() { return {}; }
    queryRenderedFeatures() { return state.queryRenderedFeatures(); }
    getBounds() { return { getWest: () => 34, getSouth: () => 29, getEast: () => 40, getNorth: () => 34 }; }
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
  state.canvas = document.createElement('canvas');
  state.queryRenderedFeatures.mockReturnValue([]);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('keeps detections and the selected area through a tile failure and explicit basemap retry', () => {
  const region = boundsRegion([34,29,40,34]);
  const data: Observations = { type: 'FeatureCollection', features: [], metadata: { returned: 0, has_more: false, limit: 2000, offset: 0 } };
  render(<RegionMap data={data} region={region} loading={false} onSelect={vi.fn()} onRegion={vi.fn()} onClear={vi.fn()} />);
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
  expect(screen.getByRole('button', { name: 'Draw polygon' })).toBeTruthy();
});

it('restores rectangle and polygon drawing, cancel and clear around the existing layers', () => {
  const onRegion = vi.fn(), onClear = vi.fn();
  const { container } = render(<RegionMap data={null} region={boundsRegion([34,29,40,34])} loading={false} onSelect={vi.fn()} onRegion={onRegion} onClear={onClear} />);
  expect(container.querySelector('.map-stage > .map-canvas')).toBeTruthy();
  expect(container.querySelector('.map-stage .map-tools')).toBeNull();
  const clickPoint = (lng: number, lat: number) => act(() => state.handlers.click({ point: {}, lngLat: { lng, lat } }));
  fireEvent.click(screen.getByRole('button', { name: 'Rectangle' }));
  clickPoint(35,30); clickPoint(37,32);
  expect(onRegion).toHaveBeenLastCalledWith(boundsRegion([35,30,37,32]));
  fireEvent.click(screen.getByRole('button', { name: 'Draw polygon' }));
  clickPoint(35,30); clickPoint(37,30); clickPoint(36,32);
  fireEvent.click(screen.getByRole('button', { name: 'Finish' }));
  expect(onRegion).toHaveBeenLastCalledWith({ type: 'Polygon', coordinates: [[[35,30],[37,30],[36,32],[35,30]]] });
  fireEvent.click(screen.getByRole('button', { name: 'Draw polygon' }));
  fireEvent.click(screen.getByRole('button', { name: 'Cancel drawing' }));
  expect(screen.queryByRole('button', { name: 'Finish' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Map bounds' }));
  expect(onRegion).toHaveBeenLastCalledWith(boundsRegion([34,29,40,34]));
  fireEvent.click(screen.getByRole('button', { name: 'Clear region' }));
  expect(onClear).toHaveBeenCalledTimes(1);
  expect(state.addLayer).toHaveBeenCalledWith(expect.objectContaining({ id: 'observations', source: 'observations', type: 'circle' }));
});

it('retains observation selection with original properties and coordinates after drawing is cancelled', () => {
  const onSelect = vi.fn();
  render(<RegionMap data={null} region={null} loading={false} onSelect={onSelect} onRegion={vi.fn()} onClear={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: 'Draw polygon' }));
  fireEvent.keyDown(screen.getByRole('button', { name: 'Cancel drawing' }), { key: 'Escape' });
  state.queryRenderedFeatures.mockReturnValue([{ geometry: { type: 'Point', coordinates: [35,31] }, properties: { id: 1, uncertainty: '{"coverage":"unknown"}' } }]);
  act(() => state.handlers.click({ point: {}, lngLat: { lng: 35, lat: 31 } }));
  expect(onSelect).toHaveBeenCalledWith({ id: 1, uncertainty: { coverage: 'unknown' }, coordinates: [35,31] });
});

it('restores PNG download with basemap attribution and applied scientific scope', () => {
  const fillText = vi.fn();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ measureText: () => ({ width: 0 }), fillRect: vi.fn(), drawImage: vi.fn(), fillText } as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/png;base64,c3ludGhldGlj');
  const download = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  render(<RegionMap data={null} region={null} loading={false} onSelect={vi.fn()} onRegion={vi.fn()} onClear={vi.fn()} scopeLabel="Synthetic software test scope" />);
  fireEvent.click(screen.getByRole('button', { name: 'Export displayed map as PNG' }));
  expect(download).toHaveBeenCalledTimes(1);
  expect(fillText).toHaveBeenCalledWith('Synthetic software test scope', expect.any(Number), expect.any(Number));
  expect(fillText.mock.calls.some(([line]) => line.includes('Basemap attribution'))).toBe(true);
});
