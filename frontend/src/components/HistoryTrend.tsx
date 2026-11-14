import { useMemo } from 'react';
import type { HistoryResult } from '../history';
import ScientificChart from './ScientificChart';

export default function HistoryTrend({ result, sensor }: { result: HistoryResult; sensor: string }) {
  const rows = useMemo(() => result.monthly.filter(r => r.sensor_code === sensor), [result, sensor]);
  const labels = useMemo(() => rows.map(r => r.month), [rows]);
  const series = useMemo(() => [
    { name: 'Archived count (may be incomplete)', values: rows.map(r => r.count), color: '#f5b556' },
    { name: 'Prior complete-year median', values: rows.map(r => r.historical_median), color: '#78c8c0', dashed: true },
    { name: 'Upper percentile threshold', values: rows.map(r => r.upper_threshold), color: '#b99df2', dashed: true },
  ], [rows]);
  return <ScientificChart title={`${sensor} historical activity trend`} labels={labels} series={series} metadata={{ analysis_id: result.analysis_id, query: result.query, sources: result.sources }} />;
}
