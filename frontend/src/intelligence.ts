import { API_BASE, request } from './api';
import type { HistoryQuery } from './history';

export type Statement = { text: string; evidence_ids: string[] };
export type AIEvidence = {
  id: string; tool: string; status: 'available' | 'unavailable'; scope: Record<string, unknown>;
  analysis_ids: string[]; sources: { id: string; sha256: string; source_url: string | null; sensor_code?: string; product_version?: string }[];
  source_count: number; source_list_truncated: boolean; retrieved_at: string; cache_hit: boolean;
  facts: { section: string; label: string; value: number | string | null; sensor?: string; period?: string; unit?: string; [key: string]: unknown }[];
  data: Record<string, unknown>; limitations: string[];
  charts: { title: string; labels: string[]; series: { name: string; values: (number | null)[]; color: string }[] }[];
};
export type AIReply = {
  conversation_id: string; report_id: string; model: string; created_at: string;
  status: 'interpreted' | 'evidence_only'; forecasting: false;
  interpretation: { executive_summary: Statement[]; interpretations: Statement[]; data_limitations: Statement[]; recommendations: Statement[] } | null;
  evidence: AIEvidence[]; tool_calls: { tool: string; evidence_id: string; status: string }[]; notices: string[];
};
export type AIStatus = { configured: boolean; model: string; fallback_models?: string[]; tools: string[]; regions: Record<string, string>; privacy: string };
export type DateWindow = { start_date: string; end_date: string };
export const intelligence = {
  status: (signal: AbortSignal) => request<AIStatus>('/ai/status', signal),
  ask: (message: string, context: HistoryQuery, conversation_id: string | undefined, report: boolean, signal: AbortSignal, refresh: boolean, date_window?: DateWindow) =>
    request<AIReply>(report ? '/ai/reports' : '/ai/chat', signal, { message, context, conversation_id, refresh, date_window }),
  reset: (conversation_id: string) => request('/ai/conversations/reset', undefined, { conversation_id }),
  async exportReport(reply: AIReply, format: 'markdown' | 'json'): Promise<string> {
    const response = await fetch(`${API_BASE}/ai/reports/export`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: reply.conversation_id, report_id: reply.report_id, format }),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(typeof error.detail === 'string' ? error.detail : 'Report export failed.');
    }
    return response.text();
  },
};
