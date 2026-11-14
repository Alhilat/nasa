import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import type { GeoJSONSource, MapMouseEvent } from 'maplibre-gl';
import type { FeatureCollection, Geometry } from 'geojson';
import { Maximize2, RefreshCw } from 'lucide-react';
import { mapStyle } from '../mapStyle';
import { frameRegion, watchBasemap } from '../basemap';
import type { Region } from '../dashboard';
import type { ObservationProperties, Observations } from '../types';
import 'maplibre-gl/dist/maplibre-gl.css';

const empty: FeatureCollection = { type: 'FeatureCollection', features: [] };
export default function RegionMap({ data, region, loading, onSelect }: {
  data: Observations | null; region: Region | null; loading: boolean;
  onSelect: (row: ObservationProperties) => void;
}) {
  const container = useRef<HTMLDivElement>(null), mapRef = useRef<maplibregl.Map | null>(null);
  const retryBasemap = useRef<(() => void) | null>(null), framedRegion = useRef<Region | null>(null);
  const latest = useRef({ data, region, onSelect }); latest.current = { data, region, onSelect };
  const [error, setError] = useState(''), [ready, setReady] = useState(false);

  function paintRegion(geometry: Region | null = latest.current.region) {
    const source = mapRef.current?.getSource('selection') as GeoJSONSource | undefined;
    source?.setData({ type: 'FeatureCollection', features: geometry ? [{ type: 'Feature', properties: {}, geometry: geometry as Geometry }] : [] });
  }
  useEffect(() => {
    if (!container.current) return;
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({ container: container.current, style: mapStyle(), center: [36.5, 31.5], zoom: 5, renderWorldCopies: false,
        canvasContextAttributes: { preserveDrawingBuffer: true }, attributionControl: { compact: true } });
    } catch { setError('Interactive map unavailable.'); return; }
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
    const basemap = watchBasemap(map, setError);
    retryBasemap.current = () => { setReady(false); basemap.retry(); };
    let initializedView = false;
    map.on('style.load', () => {
      if (map.getSource('observations')) return;
      map.addSource('observations', { type: 'geojson', data: latest.current.data ?? empty });
      map.addSource('selection', { type: 'geojson', data: empty });
      map.addLayer({ id: 'selection-fill', type: 'fill', source: 'selection', filter: ['==', '$type', 'Polygon'], paint: { 'fill-color': '#f5ad42', 'fill-opacity': 0.08 } });
      map.addLayer({ id: 'selection-line', type: 'line', source: 'selection', paint: { 'line-color': '#f5ad42', 'line-width': 2, 'line-dasharray': [3, 2] } });
      map.addLayer({ id: 'observations', type: 'circle', source: 'observations', paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 3, 10, 7],
        'circle-color': ['match', ['get', 'sensor_code'], 'MODIS_TERRA', '#f8bf60', 'MODIS_AQUA', '#f8bf60', '#f47f59'],
        'circle-opacity': 0.85, 'circle-stroke-color': '#ffe8ca80', 'circle-stroke-width': 0.5,
      } });
      setReady(true); paintRegion();
      if (!initializedView && latest.current.region) { frameRegion(map, latest.current.region); framedRegion.current = latest.current.region; }
      initializedView = true;
    });
    map.on('click', (event: MapMouseEvent) => {
      const feature = map.getLayer('observations') && map.queryRenderedFeatures(event.point, { layers: ['observations'] })[0];
      if (feature?.properties) {
        const props = { ...feature.properties } as ObservationProperties;
        if (feature.geometry.type === 'Point') props.coordinates = feature.geometry.coordinates.slice(0, 2) as [number, number];
        if (typeof props.uncertainty === 'string') { try { props.uncertainty = JSON.parse(props.uncertainty); } catch { props.uncertainty = {}; } }
        latest.current.onSelect(props);
      }
    });
    const observer = new ResizeObserver(() => map.resize()); observer.observe(container.current);
    return () => { basemap.dispose(); retryBasemap.current = null; observer.disconnect(); map.remove(); mapRef.current = null; };
  }, []);
  useEffect(() => { (mapRef.current?.getSource('observations') as GeoJSONSource | undefined)?.setData(data ?? empty); }, [data, ready]);
  useEffect(() => {
    paintRegion(region);
    if (ready && mapRef.current && region && region !== framedRegion.current) frameRegion(mapRef.current, region);
    if (ready) framedRegion.current = region;
  }, [region, ready]);
  return <div className={'region-map' + (error ? ' has-map-problem' : '')}>
    <div ref={container} className="map-canvas" aria-label="Interactive thermal detection map" />
    <button className="reset-map icon-button" title="Fit selected area" aria-label="Reset map view" onClick={() => { const map = mapRef.current; if (map) { if (latest.current.region) frameRegion(map, latest.current.region); else map.flyTo({ center: [36.5, 31.5], zoom: 5 }); } }}><Maximize2 size={16} /></button>
    {error && <div className="map-warning" role="status"><span>{error}</span>{retryBasemap.current && <button type="button" className="button secondary" onClick={() => retryBasemap.current?.()}><RefreshCw size={14} /> Retry basemap</button>}</div>}
    {!ready && !error && <p className="map-notice" role="status">Loading basemap…</p>}
    <div className="map-legend"><span><i className="dot modis" /> MODIS · 1 km</span><span><i className="dot viirs" /> VIIRS · 375 m</span><span>{loading ? 'Loading observations…' : data ? `${data.metadata.returned.toLocaleString()} displayed${data.metadata.has_more ? ' · page capped' : ''}` : 'No observations loaded'}</span></div>
  </div>;
}
