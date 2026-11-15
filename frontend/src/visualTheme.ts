/** Rendering tokens for canvas, SVG charts and MapLibre paint properties. */
import { scientificColors } from './colorScales';
export const visualTheme = {
  surface: '#F4F2EB',
  text: '#252B35',
  blue: '#1769AA',
  orange: '#F47A32',
  viirs: scientificColors.sensors.VIIRS,
  reference: '#8CC4EE',
  white: '#FFFFFF',
  muted: '#252B35',
  rule: '#8B929C',
  alert: '#D94141',
  fontUI: 'Inter, sans-serif',
  fontData: 'IBM Plex Mono, monospace',
} as const;
