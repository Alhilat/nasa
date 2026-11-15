import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import Sources from './Sources';
import { api } from '../api';

vi.mock('../api', () => ({ api: { sources: vi.fn(), jobs: vi.fn() } }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const source = {
  id: 'test-source', sha256: 'a'.repeat(64), original_filename: 'test-firms.csv',
  sensor_code: 'MODIS', source_url: 'https://example.org/source', product_version: 'native',
  processing_level: 'standard', retrieved_at: '2025-01-01T00:00:00Z',
  imported_at: '2025-01-01T00:00:00Z', row_count: 1,
};

async function openArchive(writeText: ReturnType<typeof vi.fn>) {
  vi.mocked(api.sources).mockResolvedValue({ items: [source], has_more: false });
  vi.mocked(api.jobs).mockResolvedValue([]);
  vi.stubGlobal('navigator', { clipboard: { writeText } });
  render(<Sources />);
  fireEvent.click(await screen.findByRole('button', { name: 'Copy SHA-256 for test-firms.csv' }));
}

it('confirms a successful source checksum copy', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  await openArchive(writeText);
  expect(await screen.findByText('Checksum copied for test-firms.csv.')).toBeTruthy();
  expect(writeText).toHaveBeenCalledWith(source.sha256);
});

it('offers the full selectable checksum when clipboard access is denied', async () => {
  await openArchive(vi.fn().mockRejectedValue(new DOMException('Denied', 'NotAllowedError')));
  expect(await screen.findByText(/Clipboard access is unavailable/)).toBeTruthy();
  expect(screen.getByText(source.sha256)).toBeTruthy();
  expect(screen.getByRole('status').textContent).toContain(source.sha256);
});
