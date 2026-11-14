import { afterEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import RegionMap from './RegionMap';
const state = vi.hoisted(() => ({ handlers: {} as Record<string, (event: unknown) => void> }));
vi.mock('maplibre-gl', () => ({ default: {
  Map: class {
    doubleClickZoom = { enable: vi.fn(), disable: vi.fn() };
    addControl() {} addSource() {} addLayer() {} remove() {} resize() {}
    getCanvas() { return { style: {} }; }
    getSource() { return { setData: vi.fn() }; }
    getLayer() { return null; }
    on(event: string, handler: (event: unknown) => void) { state.handlers[event] = handler; if (event === 'load') handler({}); }
  }, NavigationControl: class {},
} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('draws a closed polygon and supports cancellation without sending phantom regions', () => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  const onRegion = vi.fn();
  render(<RegionMap data={null} region={null} loading={false} onRegion={onRegion} onSelect={vi.fn()} onClear={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: 'Draw polygon' }));
  for (const [lng, lat] of [[35,30], [36,30], [36,31]]) act(() => state.handlers.click({ lngLat: { lng, lat } }));
  fireEvent.click(screen.getByRole('button', { name: 'Finish' }));
  expect(onRegion).toHaveBeenCalledWith({ type: 'Polygon', coordinates: [[[35,30],[36,30],[36,31],[35,30]]] });
  fireEvent.click(screen.getByRole('button', { name: 'Draw polygon' }));
  fireEvent.click(screen.getByRole('button', { name: 'Cancel drawing' }));
  expect(onRegion).toHaveBeenCalledTimes(1);
});
it('draws a rectangle from opposite corners', () => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  const onRegion = vi.fn();
  render(<RegionMap data={null} region={null} loading={false} onRegion={onRegion} onSelect={vi.fn()} onClear={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: 'Rectangle' }));
  for (const [lng, lat] of [[36,32], [35,30]]) act(() => state.handlers.click({ lngLat: { lng, lat } }));
  expect(onRegion).toHaveBeenCalledWith({ type: 'Polygon', coordinates: [[[35,30],[36,30],[36,32],[35,32],[35,30]]] });
});
