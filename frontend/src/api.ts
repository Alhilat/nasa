import type { Job, ObservationDetail, Observations, Query, Source, Summary } from './types';

export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1').replace(/\/$/, '');

export async function request<T>(path: string, signal?: AbortSignal, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      signal,
      ...(body !== undefined ? {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      } : {}),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new Error('Cannot reach the FireScope API. Start the backend and check your API URL.');
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : `Request failed (${response.status}). Check your filters and database setup.`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  observations: (query: Query, signal?: AbortSignal) => request<Observations>('/observations/query', signal, query),
  summary: (query: Query, signal?: AbortSignal) => request<Summary>('/analytics/summary', signal, query),
  sources: (signal?: AbortSignal, offset = 0) => request<{ items: Source[]; has_more: boolean }>(`/sources?limit=50&offset=${offset}`, signal),
  jobs: (signal?: AbortSignal) => request<Job[]>('/jobs', signal),
  detail: (id: number, signal?: AbortSignal) => request<ObservationDetail>(`/observations/${id}`, signal),
};

export function inclusiveEndDate(value: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString();
}
