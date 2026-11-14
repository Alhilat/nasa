import { afterEach, expect, it, vi } from 'vitest';
import type { Map } from 'maplibre-gl';
import { frameRegion, watchBasemap } from './basemap';
import { boundsRegion } from './dashboard';

function mapDouble() {
  const handlers: Record<string, Set<(event: unknown) => void>> = {};
  const methods = {
    getStyle: () => ({ sources: { 'esri-imagery': {}, 'esri-reference': {} } }),
    setStyle: vi.fn(), fitBounds: vi.fn(),
    on(event: string, handler: (event: unknown) => void) { (handlers[event] ??= new Set()).add(handler); },
    off(event: string, handler: (event: unknown) => void) { handlers[event]?.delete(handler); },
  };
  return { map: methods as unknown as Map, methods,
    emit(event: string, data: unknown) { handlers[event]?.forEach(handler => handler(data)); } };
}
afterEach(() => vi.useRealTimers());

it('never removes a slow or failing basemap and reloads it only on an explicit retry', () => {
  vi.useFakeTimers();
  const { map, methods, emit } = mapDouble(), problem = vi.fn();
  const monitor = watchBasemap(map, problem);
  emit('error', { sourceId: 'esri-imagery' });
  vi.advanceTimersByTime(20001);
  expect(problem).toHaveBeenLastCalledWith('Map tiles are taking longer to load.');
  expect(methods.setStyle).not.toHaveBeenCalled();
  monitor.retry();
  expect(methods.setStyle).toHaveBeenCalledWith(expect.objectContaining({ sources: expect.objectContaining({ 'esri-imagery': expect.anything() }) }), { diff: false });
  monitor.dispose();
});

it('clears tile warnings after successful imagery and label content, rather than failed tiles or archive events', () => {
  const { map, emit } = mapDouble(), problem = vi.fn();
  const monitor = watchBasemap(map, problem);
  emit('error', { sourceId: 'esri-imagery' });
  emit('sourcedata', { sourceId: 'esri-imagery', sourceDataType: 'content', isSourceLoaded: true, tile: { state: 'errored' } });
  emit('sourcedata', { sourceId: 'observations', sourceDataType: 'content', isSourceLoaded: true });
  expect(problem).toHaveBeenLastCalledWith('Some map tiles could not load.');
  for (const sourceId of ['esri-imagery', 'esri-reference']) emit('sourcedata', { sourceId, sourceDataType: 'content', isSourceLoaded: true, source: { type: 'raster' } });
  expect(problem).toHaveBeenLastCalledWith('Some map tiles could not load.');
  for (const sourceId of ['esri-imagery', 'esri-reference']) emit('sourcedata', { sourceId, isSourceLoaded: false, tile: { state: 'loaded' } });
  expect(problem).toHaveBeenLastCalledWith('');
  monitor.dispose();
});

it('ignores archive-layer errors and stops listening after the map is removed', () => {
  vi.useFakeTimers();
  const { map, emit } = mapDouble(), problem = vi.fn();
  const monitor = watchBasemap(map, problem);
  emit('error', { sourceId: 'observations' });
  expect(problem).not.toHaveBeenCalled();
  monitor.dispose();
  emit('error', { sourceId: 'esri-imagery' });
  vi.advanceTimersByTime(20001);
  expect(problem).not.toHaveBeenCalled();
});

it('frames the selected study area and keeps wrapped areas near the antimeridian', () => {
  const { map, methods } = mapDouble();
  frameRegion(map, boundsRegion([34,29,40,34]));
  expect(methods.fitBounds).toHaveBeenLastCalledWith([[34,29],[40,34]], expect.objectContaining({ duration: 0 }));
  frameRegion(map, boundsRegion([170,-10,-170,10]));
  expect(methods.fitBounds).toHaveBeenLastCalledWith([[170,-10],[190,10]], expect.anything());
  frameRegion(map, boundsRegion([-180,-80,180,80]));
  expect(methods.fitBounds).toHaveBeenLastCalledWith([[-180,-80],[180,80]], expect.anything());
});
