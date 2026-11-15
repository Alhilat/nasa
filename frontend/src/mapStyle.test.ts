import { expect, it } from 'vitest';
import { mapStyle } from './mapStyle';

it('uses the two ArcGIS layers with labels above imagery and ArcGIS row/column tile URLs', () => {
  const style = mapStyle('');
  if (typeof style === 'string') throw new Error('Expected the built-in ArcGIS style');
  expect(style.layers.map(layer => layer.id)).toEqual(['background', 'esri-imagery', 'esri-reference']);
  expect(style.layers[0]).toEqual({ id: 'background', type: 'background', paint: { 'background-color': '#101D35' } });
  const imagery = style.sources['esri-imagery'];
  const reference = style.sources['esri-reference'];
  if (imagery.type !== 'raster' || reference.type !== 'raster') throw new Error('Expected raster tiles');
  expect(imagery.tiles?.[0]).toBe('/basemap/imagery/{z}/{y}/{x}');
  expect(reference.tiles?.[0]).toBe('/basemap/reference/{z}/{y}/{x}');
  expect(imagery.tileSize).toBe(256);
  expect(reference.tileSize).toBe(256);
  expect(imagery.attribution).toContain('10df2279f9684e4a9f6a7f08febac2a9');
  expect(reference.attribution).toContain('a842e359856a4365b1ddf8cc34fde079');
});

it('keeps custom styles available and treats blank configuration as the built-in style', () => {
  expect(mapStyle(' https://example.com/map/style.json ')).toBe('https://example.com/map/style.json');
  expect(mapStyle('  ')).toHaveProperty('version', 8);
});
