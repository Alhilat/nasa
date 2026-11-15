import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import type { GeoJSONSource, MapMouseEvent } from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';
import { TerraDraw, TerraDrawPolygonMode, TerraDrawRectangleMode, TerraDrawRenderMode, ValidateNotSelfIntersecting } from 'terra-draw';
import { TerraDrawMapLibreGLAdapter } from 'terra-draw-maplibre-gl-adapter';
import { Crosshair, Download, Maximize2, Pentagon, RefreshCw, SquareDashed, Trash2, X } from 'lucide-react';
import { mapStyle } from '../mapStyle';
import { frameRegion, watchBasemap } from '../basemap';
import { boundsRegion } from '../dashboard';
import type { Region } from '../dashboard';
import type { ObservationProperties, Observations } from '../types';
import 'maplibre-gl/dist/maplibre-gl.css';
import { visualTheme as theme } from '../visualTheme';
import CoordinateRegionForm from './CoordinateRegionForm';
import { scientificColors } from '../colorScales';

const empty: FeatureCollection = { type: 'FeatureCollection', features: [] };
type Mode = 'navigate' | 'polygon' | 'rectangle';
export default function RegionMap({ data, region, loading, scopeLabel = '', onRegion, onSelect, onClear }: {
  data: Observations | null; region: Region | null; loading: boolean;
  onSelect: (row: ObservationProperties) => void; onRegion: (region: Region) => void; onClear: () => void; scopeLabel?: string;
}) {
  const container = useRef<HTMLDivElement>(null), mapRef = useRef<maplibregl.Map | null>(null);
  const retryBasemap = useRef<(() => void) | null>(null), framedRegion = useRef<Region | null>(null);
  const latest = useRef({ data, region, onRegion, onSelect }); latest.current = { data, region, onRegion, onSelect };
  const drawing = useRef<Mode>('navigate'), drawRef = useRef<TerraDraw | null>(null);
  const [mode, setMode] = useState<Mode>('navigate');
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [ready, setReady] = useState(false);

  function paintRegion(geometry: Region | null = latest.current.region) {
    const source = mapRef.current?.getSource('selection') as GeoJSONSource | undefined;
    const shape = drawing.current === 'navigate' ? geometry : null;
    source?.setData({ type: 'FeatureCollection', features: [
      ...(shape ? [{ type: 'Feature' as const, properties: {}, geometry: shape }] : []),
    ] });
  }

  function setDrawing(next: Mode) {
    drawing.current = next; setMode(next); setNotice('');
    if (drawRef.current?.enabled) { drawRef.current.setMode('navigate'); drawRef.current.clear(); drawRef.current.setMode(next); }
    if (mapRef.current) {
      mapRef.current.getCanvas().style.cursor = next === 'navigate' ? '' : 'crosshair';
      if (next === 'navigate') mapRef.current.doubleClickZoom.enable();
      else mapRef.current.doubleClickZoom.disable();
    }
    paintRegion();
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
    retryBasemap.current = () => {
      setDrawing('navigate'); drawRef.current?.stop(); drawRef.current = null;
      setReady(false); basemap.retry();
    };
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
        'circle-color': ['match', ['get', 'sensor_code'], 'MODIS_TERRA', scientificColors.sensors.MODIS, 'MODIS_AQUA', scientificColors.sensors.MODIS, scientificColors.sensors.VIIRS],
        'circle-opacity': 0.85, 'circle-stroke-color': '#FFFFFF80', 'circle-stroke-width': 0.5,
      } });
      // A style retry replaces adapter sources too; rebuild it against the new style.
      const draw = new TerraDraw({
        adapter: new TerraDrawMapLibreGLAdapter({ map }),
        modes: [new TerraDrawRenderMode({ modeName: 'navigate', styles: {} }),
          new TerraDrawPolygonMode({ keyEvents: { finish: 'Enter', cancel: 'Escape' }, validation: ValidateNotSelfIntersecting,
            styles: { fillColor: theme.reference, fillOpacity: 0.12, outlineColor: theme.reference } }),
          new TerraDrawRectangleMode({ styles: { fillColor: theme.reference, fillOpacity: 0.12, outlineColor: theme.reference } })],
      });
      drawRef.current = draw;
      draw.on('finish', id => {
        const feature = draw.getSnapshotFeature(id);
        if (!feature || feature.geometry.type !== 'Polygon') return;
        const geometry: Region = { type: 'Polygon', coordinates: feature.geometry.coordinates };
        const ring = geometry.coordinates[0] as number[][];
        const crosses = ring.some((p, i) => Math.abs(p[0] - ring[(i + 1) % ring.length][0]) > 180);
        if (crosses) { setDrawing('navigate'); setNotice('For antimeridian regions use the coordinate form or split GeoJSON.'); return; }
        latest.current.onRegion(geometry); setDrawing('navigate'); paintRegion(geometry);
        setNotice('Region drawn. Apply filters to query it.');
      });
      draw.start(); draw.setMode('navigate');
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
    });
    const observer = new ResizeObserver(() => map.resize()); observer.observe(container.current);
    return () => { drawRef.current?.stop(); drawRef.current = null; basemap.dispose(); retryBasemap.current = null; observer.disconnect(); map.remove(); mapRef.current = null; };
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
      context.fillStyle = theme.surface; context.fillRect(0, 0, canvas.width, canvas.height); context.drawImage(original, 0, 0);
      context.fillStyle = theme.muted; context.font = '12px IBM Plex Mono, monospace';
      lines.forEach((line, index) => context.fillText(line, 12, original.height + 20 + index * 18));
      const link = document.createElement('a'); link.download = 'firescope-map.png'; link.href = canvas.toDataURL('image/png'); link.click();
    } catch { setNotice('Map export failed. The basemap may restrict image export; analytical CSV and JSON exports are available.'); }
  }
  return <div onKeyDown={e => { if (e.key === 'Escape') setDrawing('navigate'); }} className={'region-map' + (error ? ' has-map-problem' : '')}>
    <div className="map-tools" aria-label="Region drawing tools">
      <button className={`map-tool ${mode === 'polygon' ? 'active' : ''}`} disabled={!ready} aria-pressed={mode === 'polygon'} onClick={() => setDrawing(mode === 'polygon' ? 'navigate' : 'polygon')}><Pentagon size={15} /> Draw polygon</button>
      <button className={`map-tool ${mode === 'rectangle' ? 'active' : ''}`} disabled={!ready} aria-pressed={mode === 'rectangle'} onClick={() => setDrawing(mode === 'rectangle' ? 'navigate' : 'rectangle')}><SquareDashed size={15} /> Rectangle</button>
      <button className="map-tool" disabled={!ready} onClick={mapBounds}><Crosshair size={15} /> Map bounds</button>
      <button className="map-tool" onClick={() => { setDrawing('navigate'); onClear(); }} aria-label="Clear region"><Trash2 size={15} /></button>
      <button className="map-tool" disabled={!ready} onClick={exportMap} aria-label="Export displayed map as PNG"><Download size={15} /></button>
    </div>
    <CoordinateRegionForm onRegion={geometry => { setDrawing('navigate'); onRegion(geometry); paintRegion(geometry); setNotice('Coordinates selected. Apply filters to query the region.'); }} />
    <div className="map-stage">
      <div ref={container} className="map-canvas" aria-label="Interactive thermal detection map" />
      {mode !== 'navigate' && <div className="drawing-notice" role="status"><span>{mode === 'polygon' ? 'Click vertices; click the first vertex or press Enter to finish' : 'Click two opposite corners'}</span><button className="icon-button" aria-label="Cancel drawing" onClick={() => setDrawing('navigate')}><X size={16} /></button></div>}
      <button className="reset-map icon-button" title="Fit selected area" aria-label="Reset map view" onClick={() => { const map = mapRef.current; if (map) { if (latest.current.region) frameRegion(map, latest.current.region); else map.flyTo({ center: [36.5, 31.5], zoom: 5 }); } }}><Maximize2 size={16} /></button>
      {error && <div className="map-warning" role="status"><span>{error}</span>{retryBasemap.current && <button type="button" className="button secondary" onClick={() => retryBasemap.current?.()}><RefreshCw size={14} /> Retry basemap</button>}</div>}
      {!ready && !error && <p className="map-notice" role="status">Loading basemap…</p>}
      {notice && <p className="map-notice" role="status">{notice}</p>}
      <div className="map-legend"><span><i className="dot modis" /> MODIS · 1 km</span><span><i className="dot viirs" /> VIIRS · 375 m</span><span>{loading ? 'Loading observations…' : data ? `${data.metadata.returned.toLocaleString()} displayed${data.metadata.has_more ? ' · page capped' : ''}` : 'No observations loaded'}</span></div>
    </div>
  </div>;
}
