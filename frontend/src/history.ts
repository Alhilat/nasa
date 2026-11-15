import { API_BASE, request } from './api';
import type { HarmonizedCalendar, MedianComparison } from './calendar.types';

export type CoverageMonth = { sensor_code: string; month: string; reference: string };
export type HistoryQuery = {
  start_year: number; end_year: number; baseline_start_year: number; baseline_end_year: number;
  bbox?: number[]; polygon?: object; sensors: string[]; confidence?: string;
  percentile: number; min_baseline_years: number; grid_size_deg: number;
  complete_months: CoverageMonth[];
};
type Comparison = { difference: number | null; percent_change: number | null };
export type HistoryMonth = {
  sensor_code: string; month: string; count: number | null; completeness: string;
  archive_completeness?: string; completeness_origin?: string; observation_coverage?: string;
  missing_data_status?: string; missing_data_reason?: string;
  comparison_series?: string; comparison_value?: number | null; comparison_units?: string;
  harmonized_value?: number | null; harmonized_extrapolated?: boolean | null;
  calibration_model_version?: string | null;
  historical_median: number | null; lower_threshold: number | null; upper_threshold: number | null;
  baseline_size: number; baseline_period?: string | null; baseline_window?: string | null;
  min_baseline_years?: number; baseline_sensors?: string[];
  anomaly_status: string; robust_z: number | null; year_over_year: Comparison;
  coverage_reference?: string | null; source_ids?: string[]; baseline_years?: number[];
  limitations?: string[];
  median_comparison?: MedianComparison;
};
export type HarmonizationSummary = {
  available: boolean; applied: boolean; status: string; comparison_series: string;
  model_version: string | null; method: string | null;
  source_sensor: string | null; reference_sensor: string | null;
  reason: string;
};
export type SensorTransition = {
  sensor_code: string; transition_type: string;
  operational_start?: string | null; partial_start_month?: string | null;
  first_full_month?: string | null; pre_operational_months_in_selection?: number;
  partial_transition_months_in_selection?: string[];
  product_versions?: string[]; processing_levels?: string[];
  applied_calibration_model?: string | null; harmonized?: boolean;
  note: string;
};
export type CompletenessSummary = {
  audit_version: string; observation_coverage: string;
  complete_months_count: number; unknown_months_count: number;
  assessed_months_count: number; status_counts: Record<string, number>;
};
export type HistoryResult = {
  analysis_id: string; algorithm_version: string; query: HistoryQuery;
  baseline_period?: string; min_baseline_years?: number; observation_coverage?: string;
  completeness_summary?: CompletenessSummary;
  harmonization?: HarmonizationSummary;
  harmonized_calendar?: HarmonizedCalendar;
  sensor_transitions?: SensorTransition[];
  limitations?: string[];
  metric_explanations: Record<string, string>; sources: {
    id: string; sha256: string; source_url: string; original_filename?: string;
    product_version?: string; processing_level?: string; sensor_code?: string; retrieved_at?: string;
  }[];
  monthly: HistoryMonth[];
  yearly: { sensor_code: string; year: number; count: number | null; observed_count: number | null;
    complete_months: number[]; year_over_year: Comparison & { matched_months: number[] } }[];
  seasonal_profiles: { sensor_code: string; calendar_month: number; median: number | null; sample_size: number; comparison_series?: string }[];
  concentration: { sensor_code: string; observed_count: number | null; occupied_cells: number;
    herfindahl_index: number | null; top_10_cells_share: number | null }[];
  spatial: { type: string; features: { geometry: object; properties: {
    sensor_code: string; grid_x: number; grid_y: number; count: number; share: number;
  } }[] };
};

const missingStatusLabels: Record<string, string> = {
  complete_assessed: 'Archive complete · assessed',
  complete_insufficient_baseline: 'Archive complete · insufficient baseline',
  complete_from_annual_source: 'Archive complete (annual country source)',
  complete_from_api_windows: 'Archive complete (standard API windows)',
  complete_caller_declared: 'Caller-declared complete',
  pre_operational_sensor: 'Pre-operational sensor',
  sensor_transition_partial_month: 'Partial sensor-start month',
  partial_month_archive: 'Partial month archive',
  nrt_unreconciled: 'NRT unreconciled with standard baseline',
  spatial_scope_mismatch: 'Spatial scope mismatch (API bbox vs country baseline)',
  mixed_processing_revisions: 'Mixed standard/NRT revisions',
  unattested_or_missing_source: 'Unknown / unattested archive coverage',
};

export function formatMissingDataStatus(status?: string, completeness?: string): string {
  if (status && missingStatusLabels[status]) return missingStatusLabels[status];
  if (status) return status.replaceAll('_', ' ');
  return completeness === 'complete' ? 'Archive complete' : 'Unknown archive completeness';
}
export const historyRequest = (query: HistoryQuery, signal?: AbortSignal) =>
  request<HistoryResult>('/analytics/history', signal, query);
export const jordanBoundary = () => request<object>('/analytics/history/jordan-boundary');

export async function historyCsv(result: HistoryResult): Promise<string> {
  const response = await fetch(`${API_BASE}/analytics/history/export.csv`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(result.query),
  });
  if (!response.ok) throw new Error(`CSV export failed (${response.status}).`);
  if (response.headers.get('X-Analysis-ID') !== result.analysis_id)
    throw new Error('The archive changed. Run the analysis again before exporting.');
  return response.text();
}

export function downloadArtifact(content: string, filename: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = filename; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// A missing harmonized estimate must stay missing rather than reverting to native counts.
export function comparisonValue(row: Pick<HistoryMonth, 'comparison_series' | 'comparison_value' | 'count'>): number | null {
  return row.comparison_series === 'validated_harmonized'
    ? row.comparison_value ?? null
    : row.comparison_value ?? row.count;
}

export function comparisonLabel(rows: Pick<HistoryMonth, 'comparison_series'>[]): string {
  return rows.some(row => row.comparison_series === 'validated_harmonized')
    ? 'Harmonized detections (reference sensor equivalent)'
    : 'Archived detections';
}
