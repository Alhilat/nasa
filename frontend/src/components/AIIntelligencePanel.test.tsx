import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import AIIntelligencePanel from './AIIntelligencePanel';
import { downloadArtifact } from '../history';
import { intelligence } from '../intelligence';
import type { AIReply } from '../intelligence';
import type { HistoryQuery } from '../history';

vi.mock('../intelligence', () => ({ intelligence: { status: vi.fn(), ask: vi.fn(), reset: vi.fn(), exportReport: vi.fn() } }));
vi.mock('../history', async original => ({ ...await original<typeof import('../history')>(), downloadArtifact: vi.fn() }));
vi.mock('./ScientificChart', () => ({ default: () => <div>Python evidence chart</div> }));

const context: HistoryQuery = { start_year: 2013, end_year: 2016, baseline_start_year: 2013, baseline_end_year: 2016, bbox: [34,29,40,34], sensors: ['MODIS_TERRA'], percentile: 95, min_baseline_years: 3, grid_size_deg: 1, complete_months: [] };
const statement = { text: 'Consult the evidence and its coverage limitations.', evidence_ids: ['E-synthetic'] };
const reply: AIReply = { conversation_id: 'a'.repeat(43), report_id: 'b'.repeat(32), model: 'synthetic-provider-test', created_at: '2026-11-14T00:00:00Z', status: 'interpreted', forecasting: false,
  interpretation: { executive_summary: [statement], interpretations: [], data_limitations: [statement], recommendations: [statement] }, tool_calls: [{ tool: 'get_historical_activity', evidence_id: 'E-synthetic', status: 'available' }], notices: [],
  evidence: [{ id: 'E-synthetic', tool: 'get_historical_activity', status: 'available', scope: { query: context }, analysis_ids: ['test-analysis-id'], sources: [], source_count: 0, source_list_truncated: false, retrieved_at: '2026-11-14T00:00:00Z', cache_hit: false,
    facts: [{ section: 'historical_observations', label: 'Synthetic archived count', value: 8, sensor: 'MODIS_TERRA', period: '2016', unit: 'thermal detections' }], data: {}, limitations: ['Synthetic test data, never application observations.'], charts: [{ title: 'Synthetic chart', labels: ['2016'], series: [{ name: 'MODIS_TERRA', values: [8], color: '#f5b556' }] }] }],
};
beforeEach(() => {
  vi.mocked(intelligence.status).mockResolvedValue({ configured: true, model: 'synthetic-provider-test', tools: [], regions: {}, privacy: 'Questions and selected evidence are sent to Gemini only when submitted.' });
  vi.mocked(intelligence.ask).mockResolvedValue(reply);
  vi.mocked(intelligence.exportReport).mockResolvedValue('# Synthetic test report');
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const ask = async () => { await waitFor(() => expect(screen.getByRole('button', { name: 'Generate report' }).hasAttribute('disabled')).toBe(false)); fireEvent.change(screen.getByLabelText('Question'), { target: { value: 'Explain this selected area' } }); fireEvent.click(screen.getByRole('button', { name: 'Ask' })); };

it('uses the applied map context, renders evidence and follows up with a server conversation ID', async () => {
  render(<AIIntelligencePanel context={context} />);
  await ask();
  expect(await screen.findByText('Synthetic archived count')).toBeTruthy();
  expect(vi.mocked(intelligence.ask).mock.calls[0][1]).toEqual(context);
  expect(vi.mocked(intelligence.ask).mock.calls[0][2]).toBeUndefined();
  fireEvent.click(screen.getByRole('button', { name: 'Show evidence charts' }));
  expect(screen.getByText('Python evidence chart')).toBeTruthy();
  vi.mocked(intelligence.ask).mockResolvedValue({ ...reply, report_id: 'c'.repeat(32) });
  await ask();
  await waitFor(() => expect(vi.mocked(intelligence.ask).mock.calls[1][2]).toBe(reply.conversation_id));
});

it('clears stale answers and conversation context when the applied map region changes', async () => {
  const view = render(<AIIntelligencePanel context={context} />);
  await ask(); await screen.findByText('Synthetic archived count');
  view.rerender(<AIIntelligencePanel context={{ ...context, bbox: [35,30,39,33] }} />);
  expect(await screen.findByText(/Selection changed/)).toBeTruthy();
  expect(screen.queryByText('Synthetic archived count')).toBeNull();
  await ask();
  await waitFor(() => expect(vi.mocked(intelligence.ask).mock.calls[1][2]).toBeUndefined());
});

it('generates a report and restores Markdown and JSON evidence exports', async () => {
  render(<AIIntelligencePanel context={context} />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Generate report' }).hasAttribute('disabled')).toBe(false));
  fireEvent.click(screen.getByRole('button', { name: 'Generate report' }));
  await screen.findByText('Synthetic archived count');
  expect(vi.mocked(intelligence.ask).mock.calls[0][3]).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Report · Markdown' }));
  await waitFor(() => expect(intelligence.exportReport).toHaveBeenCalledWith(reply, 'markdown'));
  expect(downloadArtifact).toHaveBeenCalledWith('# Synthetic test report', 'firescope-ai-report.md', 'text/markdown');
  await waitFor(() => expect(screen.queryByText('Preparing report export…')).toBeNull());
  fireEvent.click(screen.getByRole('button', { name: 'Evidence · JSON' }));
  await waitFor(() => expect(intelligence.exportReport).toHaveBeenCalledWith(reply, 'json'));
  expect(downloadArtifact).toHaveBeenCalledWith('# Synthetic test report', 'firescope-ai-evidence.json', 'application/json');
});

it('shows provider failure without manufacturing an answer', async () => {
  vi.mocked(intelligence.ask).mockRejectedValue(new Error('Gemini quota reached. Retry later.'));
  render(<AIIntelligencePanel context={context} />);
  await ask();
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Gemini quota reached. Retry later.');
  expect(screen.queryByText('Synthetic archived count')).toBeNull();
});

it('does not permit requests when the provider is unconfigured', async () => {
  vi.mocked(intelligence.status).mockResolvedValue({ configured: false, model: 'test', tools: [], regions: {}, privacy: '' });
  render(<AIIntelligencePanel context={context} />);
  expect(await screen.findByText(/assistant is not connected/)).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Ask' }).hasAttribute('disabled')).toBe(true);
  expect(intelligence.ask).not.toHaveBeenCalled();
});
