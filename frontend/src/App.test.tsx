import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from './App';
import { request } from './api';

vi.mock('./api', () => ({ request: vi.fn().mockResolvedValue({ status: 'ok' }) }));
vi.mock('./pages/Dashboard', () => ({ default: () => <h1>Dashboard route content</h1> }));
vi.mock('./pages/Explorer', () => ({ default: () => <h1>Explorer route content</h1> }));
vi.mock('./pages/History', () => ({ default: () => <h1>History route content</h1> }));
vi.mock('./pages/Sources', () => ({ default: () => <h1>Sources route content</h1> }));
vi.mock('./pages/Methodology', () => ({ default: () => <h1>Methods route content</h1> }));
beforeEach(() => vi.mocked(request).mockResolvedValue({ status: 'ok' }));
afterEach(cleanup);

it('restores all five navigation destinations and the scientific shell content', async () => {
  render(<MemoryRouter><App /></MemoryRouter>);
  for (const [name, heading] of [
    ['Observation explorer', 'Explorer route content'],
    ['Historical analysis', 'History route content'],
    ['Data & provenance', 'Sources route content'],
    ['Methodology', 'Methods route content'],
    ['Intelligence dashboard', 'Dashboard route content'],
  ]) {
    fireEvent.click(screen.getByRole('link', { name }));
    expect(await screen.findByRole('heading', { name: heading })).toBeTruthy();
  }
  expect(screen.getByText(/Every observation has a source/)).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Our scientific approach' }).getAttribute('href')).toBe('/methodology');
  expect(screen.getByText('FireScope v0.1.0')).toBeTruthy();
  expect(screen.getByText('NASA FIRMS attribution retained · All times UTC')).toBeTruthy();
});

it('opens the restored Explorer directly and closes navigation after choosing a route', async () => {
  render(<MemoryRouter initialEntries={['/explorer']}><App /></MemoryRouter>);
  expect(await screen.findByRole('heading', { name: 'Explorer route content' })).toBeTruthy();
  const menu = screen.getByRole('button', { name: 'Toggle navigation' });
  fireEvent.click(menu);
  expect(menu.getAttribute('aria-expanded')).toBe('true');
  fireEvent.click(screen.getByRole('link', { name: 'Historical analysis' }));
  expect(await screen.findByRole('heading', { name: 'History route content' })).toBeTruthy();
  expect(menu.getAttribute('aria-expanded')).toBe('false');
});
