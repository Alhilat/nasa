import { useEffect, useRef, useState } from 'react';
import { API_BASE, request } from './api';
import type { HistoryQuery } from './history';
import type { Query } from './types';

export type Region = { type: 'Polygon' | 'MultiPolygon'; coordinates: number[][][] | number[][][][] };
export type Resource<T> = { data: T | null; error: string; loading: boolean };
export type Comparison = {
  job_id: string; algorithm_version: string; parameters: Record<string, unknown>;
  provenance: Record<string, unknown>; scope: string; method: string;
  raw_count: number | null; grid_count: number | null; archive_counts_match: boolean | null;
  daily: { sensor_code: string; day: string; raw_count: number; grid_count: number; occupied_cells: number }[];
};

export function useResource<T>(key: string | null, load: (signal: AbortSignal) => Promise<T>, revision = 0): Resource<T> {
  const loader = useRef(load); loader.current = load;
  const [state, setState] = useState<Resource<T>>({ data: null, error: '', loading: key !== null });
  useEffect(() => {
    if (key === null) { setState({ data: null, error: '', loading: false }); return; }
    const controller = new AbortController();
    setState({ data: null, error: '', loading: true });
    loader.current(controller.signal).then(data => {
      if (!controller.signal.aborted) setState({ data, error: '', loading: false });
    }).catch(error => {
      if (!controller.signal.aborted) setState({ data: null, error: error instanceof Error ? error.message : 'Request failed.', loading: false });
    });
    return () => controller.abort();
  }, [key, revision]);
  return state;
}

export function parseBounds(value: string): [number, number, number, number] {
  const parts = value.split(',').map(s => s.trim());
  const numbers = parts.map(Number);
  if (parts.length !== 4 || parts.some(v => !v) || numbers.some(v => !Number.isFinite(v)))
    throw new Error('Enter four finite bounds: west, south, east, north.');
  const [west, south, east, north] = numbers;
  if (west < -180 || west > 180 || east < -180 || east > 180 || west === east || south < -90 || north > 90 || south >= north)
    throw new Error('Use distinct longitudes in −180…180 and ordered latitudes in −90…90.');
  return numbers as [number, number, number, number];
}

export function boundsRegion([w, s, e, n]: [number, number, number, number]): Region {
  const ring = (west: number, east: number) => [[west, s], [east, s], [east, n], [west, n], [west, s]];
  return w < e ? { type: 'Polygon', coordinates: [ring(w, e)] }
    : { type: 'MultiPolygon', coordinates: [[ring(w, 180)], [ring(-180, e)]] };
}

export function historySelection(query: Query, percentile: number, minimum: number, declarations: string): HistoryQuery {
  const start = Number(query.start!.slice(0, 4));
  const endDate = new Date(new Date(query.end!).getTime() - 1);
  const end = endDate.getUTCFullYear();
  if (end - start > 49 || start < 1900 || end > 2099) throw new Error('Choose at most 50 years between 1900 and 2099.');
  if (!Number.isFinite(percentile) || percentile < 50 || percentile >= 100 || !Number.isInteger(minimum) || minimum < 3 || minimum > 30)
    throw new Error('Use a percentile from 50 to below 100 and at least 3 (at most 30) reference years.');
  const coverage = JSON.parse(declarations);
  if (!Array.isArray(coverage)) throw new Error('Coverage declarations must be a JSON array.');
  return { start_year: start, end_year: end, baseline_start_year: start, baseline_end_year: end,
    bbox: query.bbox, polygon: query.polygon, sensors: query.sensors, confidence: query.confidence,
    percentile, min_baseline_years: minimum, grid_size_deg: 1, complete_months: coverage };
}

export async function detectionCsv(query: Query): Promise<string> {
  const response = await fetch(`${API_BASE}/observations/export.csv`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(query),
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({}));
    throw new Error(typeof problem.detail === 'string' ? problem.detail : `CSV export failed (${response.status}).`);
  }
  return response.text();
}

export const compare = (jobId: string, query: Query, signal: AbortSignal) =>
  request<Comparison>(`/analytics/comparison/${encodeURIComponent(jobId)}`, signal, query);

export const formatCount = (value: number | null | undefined) => value == null ? '—' : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
