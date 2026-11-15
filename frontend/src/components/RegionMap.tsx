import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import type { GeoJSONSource, MapMouseEvent } from 'maplibre-gl';
import type { FeatureCollection, Geometry } from 'geojson';
import { Check, Crosshair, Download, Maximize2, Pentagon, RefreshCw, SquareDashed, Trash2, X } from 'lucide-react';
import { mapStyle } from '../mapStyle';
import { frameRegion, watchBasemap } from '../basemap';
import { boundsRegion } from '../dashboard';
import type { Region } from '../dashboard';
import type { ObservationProperties, Observations } from '../types';
import 'maplibre-gl/dist/maplibre-gl.css';
import { visualTheme as theme } from '../visualTheme';

const empty: FeatureCollection = { type: 'FeatureCollection', features: [] };
type Mode = 'navigate' | 'polygon' | 'rectangle';
export default function RegionMap({ data, region, loading, scopeLabel = '', onRegion, onSelect, onClear }: {
  data: Observations | null; region: Region | null; loading: boolean;
  onSelect: (row: ObservationProperties) => void; onRegion: (region: Region) => void; onClear: () => void; scopeLabel?: string;
}) {
  const container = useRef<HTMLDivElement>(null), mapRef = useRef<maplibregl.Map | null>(null);
  const retryBasemap = useRef<(() => void) | null>(null), framedRegion = useRef<Region | null>(null);
  const latest = useRef({ data, region, onRegion, onSelect }); latest.current = { data, region, onRegion, onSelect };
  const drawing = useRef<Mode>('navigate'), points = useRef<number[][]>([]);
  const [mode, setMode] = useState<Mode>('navigate'), [pointCount, setPointCount] = useState(0);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [ready, setReady] = useState(false);

  function paintRegion(geometry: Region | null = latest.current.region) {
    const source = mapRef.current?.getSource('selection') as GeoJSONSource | undefined;
    const vertices = points.current.map(coordinates => ({ type: 'Feature' as const, properties: {}, geometry: { type: 'Point' as const, coordinates } }));
    const ring = points.current;
    const draft: Geometry | null = ring.length >= 3 ? { type: 'Polygon', coordinates: [[...ring, ring[0]]] }
      : ring.length === 2 ? { type: 'LineString', coordinates: ring } : null;
    const shape = drawing.current === 'navigate' ? geometry as Geometry | null : draft;
    source?.setData({ type: 'FeatureCollection', features: [
      ...(shape ? [{ type: 'Feature' as const, properties: {}, geometry: shape }] : []), ...vertices,
    ] });
  }

  function setDrawing(next: Mode) {
    drawing.current = next; points.current = []; setPointCount(0); setMode(next); setNotice('');
    if (mapRef.current) {
      mapRef.current.getCanvas().style.cursor = next === 'navigate' ? '' : 'crosshair';
      if (next === 'navigate') mapRef.current.doubleClickZoom.enable();
      else mapRef.current.doubleClickZoom.disable();
    }
    paintRegion();
  }

  function finish() {
    if (points.current.length < 3) return;
    const ring = points.current;
    if (ring.some((p, i) => Math.abs(p[0] - ring[(i + 1) % ring.length][0]) > 180)) {
      setNotice('Split regions at the antimeridian using the GeoJSON field.'); return;
    }
    const geometry: Region = { type: 'Polygon', coordinates: [[...ring, ring[0]]] };
    latest.current.onRegion(geometry); setDrawing('navigate'); paintRegion(geometry);
    setNotice('Region drawn. Apply filters to query it.');
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
      map.addLayer({ id: 'selection-fill', type: 'fill', source: 'selection', filter: ['==', '$type', 'Polygon'], paint: { 'fill-color': theme.reference, 'fill-opacity': 0.08 } });
      map.addLayer({ id: 'selection-line', type: 'line', source: 'selection', paint: { 'line-color': theme.reference, 'line-width': 2, 'line-dasharray': [3, 2] } });
      map.addLayer({ id: 'selection-points', type: 'circle', source: 'selection', filter: ['==', '$type', 'Point'], paint: { 'circle-color': theme.reference, 'circle-radius': 5 } });
      map.addLayer({ id: 'observations', type: 'circle', source: 'observations', paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 3, 10, 7],
        'circle-color': ['match', ['get', 'sensor_code'], 'MODIS_TERRA', theme.orange, 'MODIS_AQUA', theme.orange, theme.viirs],
        'circle-opacity': 0.85, 'circle-stroke-color': '#FFFFFF80', 'circle-stroke-width': 0.5,
      } });
      setReady(true); paintRegion();
      if (!initializedView && latest.current.region) { frameRegion(map, latest.current.region); framedRegion.current = latest.current.region; }
      initializedView = true;
    });
    map.on('click', (event: MapMouseEvent) => {
      if (drawing.current === 'navigate') {
        const feature = map.getLayer('observations') && map.queryRenderedFeatures(event.point, { layers: ['observations'] })[0];
        if (feature?.properties) {
          const props = { ...feature.properties } as ObservationProperties;
          if (feature.geometry.type === 'Point') props.coordinates = feature.geometry.coordinates.slice(0, 2) as [number, number];
          if (typeof props.uncertainty === 'string') { try { props.uncertainty = JSON.parse(props.uncertainty); } catch { props.uncertainty = {}; } }
          latest.current.onSelect(props);
        }
        return;
      }
      const lng = Math.max(-180, Math.min(180, event.lngLat.lng));
      const lat = Math.max(-90, Math.min(90, event.lngLat.lat));
      points.current.push([lng, lat]); setPointCount(points.current.length);
      if (drawing.current === 'rectangle' && points.current.length === 2) {
        const [[x1, y1], [x2, y2]] = points.current;
        if (Math.abs(x1 - x2) > 180) { points.current = []; setPointCount(0); setNotice('For antimeridian regions use wrapped bounds or split GeoJSON in Analysis settings.'); return; }
        if (x1 === x2 || y1 === y2) { points.current = []; setPointCount(0); setNotice('Choose two distinct opposite corners.'); return; }
        const geometry = boundsRegion([Math.min(x1, x2), Math.min(y1, y2), Math.max(x1, x2), Math.max(y1, y2)]);
        latest.current.onRegion(geometry); setDrawing('navigate'); paintRegion(geometry);
        setNotice('Rectangle drawn. Apply filters to query it.');
      } else paintRegion();
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
  function mapBounds() {
    const b = mapRef.current?.getBounds();
    if (!b) return;
    const w = Math.max(-180, b.getWest()), e = Math.min(180, b.getEast());
    const geometry = boundsRegion([w, Math.max(-90, b.getSouth()), e, Math.min(90, b.getNorth())]);
    onRegion(geometry); setDrawing('navigate'); paintRegion(geometry); setNotice('Map extent selected. Apply filters to query it.');
  }
  function exportMap() {
    try {
      const map = mapRef.current;
      if (!map) return;
      const original = map.getCanvas(), canvas = document.createElement('canvas');
      canvas.width = original.width; canvas.height = original.height;
      const context = canvas.getContext('2d'); if (!context) return;
      context.font = '12px IBM Plex Mono, monospace';
      const attribution = Object.values(map.getStyle().sources).map(s => 'attribution' in s ? s.attribution : '').filter(Boolean).join(' • ').replace(/<[^>]+>/g, '');
      const notes = ['FireScope • Displayed page only • Thermal detections, not unique fires or risk forecasts.', scopeLabel,
        'Drawn regions may be pending; apply filters before interpreting the selection.',
        'Basemap attribution: ' + (attribution || 'No basemap attribution supplied by the active style.')];
      const lines: string[] = [];
      for (const note of notes) {
        let line = '';
        for (const word of note.split(' ')) {
          if (line && context.measureText(`${line} ${word}`).width > canvas.width - 24) { lines.push(line); line = word; }
          else line = line ? `${line} ${word}` : word;
        }
        if (line) lines.push(line);
      }
      canvas.height = original.height + lines.length * 18 + 18;
      context.fillStyle = theme.navy; context.fillRect(0, 0, canvas.width, canvas.height); context.drawImage(original, 0, 0);
      context.fillStyle = theme.muted; context.font = '12px IBM Plex Mono, monospace';
      lines.forEach((line, index) => context.fillText(line, 12, original.height + 20 + index * 18));
      const link = document.createElement('a'); link.download = 'firescope-map.png'; link.href = canvas.toDataURL('image/png'); link.click();
    } catch { setNotice('Map export failed. The basemap may restrict image export; analytical CSV and JSON exports are available.'); }
  }
  return <div onKeyDown={e => { if (e.key === 'Escape') setDrawing('navigate'); }} className={'region-map' + (error ? ' has-map-problem' : '')}>
    <div ref={container} className="map-canvas" aria-label="Interactive thermal detection map" />
    <div className="map-tools" aria-label="Region drawing tools">
      <button className={`map-tool ${mode === 'polygon' ? 'active' : ''}`} disabled={!ready} aria-pressed={mode === 'polygon'} onClick={() => setDrawing(mode === 'polygon' ? 'navigate' : 'polygon')}><Pentagon size={15} /> Draw polygon</button>
      <button className={`map-tool ${mode === 'rectangle' ? 'active' : ''}`} disabled={!ready} aria-pressed={mode === 'rectangle'} onClick={() => setDrawing(mode === 'rectangle' ? 'navigate' : 'rectangle')}><SquareDashed size={15} /> Rectangle</button>
      <button className="map-tool" disabled={!ready} onClick={mapBounds}><Crosshair size={15} /> Map bounds</button>
      <button className="map-tool" onClick={() => { setDrawing('navigate'); onClear(); }} aria-label="Clear region"><Trash2 size={15} /></button>
      <button className="map-tool" disabled={!ready} onClick={exportMap} aria-label="Export displayed map as PNG"><Download size={15} /></button>
    </div>
    {mode !== 'navigate' && <div className="drawing-notice" role="status"><span>{mode === 'polygon' ? `Click vertices · ${pointCount} selected` : 'Click two opposite corners'}</span>{mode === 'polygon' && <button className="button primary" disabled={pointCount < 3} onClick={finish}><Check size={14} /> Finish</button>}<button className="icon-button" aria-label="Cancel drawing" onClick={() => setDrawing('navigate')}><X size={16} /></button></div>}
    <button className="reset-map icon-button" title="Fit selected area" aria-label="Reset map view" onClick={() => { const map = mapRef.current; if (map) { if (latest.current.region) frameRegion(map, latest.current.region); else map.flyTo({ center: [36.5, 31.5], zoom: 5 }); } }}><Maximize2 size={16} /></button>
    {error && <div className="map-warning" role="status"><span>{error}</span>{retryBasemap.current && <button type="button" className="button secondary" onClick={() => retryBasemap.current?.()}><RefreshCw size={14} /> Retry basemap</button>}</div>}
    {!ready && !error && <p className="map-notice" role="status">Loading basemap…</p>}
    {notice && <p className="map-notice" role="status">{notice}</p>}
    <div className="map-legend"><span><i className="dot modis" /> MODIS · 1 km</span><span><i className="dot viirs" /> VIIRS · 375 m</span><span>{loading ? 'Loading observations…' : data ? `${data.metadata.returned.toLocaleString()} displayed${data.metadata.has_more ? ' · page capped' : ''}` : 'No observations loaded'}</span></div>
  </div>;
}
