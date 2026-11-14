import type { ErrorEvent, Map, MapSourceDataEvent } from 'maplibre-gl';
import { mapStyle } from './mapStyle';
import type { Region } from './dashboard';

const localSources = new Set(['observations', 'selection']);

export function frameRegion(map: Map, region: Region) {
  const coordinates = region.type === 'Polygon'
    ? (region.coordinates as number[][][]).flat()
    : (region.coordinates as number[][][][]).flat(2);
  if (!coordinates.length) return;
  const longitudes = coordinates.map(point => point[0]);
  let west = Math.min(...longitudes), east = Math.max(...longitudes);
  if (east - west > 180) {
    const shifted = longitudes.map(lng => lng < 0 ? lng + 360 : lng);
    const shiftedWest = Math.min(...shifted), shiftedEast = Math.max(...shifted);
    if (shiftedEast > shiftedWest && shiftedEast - shiftedWest < east - west) { west = shiftedWest; east = shiftedEast; }
  }
  const latitudes = coordinates.map(point => point[1]);
  map.fitBounds([[west, Math.min(...latitudes)], [east, Math.max(...latitudes)]], { padding: 40, maxZoom: 10, duration: 0 });
}

/** Keep tile failures separate from the archive layers and allow the style to recover. */
export function watchBasemap(map: Map, onProblem: (message: string) => void) {
  let timer: ReturnType<typeof setTimeout>;
  const successful = new Set<string>();
  const failed = new Set<string>();
  const sourceIds = () => Object.keys(map.getStyle()?.sources ?? {}).filter(id => !localSources.has(id));
  const armTimeout = () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (sourceIds().some(id => !successful.has(id))) onProblem('Map tiles are taking longer to load.');
    }, 20000);
  };
  const onStyle = () => {
    successful.clear(); failed.clear(); onProblem(''); armTimeout();
  };
  const onError = (event: ErrorEvent & { sourceId?: string }) => {
    if (event.sourceId && localSources.has(event.sourceId)) return;
    failed.add(event.sourceId ?? 'style');
    onProblem('Some map tiles could not load.');
  };
  const onSource = (event: MapSourceDataEvent) => {
    if (localSources.has(event.sourceId)) return;
    // Raster tile completion events have a tile but no sourceDataType. The
    // source-level "content" event only means its TileJSON metadata is ready.
    const tileLoaded = event.tile?.state === 'loaded';
    const contentLoaded = !event.tile && event.sourceDataType === 'content' && event.isSourceLoaded
      && event.source?.type !== 'raster' && event.source?.type !== 'vector';
    if (!tileLoaded && !contentLoaded) return;
    successful.add(event.sourceId); failed.delete(event.sourceId);
    if (sourceIds().every(id => successful.has(id)) && !failed.size) {
      clearTimeout(timer); onProblem('');
    }
  };
  map.on('style.load', onStyle);
  map.on('error', onError);
  map.on('sourcedata', onSource);
  armTimeout();
  return {
    retry() {
      successful.clear(); failed.clear(); onProblem(''); armTimeout();
      map.setStyle(mapStyle(), { diff: false });
    },
    dispose() {
      clearTimeout(timer);
      map.off('style.load', onStyle);
      map.off('error', onError);
      map.off('sourcedata', onSource);
    },
  };
}
