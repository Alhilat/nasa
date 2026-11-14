import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useResource } from './useResource';

afterEach(cleanup);

it('aborts the old request and ignores its result when the selection changes', async () => {
  const pending: { signal: AbortSignal; resolve: (value: string) => void }[] = [];
  const load = vi.fn((signal: AbortSignal) => new Promise<string>(resolve => pending.push({ signal, resolve })));
  const { result, rerender } = renderHook(({ key }) => useResource(key, load), { initialProps: { key: 'first' as string | null } });
  await waitFor(() => expect(pending).toHaveLength(1));
  rerender({ key: 'second' });
  await waitFor(() => expect(pending).toHaveLength(2));
  expect(pending[0].signal.aborted).toBe(true);
  await act(async () => pending[1].resolve('new selection'));
  await act(async () => pending[0].resolve('stale selection'));
  expect(result.current).toEqual({ data: 'new selection', error: '', loading: false });
  rerender({ key: null });
  expect(result.current).toEqual({ data: null, error: '', loading: false });
});

it('isolates errors and retries when the revision changes', async () => {
  const load = vi.fn().mockRejectedValueOnce(new Error('Unavailable')).mockResolvedValueOnce('recovered');
  const { result, rerender } = renderHook(({ revision }) => useResource('data', load, revision), { initialProps: { revision: 0 } });
  await waitFor(() => expect(result.current.error).toBe('Unavailable'));
  rerender({ revision: 1 });
  await waitFor(() => expect(result.current.data).toBe('recovered'));
  expect(result.current).toEqual({ data: 'recovered', error: '', loading: false });
});
