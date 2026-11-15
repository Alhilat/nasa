import type { HistoryResult } from './history';

/** Serialize the reviewed snapshot, retaining only each month's public provenance. */
export function harmonizedCalendarCsv(result: HistoryResult): string {
  const calendar = result.harmonized_calendar;
  if (!calendar) throw new Error('No harmonized calendar is available.');
  const fields = ['month', 'value', 'lower_95', 'upper_95', 'sensor_code', 'origin', 'validation_status', 'completeness', 'extrapolated', 'model_version', 'source_ids', 'reason', 'uncertainty_reason', 'median_comparison'] as const;
  const mappedFields = ['mapped_value', 'mapped_lower_95', 'mapped_upper_95', 'mapped_extrapolated'] as const;
  const quote = (v: unknown) => `"${String(v === null || v === undefined ? '' : typeof v === 'object' ? JSON.stringify(v) : v).replaceAll('"', '""')}"`;
  // Append new columns so existing column positions remain compatible.
  const header = [...fields, 'units', 'analysis_id', 'algorithm_version', 'query_json', 'source_metadata_json', 'model_json', 'calendar_status', 'selection_policy', 'uncertainty_method', 'limitations_json', ...mappedFields];
  return [header.join(','), ...calendar.monthly.map(r => {
    const sources = result.sources.filter(s => r.source_ids.includes(s.id)).map(s => ({
      id: s.id, sha256: s.sha256, source_url: s.source_url, original_filename: s.original_filename,
      sensor_code: s.sensor_code, product_version: s.product_version,
      processing_level: s.processing_level, retrieved_at: s.retrieved_at,
    }));
    return [...fields.map(f => r[f]), calendar.units, result.analysis_id, calendar.algorithm_version,
      result.query, sources, calendar.model, calendar.status, calendar.selection_policy,
      calendar.uncertainty_method, calendar.limitations, ...mappedFields.map(f => r[f])].map(quote).join(',');
  })].join('\n') + '\n';
}
