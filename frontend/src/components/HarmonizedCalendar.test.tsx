import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import HarmonizedCalendar from './HarmonizedCalendar';
import type { HistoryResult } from '../history';
import { downloadArtifact } from '../history';
import { harmonizedCalendarCsv } from '../calendar';

const state = vi.hoisted(() => ({ chart: {} as Record<string, unknown> }));
vi.mock('./ScientificChart', () => ({ default: (props: Record<string, unknown>) => {
  state.chart = props; return <div>Calendar trend fixture</div>;
} }));
vi.mock('../history', async original => ({ ...await original<typeof import('../history')>(), downloadArtifact: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

// Explicit synthetic software response; not scientific observations.
const result = {
  analysis_id: 'synthetic-only', query: { sensors: ['MODIS_AQUA', 'VIIRS_SNPP'] }, sources: [],
  monthly: [
    { sensor_code: 'MODIS_AQUA', month: '2017-01', count: 10, comparison_series: 'validated_harmonized', comparison_value: 999, completeness: 'complete', anomaly_status: 'within_range' },
    { sensor_code: 'VIIRS_SNPP', month: '2017-01', count: 100, completeness: 'complete', anomaly_status: 'within_range' },
  ],
  harmonized_calendar: {
    algorithm_version: 'test-only', status: 'experimental', reference_sensor: 'MODIS_AQUA', source_sensor: 'VIIRS_SNPP',
    units: 'MODIS_AQUA-equivalent detections per month', reason: 'Synthetic response', selection_policy: 'Never sum.',
    uncertainty_method: 'Synthetic interval', limitations: ['Synthetic software fixture.'], candidates: [], model: null,
    monthly: [
      { month: '2017-01', value: 10, lower_95: null, upper_95: null, sensor_code: 'MODIS_AQUA', origin: 'modis_reference', validation_status: 'experimental', completeness: 'complete', extrapolated: false, model_version: null, source_ids: [], reason: 'Native reference', uncertainty_reason: 'Not quantified' },
      { month: '2017-02', value: 15, lower_95: 12, upper_95: 18, sensor_code: 'VIIRS_SNPP', origin: 'mapped_viirs', validation_status: 'experimental', completeness: 'complete', extrapolated: false, model_version: 'synthetic-model', source_ids: ['synthetic-source'], reason: 'Mapped, "synthetic"\nfixture', uncertainty_reason: 'Parameter interval' },
      { month: '2017-03', value: null, lower_95: null, upper_95: null, sensor_code: null, origin: 'missing', validation_status: 'unavailable', completeness: 'unknown', extrapolated: false, model_version: null, source_ids: [], reason: 'Missing', uncertainty_reason: 'Unknown' },
    ],
  },
} as unknown as HistoryResult;

function open(data = result, selected = '') {
  const onSelect = vi.fn();
  render(<HarmonizedCalendar result={data} sensor="MODIS_AQUA" selected={selected} onSelect={onSelect} />);
  return onSelect;
}

it('defaults to one harmonized series and sends actual interval bounds with null gaps to the chart', () => {
  open();
  expect(screen.getByRole('button', { name: 'Harmonized' }).getAttribute('aria-pressed')).toBe('true');
  expect(screen.getByText('Experimental')).toBeTruthy();
  expect(state.chart.series).toMatchObject([{ values: [10, 15, null] }, { values: [null, 12, null] }, { values: [null, 18, null] }]);
  expect(state.chart.band).toMatchObject({ lower: [null, 12, null], upper: [null, 18, null] });
  expect(screen.getByLabelText('Harmonized month details').textContent).toContain('95% parameter interval: 12–18');
});

it('switches MODIS and VIIRS to original counts without carrying calibrated native comparison values', () => {
  open();
  fireEvent.click(screen.getByRole('button', { name: 'MODIS' }));
  expect(state.chart.series).toMatchObject([{ values: [10] }]);
  expect(state.chart.band).toBeUndefined();
  expect(screen.queryByText('Experimental')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'VIIRS' }));
  expect(state.chart.series).toMatchObject([{ values: [100] }]);
});

it('selects missing months without filling them and explains an unavailable native family', () => {
  const onSelect = open({ ...result, query: { ...result.query, sensors: ['MODIS_AQUA'] } }, '2017-03');
  expect(screen.getByLabelText('Harmonized month details').textContent).toContain('Missing');
  fireEvent.click(screen.getByRole('button', { name: /2017-03, Harmonized:/ }));
  expect(onSelect).toHaveBeenCalledWith('2017-03');
  fireEvent.click(screen.getByRole('button', { name: 'VIIRS' }));
  expect(screen.getByText(/No VIIRS sensor is selected/)).toBeTruthy();
});

it('exports the reviewed harmonized snapshot with intervals, provenance, approval and escaped text', () => {
  open();
  fireEvent.click(screen.getByRole('button', { name: 'Export harmonized calendar CSV' }));
  const [csv, filename, type] = vi.mocked(downloadArtifact).mock.calls[0];
  expect(filename).toBe('pirx-harmonized-calendar.csv');
  expect(type).toBe('text/csv');
  expect(csv).toContain('lower_95,upper_95');
  expect(csv).toContain('"2017-02","15","12","18"');
  expect(csv).toContain('"2017-03","","",""');
  expect(csv).toContain('Mapped, ""synthetic""\nfixture');
  expect(csv).toContain('synthetic-only');
  expect(csv).toContain('synthetic-source');
});

it('keeps CSV provenance scoped to each month and omits unrelated archive audit payloads', () => {
  const csv = harmonizedCalendarCsv({ ...result, sources: [
    { id: 'synthetic-source', sha256: 'synthetic-checksum', source_url: 'https://example.org/synthetic-only',
      quality_reports: [{ internal_audit: 'unnecessary-payload'.repeat(100000) }] },
    { id: 'unrelated-source', sha256: 'unrelated-checksum', source_url: 'https://example.org/unrelated' },
  ] } as unknown as HistoryResult);
  expect(csv).toContain('synthetic-checksum');
  expect(csv).not.toContain('unrelated-checksum');
  expect(csv).not.toContain('unnecessary-payload');
  expect(csv.length).toBeLessThan(10000);
});

it('switches calendar colors without changing observations, query, or chart values', () => {
  open();
  const originalSeries = state.chart.series;
  fireEvent.change(screen.getByLabelText('Calendar colors'), { target: { value: 'median' } });
  expect(screen.getByText(/Signed values show detections above/)).toBeTruthy();
  expect(screen.getByText('Unassessed')).toBeTruthy();
  expect(state.chart.series).toEqual(originalSeries);
  fireEvent.change(screen.getByLabelText('Calendar colors'), { target: { value: 'activity' } });
  expect(screen.getByText(/Higher count/)).toBeTruthy();
});

it('plots mapped VIIRS overlap estimates and parameter uncertainty intervals alongside MODIS reference months', () => {
  const overlapResult = {
    ...result,
    harmonized_calendar: {
      ...result.harmonized_calendar,
      monthly: [
        { month: '2017-01', value: 10, lower_95: null, upper_95: null, mapped_value: 11, mapped_lower_95: 9, mapped_upper_95: 13, mapped_extrapolated: false, sensor_code: 'MODIS_TERRA', origin: 'modis_reference', validation_status: 'experimental', completeness: 'complete', extrapolated: false, model_version: null, source_ids: [], reason: 'Native reference', uncertainty_reason: 'Not quantified' },
      ],
    },
  } as unknown as HistoryResult;
  open(overlapResult, '2017-01');
  expect(state.chart.series).toHaveLength(4);
  expect(state.chart.series).toMatchObject([
    { values: [10] },
    { values: [11] },
    { values: [9] },
    { values: [13] },
  ]);
  expect(state.chart.band).toMatchObject({ lower: [9], upper: [13] });
  expect(screen.getByLabelText('Harmonized month details').textContent).toContain('Mapped VIIRS_SNPP estimate: 11 MODIS_AQUA-equivalent detections per month (95% parameter interval: 9–13).');
});


it('exports mapped overlap fields and leaves them empty for older responses', () => {
  const data = structuredClone(result);
  Object.assign(data.harmonized_calendar!.monthly[0], {
    mapped_value: 11, mapped_lower_95: 8, mapped_upper_95: 14, mapped_extrapolated: false,
  });
  const csv = harmonizedCalendarCsv(data);
  expect(csv).toContain('mapped_value,mapped_lower_95,mapped_upper_95,mapped_extrapolated');
  expect(csv.split('\n')[1]).toContain('"11","8","14","false"');
  expect(harmonizedCalendarCsv(result)).not.toContain('undefined');
});
