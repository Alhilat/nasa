import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import type { GeoJSONSource, MapLayerMouseEvent } from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';
import { Crosshair, Maximize2 } from 'lucide-react';
import type { ObservationProperties, Observations } from '../types';
import 'maplibre-gl/dist/maplibre-gl.css';

const empty: FeatureCollection = { type: 'FeatureCollection', features: [] };

type Props = {
  data: Observations | null;
  onBounds: (bbox: [number, number, number, number]) => void;
  onSelect: (observation: ObservationProperties) => void;
};

export default function FireMap({ data, onBounds, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const latest = useRef({ data, onSelect });
  latest.current = { data, onSelect };
  const [mapError, setMapError] = useState(false);

  useEffect(() => {
    if (!container.current) return;
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container: container.current,
        style: import.meta.env.VITE_MAP_STYLE_URL ?? 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
        center: [24, 12], zoom: 1.7, minZoom: 0.8,
        renderWorldCopies: false, attributionControl: { compact: true },
      });
    } catch {
      setMapError(true);
      return;
    }
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
    map.on('error', () => setMapError(true));
    map.on('load', () => {
      map.addSource('observations', { type: 'geojson', data: latest.current.data ?? empty });
      map.addLayer({
        id: 'observations', type: 'circle', source: 'observations',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 3, 8, 6],
          'circle-color': ['match', ['get', 'sensor_code'], 'MODIS_TERRA', '#ffb65c', 'MODIS_AQUA', '#ffb65c', '#f36943'],
          'circle-opacity': 0.85, 'circle-stroke-width': 1, 'circle-stroke-color': '#ffffff55',
        },
      });
      map.on('click', 'observations', (event: MapLayerMouseEvent) => {
        const properties = event.features?.[0]?.properties;
        if (properties) latest.current.onSelect(properties as ObservationProperties);
      });
      map.on('mouseenter', 'observations', () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', 'observations', () => { map.getCanvas().style.cursor = ''; });
    });
    const resize = new ResizeObserver(() => map.resize());
    resize.observe(container.current);
    return () => { resize.disconnect(); map.remove(); mapRef.current = null; };
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

  return <div className="fire-map">
    <div ref={container} className="map-canvas" aria-label="Interactive satellite fire observation map" />
    <div className="map-topbar">
      <span className="map-badge"><span className="status-dot" /> OBSERVATION MAP</span>
      <button className="map-action" onClick={selectBounds}><Crosshair size={14} /> Use map bounds</button>
    </div>
    <button className="reset-map" aria-label="Reset map view" title="Reset map view" onClick={() => mapRef.current?.flyTo({ center: [24, 12], zoom: 1.7 })}><Maximize2 size={16} /></button>
    {(!data || data.features.length === 0) && <div className="map-empty">
      <span className="map-crosshair">+</span><span>No observations displayed</span>
      <small>Connect an archive, then apply your filters</small>
    </div>}
    {mapError && <div className="map-warning" role="status">Basemap unavailable. Check connectivity or configure a local map style.</div>}
    <div className="map-legend"><span><i className="dot modis" /> MODIS · 1 km</span><span><i className="dot viirs" /> VIIRS · 375 m</span><span className="legend-note">Nominal pixel resolution</span></div>
  </div>;
}
