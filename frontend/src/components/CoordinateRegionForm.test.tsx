import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import CoordinateRegionForm from './CoordinateRegionForm';
import { boundsRegion } from '../dashboard';

afterEach(cleanup);
function open(west = '35', east = '37', south = '30', north = '32') {
  const onRegion = vi.fn();
  render(<CoordinateRegionForm onRegion={onRegion} />);
  fireEvent.click(screen.getByText('Enter latitude / longitude'));
  for (const [label, value] of [['West longitude', west], ['East longitude', east], ['South latitude', south], ['North latitude', north]]) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }
  fireEvent.submit(screen.getByRole('form', { name: 'Region coordinates' }));
  return onRegion;
}
it('turns labeled latitude and longitude bounds into the same pending GeoJSON region', () => {
  expect(open()).toHaveBeenCalledWith(boundsRegion([35,30,37,32]));
});
it('supports wrapped longitude bounds as a split MultiPolygon', () => {
  expect(open('170', '-170')).toHaveBeenCalledWith(boundsRegion([170,30,-170,32]));
});
it.each([['', '37', '30', '32'], ['181', '37', '30', '32'], ['35', '35', '30', '32'], ['180', '-180', '30', '32'], ['35', '37', '40', '32']])('rejects blank, out-of-range or degenerate bounds (%s)', (w, e, s, n) => {
  const onRegion = open(w, e, s, n);
  expect(onRegion).not.toHaveBeenCalled();
  expect(screen.getByRole('alert')).toBeTruthy();
});
