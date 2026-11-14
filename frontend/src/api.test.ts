import { afterEach, describe, expect, it, vi } from 'vitest';
import { inclusiveEndDate, request } from './api';

afterEach(() => vi.unstubAllGlobals());

describe('API boundary', () => {
  it('sends polygon queries as JSON and preserves null values', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ frp_mw: null }) });
    vi.stubGlobal('fetch', fetchMock);
    const query = { polygon: { type: 'Polygon', coordinates: [] } };
    expect(await request('/observations/query', undefined, query)).toEqual({ frp_mw: null });
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST', body: JSON.stringify(query) });
  });
  it('surfaces an API outage instead of returning an empty scientific result', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
    await expect(request('/observations')).rejects.toThrow('Cannot reach');
  });
  it('surfaces database unavailability', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({ detail: 'Database unavailable' }) }));
    await expect(request('/observations')).rejects.toThrow('Database unavailable');
  });
  it('turns an inclusive UTC end date into an exclusive next-day boundary', () => {
    expect(inclusiveEndDate('2024-02-29')).toBe('2024-03-01T00:00:00.000Z');
    expect(inclusiveEndDate('')).toBeUndefined();
  });
});
