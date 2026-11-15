import type { StyleSpecification } from 'maplibre-gl';
import { visualTheme as theme } from './visualTheme';

export function mapStyle(customStyle = import.meta.env.VITE_MAP_STYLE_URL): string | StyleSpecification {
  if (customStyle?.trim()) return customStyle.trim();

  return {
    version: 8,
    name: 'Esri World Imagery with boundaries and places',
    sources: {
      'esri-imagery': {
        type: 'raster',
        tiles: ['/basemap/imagery/{z}/{y}/{x}'],
        tileSize: 256,
        maxzoom: 23,
        attribution: '<a href="https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9" target="_blank" rel="noreferrer">Esri World Imagery</a> · Vantor, Earthstar Geographics, and the GIS User Community',
      },
      'esri-reference': {
        type: 'raster',
        tiles: ['/basemap/reference/{z}/{y}/{x}'],
        tileSize: 256,
        maxzoom: 23,
        attribution: '<a href="https://www.arcgis.com/home/item.html?id=a842e359856a4365b1ddf8cc34fde079" target="_blank" rel="noreferrer">Esri World Boundaries and Places</a> · HERE, Garmin, © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors, and the GIS User Community',
      },
    },
    layers: [
      { id: 'background', type: 'background', paint: { 'background-color': theme.navy } },
      { id: 'esri-imagery', type: 'raster', source: 'esri-imagery' },
      { id: 'esri-reference', type: 'raster', source: 'esri-reference' },
    ],
  };
}
