import type { FeatureCollection, Point } from 'geojson';

export const sensorCodes = ['MODIS_TERRA', 'MODIS_AQUA', 'VIIRS_SNPP', 'VIIRS_NOAA20', 'VIIRS_NOAA21'];
export type Query = {
  bbox?: [number, number, number, number];
  polygon?: Record<string, unknown>;
  start?: string;
  end?: string;
  sensors: string[];
  confidence?: 'low' | 'nominal' | 'high';
  limit: number;
};
export type ObservationProperties = {
  id: number; sensor_code: string; acquired_at: string; frp_mw: number | null;
  confidence_native: string; confidence_class: string; source_id: string;
  source_sha256: string; source_row: number; uncertainty: Record<string, unknown>;
};
export type Observations = FeatureCollection<Point, ObservationProperties> & {
  metadata: { returned: number; has_more: boolean; limit: number; offset: number };
};
export type Summary = {
  detection_count: number; source_count: number; first_acquisition: string | null;
  last_acquisition: string | null; frp_known_count: number; frp_sum_mw: number | null;
  by_sensor: Record<string, number>;
  daily: { day: string; sensor_code: string; count: number }[];
  coverage_known: boolean; method: string;
};
export type Source = {
  id: string; sha256: string; original_filename: string; sensor_code: string;
  source_url: string; product_version: string; processing_level: string;
  retrieved_at: string; imported_at: string; row_count: number;
};
export type Job = {
  id: string; kind: string; status: string; algorithm_version: string;
  started_at: string; finished_at: string | null; error_message: string | null;
  output_metadata: Record<string, unknown>;
  parameters: Record<string, unknown>;
};
export type ObservationDetail = {
  id: number; raw_properties: Record<string, string>; uncertainty: Record<string, unknown>;
  source_url: string; source_sha256: string; source_row: number; product_version: string;
};
