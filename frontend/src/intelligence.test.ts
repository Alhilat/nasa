import { afterEach, expect, it, vi } from 'vitest';
import { intelligence } from './intelligence';
import type { AIReply } from './intelligence';
import type { HistoryQuery } from './history';

afterEach(() => vi.unstubAllGlobals());
it('sends questions through FastAPI without exposing a Gemini key or client-supplied assistant history', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'evidence_only' }) });
  vi.stubGlobal('fetch', fetchMock);
  await intelligence.ask('Explain the data', { start_year: 2013, end_year: 2025 } as HistoryQuery, undefined, false, new AbortController().signal, false);
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toContain('/api/v1/ai/chat');
  expect(JSON.parse(options.body)).toEqual({ message: 'Explain the data', context: { start_year: 2013, end_year: 2025 }, refresh: false });
  expect(JSON.stringify(options)).not.toContain('API_KEY');
  expect(String(url)).not.toContain('google');
});
it('exports a server-stored report rather than uploading generated measurements', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, text: async () => '# Report' });
  vi.stubGlobal('fetch', fetchMock);
  const reply = { conversation_id: 'c', report_id: 'r', evidence: [{ data: { fabricated: 'client data must not be posted' } }] } as unknown as AIReply;
  expect(await intelligence.exportReport(reply, 'markdown')).toBe('# Report');
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ conversation_id: 'c', report_id: 'r', format: 'markdown' });
});
