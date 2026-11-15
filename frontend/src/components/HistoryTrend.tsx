import { useMemo } from 'react';
import { comparisonLabel, comparisonValue } from '../history';
import type { HistoryResult } from '../history';
import ScientificChart from './ScientificChart';
import { visualTheme as theme } from '../visualTheme';

export default function HistoryTrend({ result, sensor }: { result: HistoryResult; sensor: string }) {
  const rows = useMemo(() => result.monthly.filter(r => r.sensor_code === sensor), [result, sensor]);
  const labels = useMemo(() => rows.map(r => r.month), [rows]);
  const series = useMemo(() => [
    { name: comparisonLabel(rows), values: rows.map(comparisonValue), color: theme.orange },
    { name: 'Prior complete-year median', values: rows.map(r => r.historical_median), color: theme.reference, dashed: true },
    { name: 'Upper percentile threshold', values: rows.map(r => r.upper_threshold), color: theme.white, dashed: true },
  ], [rows]);
  return <ScientificChart title={`${sensor} historical activity trend`} labels={labels} series={series} metadata={{ analysis_id: result.analysis_id, query: result.query, sources: result.sources }} />;
}
