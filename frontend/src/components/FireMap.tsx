import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import type { GeoJSONSource, MapLayerMouseEvent } from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';
import { Crosshair, Maximize2, RefreshCw } from 'lucide-react';
import { mapStyle } from '../mapStyle';
import { watchBasemap } from '../basemap';
import type { ObservationProperties, Observations } from '../types';
import 'maplibre-gl/dist/maplibre-gl.css';
import { visualTheme as theme } from '../visualTheme';

const empty: FeatureCollection = { type: 'FeatureCollection', features: [] };

type Props = {
  data: Observations | null;
  onBounds: (bbox: [number, number, number, number]) => void;
  onSelect: (observation: ObservationProperties) => void;
};

export default function FireMap({ data, onBounds, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const retryBasemap = useRef<(() => void) | null>(null);
  const latest = useRef({ data, onSelect });
  latest.current = { data, onSelect };
  const [mapError, setMapError] = useState('');

  useEffect(() => {
    if (!container.current) return;
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container: container.current,
        style: mapStyle(),
        center: [24, 12], zoom: 1.7, minZoom: 0.8,
        renderWorldCopies: false, attributionControl: { compact: true },
      });
    } catch {
      setMapError('Interactive map unavailable.');
      return;
    }
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
    const basemap = watchBasemap(map, setMapError);
    retryBasemap.current = basemap.retry;
    map.on('style.load', () => {
      if (map.getSource('observations')) return;
      map.addSource('observations', { type: 'geojson', data: latest.current.data ?? empty });
      map.addLayer({
        id: 'observations', type: 'circle', source: 'observations',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 3, 8, 6],
          'circle-color': ['match', ['get', 'sensor_code'], 'MODIS_TERRA', theme.orange, 'MODIS_AQUA', theme.orange, theme.viirs],
          'circle-opacity': 0.85, 'circle-stroke-width': 1, 'circle-stroke-color': '#ffffff55',
        },
      });
    });
    map.on('click', 'observations', (event: MapLayerMouseEvent) => {
      const properties = event.features?.[0]?.properties;
      if (properties) latest.current.onSelect(properties as ObservationProperties);
    });
    map.on('mouseenter', 'observations', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'observations', () => { map.getCanvas().style.cursor = ''; });
    const resize = new ResizeObserver(() => map.resize());
    resize.observe(container.current);
    return () => { basemap.dispose(); retryBasemap.current = null; resize.disconnect(); map.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    const source = mapRef.current?.getSource('observations') as GeoJSONSource | undefined;
    source?.setData(data ?? empty);
  }, [data]);

  function selectBounds() {
    const bounds = mapRef.current?.getBounds();
    if (bounds) onBounds([
      Math.max(-180, bounds.getWest()), Math.max(-90, bounds.getSouth()),
      Math.min(180, bounds.getEast()), Math.min(90, bounds.getNorth()),
    ]);
  }

  return <div className={'fire-map' + (mapError ? ' has-map-problem' : '')}>
    <div ref={container} className="map-canvas" aria-label="Interactive satellite fire observation map" />
    <div className="map-topbar">
      <button className="map-action" onClick={selectBounds}><Crosshair size={14} /> Use map bounds</button>
    </div>
    <button className="reset-map" aria-label="Reset map view" title="Reset map view" onClick={() => mapRef.current?.flyTo({ center: [24, 12], zoom: 1.7 })}><Maximize2 size={16} /></button>
    {(!data || data.features.length === 0) && <div className="map-empty">
      <span>No observations displayed</span>
      <small>Try a different area, date range or sensor.</small>
    </div>}
    {mapError && <div className="map-warning" role="status"><span>{mapError}</span>{retryBasemap.current && <button type="button" className="button secondary" onClick={() => retryBasemap.current?.()}><RefreshCw size={14} /> Retry basemap</button>}</div>}
    <div className="map-legend"><span><i className="dot modis" /> MODIS · 1 km</span><span><i className="dot viirs" /> VIIRS · 375 m</span><span className="legend-note">Nominal pixel resolution</span></div>
  </div>;
}
