import { expect, it } from 'vitest';
import { activityColor, contrastRatio, departureColor, installScientificColors, luminance, readableText, scientificColors, sensorColor } from './colorScales';

it('keeps calendar text above WCAG AA normal-text contrast on every palette fill', () => {
  expect(contrastRatio('#000000', '#FFFFFF')).toBeCloseTo(21);
  for (const fill of [...scientificColors.activity, ...scientificColors.departure]) {
    expect(contrastRatio(fill, readableText(fill))).toBeGreaterThanOrEqual(4.5);
  }
  expect(contrastRatio(scientificColors.unknown.background, scientificColors.unknown.foreground)).toBeGreaterThanOrEqual(4.5);
});
it('orders activity by lightness and uses a distinct missing-data appearance', () => {
  const levels = scientificColors.activity.map(luminance);
  expect(levels.every((v, i) => i === 0 || v > levels[i - 1])).toBe(true);
  expect(activityColor(0, 100)).toBe(scientificColors.activity[0]);
  expect(activityColor(100, 100)).toBe(scientificColors.activity[4]);
  expect(scientificColors.activity).not.toContain(scientificColors.unknown.background);
});
it('uses opposite divergence sides, a zero center, and bounded extrema', () => {
  expect(departureColor(-100, 100)).toBe(scientificColors.departure[0]);
  expect(departureColor(0, 100)).toBe(scientificColors.departure[3]);
  expect(departureColor(100, 100)).toBe(scientificColors.departure[6]);
  expect(departureColor(1000, 1)).toBe(scientificColors.departure[6]);
});
it('shares categorical colors between rendered data and CSS legends', () => {
  installScientificColors();
  expect(document.documentElement.style.getPropertyValue('--sensor-modis')).toBe(sensorColor('MODIS_TERRA'));
  expect(document.documentElement.style.getPropertyValue('--sensor-viirs')).toBe(sensorColor('VIIRS_SNPP'));
});
