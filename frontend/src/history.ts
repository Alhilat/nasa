import { API_BASE, request } from './api';

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
  historical_median: number | null; lower_threshold: number | null; upper_threshold: number | null;
  baseline_size: number; anomaly_status: string; robust_z: number | null; year_over_year: Comparison;
  coverage_reference?: string | null; source_ids?: string[]; baseline_years?: number[];
};
export type HistoryResult = {
  analysis_id: string; algorithm_version: string; query: HistoryQuery;
  metric_explanations: Record<string, string>; sources: {
    id: string; sha256: string; source_url: string; original_filename?: string;
    product_version?: string; processing_level?: string; sensor_code?: string; retrieved_at?: string;
  }[];
  monthly: HistoryMonth[];
  yearly: { sensor_code: string; year: number; count: number | null; observed_count: number | null;
    complete_months: number[]; year_over_year: Comparison & { matched_months: number[] } }[];
  seasonal_profiles: { sensor_code: string; calendar_month: number; median: number | null; sample_size: number }[];
  concentration: { sensor_code: string; observed_count: number | null; occupied_cells: number;
    herfindahl_index: number | null; top_10_cells_share: number | null }[];
  spatial: { type: string; features: { geometry: object; properties: {
    sensor_code: string; grid_x: number; grid_y: number; count: number; share: number;
  } }[] };
};
export const historyRequest = (query: HistoryQuery, signal?: AbortSignal) =>
  request<HistoryResult>('/analytics/history', signal, query);

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
