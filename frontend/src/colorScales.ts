/** Scientific colors, shared by calendars, charts, map markers and CSS legends.
 * Cividis: Matplotlib. PuOr (reversed): ColorBrewer, Cynthia Brewer / PSU.
 * Sensor categories: blue/orange from the Okabe–Ito palette. See docs/accessibility.md.
 */
export const scientificColors = {
  activity: ['#00224E', '#434E6C', '#7D7C78', '#BCAE6C', '#FEE838'],
  departure: ['#542788', '#998EC3', '#D8DAEB', '#F7F7F7', '#FEE0B6', '#F1A340', '#B35806'],
  sensors: { MODIS: '#E69F00', VIIRS: '#56B4E9' },
  unknown: { background: '#182334', foreground: '#BCC7D6' },
  text: { dark: '#000000', light: '#FFFFFF' },
} as const;

export function luminance(hex: string): number {
  const rgb = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
}
export function contrastRatio(a: string, b: string): number {
  const first = luminance(a), second = luminance(b);
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
}
export function readableText(background: string): string {
  return contrastRatio(background, scientificColors.text.dark) > contrastRatio(background, scientificColors.text.light)
    ? scientificColors.text.dark : scientificColors.text.light;
}
export function sensorColor(sensor: string): string {
  return sensor.startsWith('MODIS') ? scientificColors.sensors.MODIS : scientificColors.sensors.VIIRS;
}
export function activityColor(value: number, maximum: number): string {
  const index = value === 0 ? 0 : Math.max(1, Math.min(4, Math.ceil(value / Math.max(1, maximum) * 4)));
  return scientificColors.activity[index];
}
export function departureColor(departure: number, maximumAbsoluteDeparture: number): string {
  if (departure === 0) return scientificColors.departure[3];
  const distance = Math.min(3, Math.max(1, Math.ceil(Math.abs(departure) / (maximumAbsoluteDeparture || 1) * 3)));
  return scientificColors.departure[3 + Math.sign(departure) * distance];
}
export function installScientificColors(root: HTMLElement = document.documentElement) {
  root.style.setProperty('--sensor-modis', scientificColors.sensors.MODIS);
  root.style.setProperty('--sensor-viirs', scientificColors.sensors.VIIRS);
  root.style.setProperty('--calendar-unknown', scientificColors.unknown.background);
  root.style.setProperty('--calendar-unknown-text', scientificColors.unknown.foreground);
  root.style.setProperty('--calendar-hatch', scientificColors.unknown.foreground + '33');
}
