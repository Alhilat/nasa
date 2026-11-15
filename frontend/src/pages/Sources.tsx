import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import {
  ArrowRight,
  Database,
  FileCheck2,
  Grid2X2,
  Layers2,
  Play,
  RefreshCw,
  SlidersHorizontal,
} from 'lucide-react';
import * as echarts from 'echarts/core';
import { MarkLineComponent } from 'echarts/components';
import { api, request } from '../api';
import ScientificChart from '../components/ScientificChart';
import { visualTheme as theme } from '../visualTheme';
import { useResource } from '../useResource';
import { downloadArtifact } from '../history';
import type { Job, Source } from '../types';

echarts.use([MarkLineComponent]);

function ProvenanceArchive() {
  const [sources, setSources] = useState<Source[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [copyResult, setCopyResult] = useState<{ hash: string; filename: string; copied: boolean } | null>(
    null,
  );
  async function copyHash(source: Source) {
    setCopyResult(null);
    try {
      await navigator.clipboard.writeText(source.sha256);
      setCopyResult({ hash: source.sha256, filename: source.original_filename, copied: true });
    } catch {
      setCopyResult({ hash: source.sha256, filename: source.original_filename, copied: false });
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    setBusy(true);
    setError('');
    setSources([]);
    setJobs([]);
    setCopyResult(null);
    Promise.all([api.sources(controller.signal, offset), api.jobs(controller.signal)])
      .then(([sourceData, jobData]) => {
        if (!controller.signal.aborted) {
          setSources(sourceData.items);
          setHasMore(sourceData.has_more);
          setJobs(jobData);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [refresh, offset]);

  return (
    <>
      <div className="engine-provenance-heading">
        <p>Original sources, reproducible processing, and a visible audit trail.</p>
        <button
          className="button secondary"
          aria-label="Refresh source archive"
          onClick={() => setRefresh((n) => n + 1)}
          disabled={busy}
        >
          <RefreshCw size={15} /> Refresh archive
        </button>
      </div>
      {error && (
        <div role="alert" className="connection-notice">
          {error}
        </div>
      )}
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Source archive</h2>
            <p>Original files with retrieval dates and SHA-256 checksums.</p>
          </div>
          <FileCheck2 size={21} className="muted" />
        </div>
        <div className={copyResult ? 'copy-feedback' : 'sr-only'} role="status" aria-live="polite">
          {copyResult && (
            <>
              <p>
                {copyResult.copied
                  ? `Checksum copied for ${copyResult.filename}.`
                  : 'Clipboard access is unavailable. Select and copy the full checksum below.'}
              </p>
              {!copyResult.copied && <code>{copyResult.hash}</code>}
            </>
          )}
        </div>
        {busy ? (
          <div className="empty-state" role="status">
            Loading source archive…
          </div>
        ) : sources.length ? (
          <div className="table-scroll" role="region" aria-label="Source archive data" tabIndex={0}>
            <table>
              <thead>
                <tr>
                  <th>Source file</th>
                  <th>Sensor</th>
                  <th>Product</th>
                  <th>Rows</th>
                  <th>SHA-256</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <span>{s.original_filename}</span>
                      <small>Retrieved {new Date(s.retrieved_at).toISOString()}</small>
                    </td>
                    <td>{s.sensor_code}</td>
                    <td>
                      {s.product_version}
                      <small>{s.processing_level}</small>
                    </td>
                    <td>{s.row_count.toLocaleString()}</td>
                    <td>
                      <code title={s.sha256}>{s.sha256.slice(0, 12)}…</code>
                      <button
                        className="copy-button"
                        aria-label={`Copy SHA-256 for ${s.original_filename}`}
                        onClick={() => copyHash(s)}
                      >
                        Copy
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <Database size={30} strokeWidth={1.3} />
            <h3>{error ? 'Archive unavailable' : 'No source files'}</h3>
            <p>Import a real FIRMS CSV with the pipeline CLI.</p>
            <p>The repository’s startup guide includes the exact commands.</p>
          </div>
        )}
        <div className="pagination">
          <button
            className="button secondary"
            disabled={offset === 0 || busy}
            onClick={() => setOffset((n) => Math.max(0, n - 50))}
          >
            Previous
          </button>
          <span>Page {offset / 50 + 1}</span>
          <button
            className="button secondary"
            disabled={!hasMore || busy || !!error}
            onClick={() => setOffset((n) => n + 50)}
          >
            Next
          </button>
        </div>
      </section>
      <section className="panel jobs-panel">
        <div className="panel-heading">
          <div>
            <h2>Processing history</h2>
            <p>The latest 50 jobs, with method versions and results.</p>
          </div>
        </div>
        {jobs.length ? (
          <div className="table-scroll" role="region" aria-label="Processing history data" tabIndex={0}>
            <table>
              <thead>
                <tr>
                  <th>Job</th>
                  <th>Method</th>
                  <th>Started (UTC)</th>
                  <th>Status</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id}>
                    <td>
                      {j.kind}
                      <small>{j.id.slice(0, 8)}</small>
                    </td>
                    <td>
                      <code>{j.algorithm_version}</code>
                    </td>
                    <td>{new Date(j.started_at).toISOString()}</td>
                    <td>
                      <span className={`job-status ${j.status}`}>{j.status}</span>
                    </td>
                    <td>
                      <details>
                        <summary>View metadata</summary>
                        <pre>{JSON.stringify(j.output_metadata, null, 2)}</pre>
                        {j.error_message && <p>{j.error_message}</p>}
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state compact">
            {busy
              ? 'Loading processing history…'
              : error
                ? 'Processing history unavailable.'
                : 'No processing jobs yet.'}
          </div>
        )}
      </section>
      <div className="science-note">
        <FileCheck2 size={16} />
        <p>
          Source hashes establish file identity, not authenticity. User-supplied NASA exports retain their
          attribution; exact payload duplicates share a normalized record; changed fields and NRT/standard
          revisions remain distinct, with all raw copies retained.
        </p>
      </div>
    </>
  );
}

type EnginePeriod = {
  label: string;
  raw_modis: number | null;
  raw_viirs: number | null;
  accepted_count: number | null;
  unified_cell_days: number | null;
  frp_before_modis: number | null;
  frp_before_viirs: number | null;
  frp_after_total: number | null;
};
type EngineMember = {
  id: number;
  sensor_code: string;
  latitude: number;
  longitude: number;
  confidence_native: string;
  frp_mw: number | null;
  brightness_k: number | null;
  brightness_field: string;
  daynight: string | null;
  source_id: string;
  source_row: number;
};
type EngineCell = {
  key: string;
  acq_date: string;
  grid_id: string;
  grid_lat: number;
  grid_lon: number;
  unified_fire_count: number;
  raw_detections_count: number;
  total_frp_mw: number | null;
  mean_frp_mw: number | null;
  frp_known_count: number;
  max_temp_k: number | null;
  temperature_known_count: number;
  sensors_involved: string[];
  day_detections: number;
  night_detections: number;
  members: EngineMember[];
  members_truncated: boolean;
};
type EngineResult = {
  analysis_id: string;
  algorithm_version: string;
  query: unknown;
  available_years: number[];
  summary: {
    input_detections: number;
    accepted_detections: number;
    rejected_detections: number;
    retention_percent: number | null;
    unified_cell_days: number;
    total_frp_mw: number | null;
    frp_known_count: number;
  };
  annual: EnginePeriod[];
  monthly: EnginePeriod[];
  cells: EngineCell[];
  cells_total: number;
  cells_truncated: boolean;
  overlap: {
    modis_detections: number;
    viirs_detections: number;
    shared_cell_days: number;
    modis_only_cell_days: number;
    viirs_only_cell_days: number;
    union_cell_days: number;
    jaccard: number | null;
    both_families_present: boolean;
  };
  sources: {
    id: string;
    original_filename: string;
    sha256: string;
    source_url: string | null;
    sensor_code: string;
    product_version: string;
    processing_level: string;
  }[];
};
const engineStages = [
  'Confidence filtering',
  'Schema alignment',
  'Spatial harmonization',
  'Daily aggregation',
  'Historical overlap',
];
const engineMonths = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];
function engineValue(value: number | null | undefined, suffix = '') {
  return value == null
    ? 'Unknown'
    : `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`;
}

function SensorIllustration() {
  const [cycle, setCycle] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [merged, setMerged] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  function play() {
    setCycle((n) => n + 1);
    setMerged(false);
    setPlaying(true);
    timer.current = setTimeout(
      () => {
        setMerged(true);
        setPlaying(false);
      },
      window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 1600,
    );
  }
  const points = [
    [742, 66],
    [800, 66],
    [858, 124],
    [742, 182],
    [800, 182],
    [858, 182],
  ];
  return (
    <section className="engine-intro" aria-labelledby="engine-sensor-title">
      <div className="engine-section-heading">
        <div>
          <h2 id="engine-sensor-title">One area. Different observations.</h2>
          <p>
            A finer pixel can reveal several thermal detections within the footprint of a coarser observation.
          </p>
        </div>
        <button className="button secondary" onClick={play} disabled={playing}>
          <Play size={15} />
          {playing ? 'Grouping…' : merged ? 'Replay grouping' : 'Show the transformation'}
        </button>
      </div>
      <svg
        className="engine-diagram"
        viewBox="0 0 1000 250"
        role="img"
        aria-label="Illustrative MODIS and VIIRS detections converge on a shared grid-cell day"
      >
        <rect
          x="100"
          y="36"
          width="184"
          height="184"
          fill="var(--orange)"
          fillOpacity=".06"
          stroke="var(--orange)"
        />
        <rect
          x="410"
          y="36"
          width="184"
          height="184"
          fill="var(--blue)"
          fillOpacity=".04"
          stroke="var(--blue)"
          strokeDasharray="5 5"
        />
        {[0, 1, 2].flatMap((row) =>
          [0, 1, 2].map((col) => (
            <rect
              key={`${row}-${col}`}
              x={714 + col * 58}
              y={36 + row * 62}
              width="52"
              height="60"
              fill="var(--blue)"
              fillOpacity=".05"
              stroke="var(--blue)"
            />
          )),
        )}
        <path d="M315 128h60m-10-8 10 8-10 8M684 128h-60m10-8-10 8 10 8" fill="none" stroke="var(--blue)" />
        <g key={cycle} className={playing ? 'engine-moving' : ''} opacity={merged ? 0 : 1}>
          {[[192, 128], ...points].map(([x, y], i) => (
            <circle
              key={i}
              className="engine-dot"
              cx={x}
              cy={y}
              r="7"
              fill="var(--orange)"
              style={{ '--dx': `${502 - x}px`, '--dy': `${128 - y}px` } as CSSProperties}
            />
          ))}
        </g>
        {merged && <circle cx="502" cy="128" r="18" fill="var(--blue)" />}
      </svg>
      <div className="engine-diagram-labels">
        <div>
          <strong>MODIS</strong>
          <span>Terra & Aqua · nominal 1 km</span>
          <span>Terra record from 2000 · Aqua from 2002</span>
          <span>Numeric confidence · brightness</span>
        </div>
        <div>
          <strong>{merged ? '1 grid-cell day' : 'Shared spatial unit'}</strong>
          <span>Prototype 0.01° grid × UTC day</span>
          <span>Approximately kilometre-scale</span>
          <span>One count per occupied cell and day</span>
        </div>
        <div>
          <strong>VIIRS</strong>
          <span>S-NPP · NOAA-20 · NOAA-21 · 375 m</span>
          <span>S-NPP archive from 2012 · NOAA platforms later</span>
          <span>Categorical confidence · bright_ti4</span>
        </div>
      </div>
      <p className="engine-caption" role="status">
        Illustrative geometry. The six VIIRS points demonstrate grouping, with no fixed MODIS-to-VIIRS
        detection ratio. Actual pixel footprints and detections vary.
      </p>
      <p>
        Different sensors can observe the same fire at different spatial resolutions. PIRX converts their
        detections into a shared spatial and temporal framework to improve comparability.
      </p>
    </section>
  );
}

export default function Sources() {
  const [studyArea, setStudyArea] = useState('jordan');
  const [year, setYear] = useState(2024),
    [month, setMonth] = useState(7);
  const [family, setFamily] = useState('both'),
    [confidence, setConfidence] = useState(50);
  const [viirsConfidence, setViirsConfidence] = useState('nominal_high');
  const [stage, setStage] = useState(0),
    [metric, setMetric] = useState('unified');
  const [resolution, setResolution] = useState<'annual' | 'monthly'>('annual');
  const [revision, setRevision] = useState(0),
    [cellKey, setCellKey] = useState('');
  const [archiveMounted, setArchiveMounted] = useState(false);
  const beforeChart = useRef<HTMLDivElement>(null),
    afterChart = useRef<HTMLDivElement>(null);
  const stageButtons = useRef<(HTMLButtonElement | null)[]>([]);
  const instanceId = useId(),
    chartGroup = `harmonization-${instanceId}`;
  const query = useMemo(
    () => ({
      year,
      month,
      sensor_family: family,
      modis_confidence_min: confidence,
      viirs_confidence: viirsConfidence,
      bbox: studyArea === 'levant' ? [34, 29, 43, 38] : [34, 29, 40, 34],
    }),
    [year, month, family, confidence, viirsConfidence, studyArea],
  );
  const resource = useResource(
    JSON.stringify(query),
    (signal) => request<EngineResult>('/analytics/harmonization', signal, query),
    revision,
  );
  const data = resource.data,
    summary = data?.summary,
    overlap = data?.overlap;
  const periods = useMemo(() => data?.[resolution] ?? [], [data, resolution]);
  const labels = useMemo(() => periods.map((p) => p.label), [periods]);
  const cell = data?.cells.find((c) => c.key === cellKey) ?? data?.cells[0];
  const beforeSeries = useMemo(
    () => [
      {
        name: metric === 'frp' ? 'MODIS FRP (MW)' : 'MODIS raw detections',
        color: theme.orange,
        values: periods.map((p) => (metric === 'frp' ? p.frp_before_modis : p.raw_modis)),
      },
      {
        name: metric === 'frp' ? 'VIIRS FRP (MW)' : 'VIIRS raw detections',
        color: theme.blue,
        dashed: true,
        values: periods.map((p) => (metric === 'frp' ? p.frp_before_viirs : p.raw_viirs)),
      },
    ],
    [metric, periods],
  );
  const afterSeries = useMemo(
    () => [
      {
        name:
          metric === 'frp'
            ? 'Accepted FRP sum (MW)'
            : metric === 'raw'
              ? 'Accepted raw detections'
              : 'Unified grid-cell days',
        color: theme.blue,
        values: periods.map((p) =>
          metric === 'frp' ? p.frp_after_total : metric === 'raw' ? p.accepted_count : p.unified_cell_days,
        ),
      },
    ],
    [metric, periods],
  );
  useEffect(() => {
    const charts = [beforeChart, afterChart]
      .map((ref) => ref.current?.querySelector<HTMLElement>('.scientific-chart'))
      .map((node) => (node ? echarts.getInstanceByDom(node) : undefined))
      .filter((chart) => chart !== undefined);
    if (!charts.length) return;
    charts.forEach((chart) => {
      chart.group = chartGroup;
      const annotations = [];
      if (resolution === 'annual' && labels.includes('2012'))
        annotations.push({
          xAxis: '2012',
          name: 'VIIRS archive begins',
          label: { formatter: 'VIIRS 2012', position: 'insideEndTop' },
        });
      const selected = resolution === 'annual' ? String(year) : `${year}-${String(month).padStart(2, '0')}`;
      if (labels.includes(selected))
        annotations.push({
          xAxis: selected,
          name: 'Selected period',
          label: { formatter: 'Selected', position: 'insideEndTop' },
        });
      chart.setOption({
        series: [
          {
            markLine: {
              symbol: 'none',
              silent: true,
              lineStyle: { color: theme.rule, type: 'dashed' },
              data: annotations,
            },
          },
        ],
      });
    });
    echarts.connect(chartGroup);
    return () => {
      echarts.disconnect(chartGroup);
    };
  }, [data, metric, resolution, year, month, labels, chartGroup]);
  const metadata = data
    ? {
        analysis_id: data.analysis_id,
        algorithm_version: data.algorithm_version,
        selection: query,
        coverage: 'unknown',
        count_unit: 'occupied prototype grid cell × UTC day',
        sources: data.sources,
      }
    : undefined;
  const years = Array.from(
    { length: Math.max(new Date().getUTCFullYear(), 2024) - 1999 },
    (_, i) => i + 2000,
  );
  return (
    <div className="harmonization-engine">
      <style>{engineStyles}</style>
      <header className="page-header">
        <div>
          <p className="engine-kicker">Scientific method · Interactive prototype</p>
          <h1>
            The harmonization engine<span>.</span>
          </h1>
          <p>Turning incompatible satellite observations into a consistent fire activity record.</p>
        </div>
        <button
          className="button secondary"
          onClick={() => setRevision((n) => n + 1)}
          disabled={resource.loading}
        >
          <RefreshCw size={15} /> Refresh
        </button>
      </header>
      <SensorIllustration />
      <section aria-labelledby="engine-selection-title">
        <div className="engine-section-heading">
          <div>
            <h2 id="engine-selection-title">
              <SlidersHorizontal size={20} /> Explore the archive
            </h2>
            <p>Change the selection to recalculate the pipeline, comparisons and cell-day evidence.</p>
          </div>
        </div>
        <div className="engine-controls">
          <label>
            Study area
            <select value={studyArea} onChange={(e) => setStudyArea(e.target.value)}>
              <option value="jordan">Jordan study envelope</option>
              <option value="levant">Levant study envelope</option>
            </select>
          </label>
          <label>
            Sensor family
            <select value={family} onChange={(e) => setFamily(e.target.value)}>
              <option value="both">MODIS + VIIRS</option>
              <option value="MODIS">MODIS</option>
              <option value="VIIRS">VIIRS</option>
            </select>
          </label>
          <label>
            Year
            <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
              {years.map((y) => (
                <option key={y}>{y}</option>
              ))}
            </select>
          </label>
          <label>
            Calendar month
            <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>
              {engineMonths.map((m, i) => (
                <option key={m} value={i + 1}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <label>
            MODIS minimum confidence
            <select value={confidence} onChange={(e) => setConfidence(Number(e.target.value))}>
              {[0, 30, 50, 80, 100].map((n) => (
                <option key={n} value={n}>
                  {n}
                  {n === 50 ? ' · prototype default' : ''}
                </option>
              ))}
            </select>
          </label>
          <label>
            VIIRS confidence
            <select value={viirsConfidence} onChange={(e) => setViirsConfidence(e.target.value)}>
              <option value="nominal_high">Nominal + High</option>
              <option value="high">High</option>
              <option value="all">Low + Nominal + High</option>
            </select>
          </label>
        </div>
        <p className="engine-caption">
          {studyArea === 'levant'
            ? 'Levant study area · 34°–43° E, 29°–38° N'
            : 'Jordan study area · 34°–40° E, 29°–34° N'}{' '}
          · UTC · includes nearby territory. All comparisons use this same bounding box. Observation coverage
          remains unknown.
        </p>
        {resource.loading && (
          <div role="status" className="engine-request-state">
            Loading archived observations and calculating cell-days…
          </div>
        )}
        {resource.error && (
          <div role="alert" className="connection-notice">
            <p>{resource.error}</p>
            <p>
              Connect the FastAPI service and PostGIS archive to calculate scientific results. The sensor
              illustration remains available as an explicitly illustrative example.
            </p>
          </div>
        )}
        {data && !summary?.input_detections && (
          <p role="status">
            No archived observations match this month and sensor selection. Archive absence leaves actual
            burning activity unknown.
          </p>
        )}
        <dl className="engine-facts">
          <div>
            <dt>Input detections</dt>
            <dd>{engineValue(summary?.input_detections)}</dd>
            <p>Canonical archived observations in the selected month before confidence filtering.</p>
          </div>
          <div>
            <dt>Accepted detections</dt>
            <dd>{engineValue(summary?.accepted_detections)}</dd>
            <p>Observations passing each instrument’s native confidence rule.</p>
          </div>
          <div>
            <dt>Unified grid-cell days</dt>
            <dd>{engineValue(summary?.unified_cell_days)}</dd>
            <p>Occupied 0.01° prototype cells, counted once per UTC day.</p>
          </div>
        </dl>
      </section>
      <section aria-labelledby="engine-pipeline-title">
        <div className="engine-section-heading">
          <div>
            <h2 id="engine-pipeline-title">From native observations to a shared record</h2>
            <p>Follow each transformation and inspect its scientific meaning.</p>
          </div>
          <Layers2 size={22} />
        </div>
        <div className="engine-stages" role="tablist" aria-label="Harmonization stages">
          {engineStages.map((name, i) => (
            <button
              key={name}
              ref={(el) => {
                stageButtons.current[i] = el;
              }}
              role="tab"
              id={`${instanceId}-tab-${i}`}
              aria-controls={`${instanceId}-stage`}
              aria-selected={stage === i}
              tabIndex={stage === i ? 0 : -1}
              onClick={() => setStage(i)}
              onKeyDown={(e) => {
                let next = i;
                if (e.key === 'ArrowRight') next = (i + 1) % 5;
                else if (e.key === 'ArrowLeft') next = (i + 4) % 5;
                else if (e.key === 'Home') next = 0;
                else if (e.key === 'End') next = 4;
                else return;
                e.preventDefault();
                setStage(next);
                stageButtons.current[next]?.focus();
              }}
            >
              <span>0{i + 1}</span>
              {name}
            </button>
          ))}
        </div>
        <div
          className="engine-stage-content"
          id={`${instanceId}-stage`}
          role="tabpanel"
          aria-labelledby={`${instanceId}-tab-${stage}`}
          tabIndex={0}
        >
          {stage === 0 && (
            <>
              <h3>Keep confidence in its native scale</h3>
              <p>
                Numeric MODIS confidence and categorical VIIRS confidence describe instrument-specific
                retrieval quality. The selected rules control inclusion independently.
              </p>
              <div className="engine-rules">
                <code>MODIS confidence ≥ {confidence}</code>
                <code>
                  VIIRS ∈{' '}
                  {viirsConfidence === 'all'
                    ? '{ l, low, n, nominal, h, high }'
                    : viirsConfidence === 'high'
                      ? '{ h, high }'
                      : '{ n, nominal, h, high }'}
                </code>
              </div>
              <dl className="engine-facts">
                <div>
                  <dt>Rejected detections</dt>
                  <dd>{engineValue(summary?.rejected_detections)}</dd>
                  <p>Input minus accepted observations, including missing or unrecognized confidence.</p>
                </div>
                <div>
                  <dt>Retention</dt>
                  <dd>{engineValue(summary?.retention_percent, '%')}</dd>
                  <p>100 × accepted / input. Unknown when the input is empty.</p>
                </div>
                <div>
                  <dt>Accepted detections</dt>
                  <dd>{engineValue(summary?.accepted_detections)}</dd>
                  <p>Filtering changes counts and the pool used for every subsequent statistic.</p>
                </div>
              </dl>
            </>
          )}
          {stage === 1 && (
            <>
              <h3>One schema, preserved instrument context</h3>
              <div className="table-scroll" role="region" aria-label="Schema alignment" tabIndex={0}>
                <table>
                  <thead>
                    <tr>
                      <th>MODIS</th>
                      <th>VIIRS</th>
                      <th>Unified field</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ['latitude', 'latitude', 'latitude'],
                      ['longitude', 'longitude', 'longitude'],
                      ['acq_date', 'acq_date', 'acq_date · UTC'],
                      ['brightness', 'bright_ti4', 'brightness_k'],
                      ['frp', 'frp', 'frp_mw'],
                      ['confidence', 'confidence', 'confidence_native'],
                      ['daynight', 'daynight', 'daynight'],
                    ].map((row) => (
                      <tr key={row[0]}>
                        {row.map((v, i) => (
                          <td key={i}>
                            <code>{v}</code>
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="engine-caption">
                Field names and types are standardized. Native confidence, brightness field, instrument,
                source file and source row remain traceable. Brightness temperatures use kelvin and retain
                their different spectral-band contexts.
              </p>
            </>
          )}
          {stage === 2 && (
            <>
              <h3>A shared, approximate spatial unit</h3>
              <pre>
                {
                  'grid_lat = Math.round(latitude * 100) / 100\ngrid_lon = Math.round(longitude * 100) / 100\ngrid_id = grid_lat.toFixed(2) + "_" + grid_lon.toFixed(2)'
                }
              </pre>
              <p>
                The prototype snaps coordinates to 0.01° grid centres. MODIS and VIIRS detections assigned to
                the same centre can contribute to the same cell-day.
              </p>
              <p className="engine-caption">
                Angular cell dimensions vary with latitude. This kilometre-scale approximation requires
                additional spatial validation for operational use. Nominal sensor footprints can cross these
                grid boundaries.
              </p>
              {cell && (
                <p className="engine-inline-result">
                  <Grid2X2 size={18} /> Selected cell {cell.grid_id} · centre {cell.grid_lat}° N,{' '}
                  {cell.grid_lon}° E
                </p>
              )}
            </>
          )}
          {stage === 3 && (
            <>
              <h3>Count an occupied cell once each day</h3>
              <p>
                <code>acq_date + grid_id</code> groups accepted observations into a common spatial and UTC-day
                unit.
              </p>
              <div
                className="table-scroll"
                role="region"
                aria-label="Cell-day aggregation metrics"
                tabIndex={0}
              >
                <table>
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>Calculation and interpretation</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>
                        <code>unified_fire_count</code>
                      </td>
                      <td>1 per occupied grid-cell day. A spatial activity-counting unit.</td>
                    </tr>
                    <tr>
                      <td>
                        <code>raw_detections_count</code>
                      </td>
                      <td>COUNT(*) of contributing accepted observations.</td>
                    </tr>
                    <tr>
                      <td>
                        <code>total_frp_mw</code>
                      </td>
                      <td>SUM of known FRP values in MW, across contributing overpasses.</td>
                    </tr>
                    <tr>
                      <td>
                        <code>mean_frp_mw</code>
                      </td>
                      <td>AVG of known observation FRP values in MW.</td>
                    </tr>
                    <tr>
                      <td>
                        <code>max_temp_k</code>
                      </td>
                      <td>MAX native-band brightness temperature in K, retaining instrument context.</td>
                    </tr>
                    <tr>
                      <td>
                        <code>sensors_involved</code>
                      </td>
                      <td>Unique contributing instrument codes.</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p className="engine-caption">
                A physical fire may span several cells and days. FRP describes radiative power, while a sum
                across overpasses describes the sampled detections. Burned area, instantaneous regional power
                and unique wildfire counts require separate methods. All-missing measurements stay unknown.
              </p>
            </>
          )}
          {stage === 4 && (
            <>
              <h3>Evaluate the common observation period</h3>
              <p>
                2012–2024 · {engineMonths[month - 1]} in every year · same study area and confidence rules.
                Both families are included in this reference comparison.
              </p>
              <dl className="engine-facts">
                <div>
                  <dt>MODIS accepted observations</dt>
                  <dd>{engineValue(overlap?.modis_detections)}</dd>
                  <p>Native detections passing the MODIS rule.</p>
                </div>
                <div>
                  <dt>VIIRS accepted observations</dt>
                  <dd>{engineValue(overlap?.viirs_detections)}</dd>
                  <p>Native detections passing the VIIRS rule.</p>
                </div>
                <div>
                  <dt>Shared grid-cell days</dt>
                  <dd>{engineValue(overlap?.shared_cell_days)}</dd>
                  <p>Cell-days observed by both families.</p>
                </div>
                <div>
                  <dt>MODIS-only cell-days</dt>
                  <dd>{engineValue(overlap?.modis_only_cell_days)}</dd>
                  <p>Observed MODIS cell-days without a VIIRS match.</p>
                </div>
                <div>
                  <dt>VIIRS-only cell-days</dt>
                  <dd>{engineValue(overlap?.viirs_only_cell_days)}</dd>
                  <p>Observed VIIRS cell-days without a MODIS match.</p>
                </div>
                <div>
                  <dt>Observed overlap</dt>
                  <dd>{engineValue(overlap?.jaccard == null ? null : overlap.jaccard * 100, '%')}</dd>
                  <p>100 × shared / union cell-days. Conditional on archived observations.</p>
                </div>
              </dl>
              {overlap && !overlap.both_families_present && (
                <p>
                  Both sensor families have yet to be represented in the selected overlap sample. Sensor
                  agreement remains unevaluated.
                </p>
              )}
              <p className="engine-caption">
                Sensitivity, overpass time, clouds and viewing geometry can still affect agreement. Missing
                coverage prevents a complete comparison. This diagnostic provides evidence for validation of
                sensor differences.
              </p>
            </>
          )}
        </div>
      </section>
      <section aria-labelledby="engine-comparison-title">
        <div className="engine-section-heading">
          <div>
            <h2 id="engine-comparison-title">Before & after harmonization</h2>
            <p>
              {resolution === 'annual'
                ? `${engineMonths[month - 1]} compared across years`
                : `Monthly observations in ${year}`}{' '}
              · equivalent geographic area.
            </p>
          </div>
        </div>
        <div className="engine-chart-controls">
          <div className="engine-segmented" role="group" aria-label="Comparison metric">
            {[
              ['raw', 'Raw hotspot counts'],
              ['unified', 'Unified fire events'],
              ['frp', 'Total FRP (MW)'],
            ].map(([key, label]) => (
              <button
                key={key}
                className="button secondary"
                aria-pressed={metric === key}
                onClick={() => setMetric(key)}
              >
                {label}
              </button>
            ))}
          </div>
          <label>
            Time scale
            <select
              value={resolution}
              onChange={(e) => setResolution(e.target.value as 'annual' | 'monthly')}
            >
              <option value="annual">Same month across years</option>
              <option value="monthly">Months of selected year</option>
            </select>
          </label>
        </div>
        <div className="engine-chart-pair">
          <div ref={beforeChart}>
            <h3>Before harmonization</h3>
            <p className="engine-caption">
              {metric === 'frp'
                ? 'Known FRP sums by family, before confidence filtering.'
                : 'Raw detections by family, before confidence filtering.'}
            </p>
            <ScientificChart
              labels={labels}
              series={beforeSeries}
              title="Before harmonization"
              metadata={metadata}
            />
          </div>
          <div ref={afterChart}>
            <h3>After harmonization</h3>
            <p className="engine-caption">
              {metric === 'frp'
                ? 'Accepted known FRP sum across overpasses, separate from counts.'
                : metric === 'raw'
                  ? 'Accepted detections, before cell-day aggregation.'
                  : 'Unified events use the occupied 0.01° grid-cell day as their counting unit.'}
            </p>
            <ScientificChart
              labels={labels}
              series={afterSeries}
              title="After harmonization"
              metadata={metadata}
            />
          </div>
        </div>
        <p className="engine-caption">
          Charts share their hover position and include accessible data tables and SVG exports. Gaps indicate
          absent archived observations. Observed counts can reflect incomplete sampling. The 2012 annotation
          marks the start of the S-NPP VIIRS record when that year is within the chart range. Confidence
          filtering can also change totals.
        </p>
      </section>
      <section aria-labelledby="engine-cell-title">
        <div className="engine-section-heading">
          <div>
            <h2 id="engine-cell-title">Inspect a grid-cell day</h2>
            <p>Follow an aggregate back to its contributing observations.</p>
          </div>
          <Grid2X2 size={22} />
        </div>
        <label className="engine-cell-select">
          Archived cell-day
          <select
            value={cell?.key ?? ''}
            disabled={!data?.cells.length}
            onChange={(e) => setCellKey(e.target.value)}
          >
            {!data?.cells.length && <option value="">No cell-days available</option>}
            {data?.cells.map((c) => (
              <option key={c.key} value={c.key}>
                {c.acq_date} · {c.grid_id} · {c.raw_detections_count} detections
              </option>
            ))}
          </select>
        </label>
        {cell ? (
          <>
            <dl className="engine-facts">
              <div>
                <dt>Unified event count</dt>
                <dd>{cell.unified_fire_count}</dd>
                <p>One occupied cell × UTC day.</p>
              </div>
              <div>
                <dt>Raw detections</dt>
                <dd>{engineValue(cell.raw_detections_count)}</dd>
                <p>Accepted observations assigned to this cell-day.</p>
              </div>
              <div>
                <dt>FRP sum</dt>
                <dd>{engineValue(cell.total_frp_mw, ' MW')}</dd>
                <p>Sum across {cell.frp_known_count} known sampled values.</p>
              </div>
              <div>
                <dt>Mean observation FRP</dt>
                <dd>{engineValue(cell.mean_frp_mw, ' MW')}</dd>
                <p>Known-value mean across contributing observations.</p>
              </div>
              <div>
                <dt>Maximum brightness</dt>
                <dd>{engineValue(cell.max_temp_k, ' K')}</dd>
                <p>Maximum of {cell.temperature_known_count} known native-band temperatures.</p>
              </div>
              <div>
                <dt>Day / night detections</dt>
                <dd>
                  {cell.day_detections} / {cell.night_detections}
                </dd>
                <p>Native D / N flags. Remaining flags are unknown.</p>
              </div>
            </dl>
            <p>
              Contributing sensors · <strong>{cell.sensors_involved.join(', ')}</strong>
            </p>
            <details>
              <summary>Inspect native observations and source rows</summary>
              <div className="table-scroll" role="region" aria-label="Contributing observations" tabIndex={0}>
                <table>
                  <thead>
                    <tr>
                      <th>Sensor / observation</th>
                      <th>Coordinates</th>
                      <th>Native confidence</th>
                      <th>FRP (MW)</th>
                      <th>Brightness (K)</th>
                      <th>Source / row</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cell.members.map((m) => (
                      <tr key={m.id}>
                        <td>
                          {m.sensor_code}
                          <small>
                            Observation {m.id} · {m.daynight ?? 'Unknown'}
                          </small>
                        </td>
                        <td>
                          {m.latitude}, {m.longitude}
                        </td>
                        <td>{m.confidence_native}</td>
                        <td>{engineValue(m.frp_mw)}</td>
                        <td>
                          {engineValue(m.brightness_k)}
                          <small>{m.brightness_field}</small>
                        </td>
                        <td>
                          <code>{m.source_id}</code>
                          <small>Row {m.source_row}</small>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {cell.members_truncated && (
                <p className="engine-caption">
                  Showing the first 20 members. Statistics include every contributing observation.
                </p>
              )}
            </details>
          </>
        ) : (
          <p className="engine-caption">
            Select a period with accepted archived observations to inspect its spatial and radiometric
            evidence.
          </p>
        )}
        {data?.cells_truncated && (
          <p className="engine-caption">
            Showing the first 200 of {data.cells_total.toLocaleString()} cell-days. Summary statistics and
            charts include the entire selection.
          </p>
        )}
      </section>
      <HarmonizationValidation />
      <section aria-labelledby="engine-why-title">
        <div className="engine-section-heading">
          <h2 id="engine-why-title">Why harmonization matters</h2>
        </div>
        <div className="engine-explanations">
          {[
            [
              'Spatial resolution',
              'MODIS and VIIRS use different pixel sizes. A shared spatial unit reduces the influence of counting multiple finer-resolution detections in one cell.',
            ],
            [
              'Detection sensitivity',
              'VIIRS can detect smaller or weaker thermal anomalies, including at night. Grouping retains these observations while exposing their instrument context.',
            ],
            [
              'Temporal consistency',
              'Sensor availability and observation characteristics can change raw counts. Historical interpretation also requires coverage, season and geography to be comparable.',
            ],
            [
              'Comparable historical records',
              'Grid-cell days provide a consistent counting framework. Independent overlap validation is needed to quantify remaining differences between instruments.',
            ],
            [
              'Multi-dimensional analysis',
              'Cell-day counts, radiative power, native-band brightness and day/night flags describe different aspects of thermal activity. Each retains its own units and interpretation.',
            ],
          ].map(([title, text]) => (
            <div key={title}>
              <h3>{title}</h3>
              <p>{text}</p>
            </div>
          ))}
        </div>
      </section>
      <section aria-labelledby="engine-evidence-title">
        <h2 id="engine-evidence-title">Evidence & limitations</h2>
        <p>
          This read-only prototype calculates from canonical archived observations and their primary
          raw-source records. The established versioned harmonization pipeline remains the source for its
          persisted products. Operational calibration requires independent validation.
        </p>
        <p className="engine-caption">
          Archive absence leaves coverage unknown. These outputs describe sampled thermal activity. Fire-risk
          forecasting and causal attribution require separate evidence. Native-band brightness temperatures
          and repeated-overpass FRP sums require instrument-aware interpretation.
        </p>
        <p className="engine-references">
          <a href="https://firms.modaps.eosdis.nasa.gov/alerts/notes.php" target="_blank" rel="noreferrer">
            NASA FIRMS sensor notes <ArrowRight size={13} />
          </a>
          <a
            href="https://developers.google.com/earth-engine/datasets/catalog/NASA_LANCE_SNPP_VIIRS_C2"
            target="_blank"
            rel="noreferrer"
          >
            VIIRS field definitions <ArrowRight size={13} />
          </a>
        </p>
        {data && (
          <details>
            <summary>Reproducible analysis metadata & source checksums</summary>
            <pre>
              {JSON.stringify(
                {
                  ...metadata,
                  interpretation: 'Prototype grid-cell days quantify observed thermal activity.',
                },
                null,
                2,
              )}
            </pre>
          </details>
        )}
      </section>
      <details
        className="engine-archive"
        onToggle={(e) => {
          if (e.currentTarget.open) setArchiveMounted(true);
        }}
      >
        <summary>
          <Database size={18} /> Source archive & processing history
        </summary>
        {archiveMounted && <ProvenanceArchive />}
      </details>
    </div>
  );
}

const engineStyles = `
.harmonization-engine .engine-validation-controls {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr));
  gap: 24px;
  max-width: 760px;
  margin-bottom: 24px;
}
.harmonization-engine .engine-validation-subheading {
  margin-top: 36px;
}
.harmonization-engine .engine-validation-limitations {
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.8;
}
.harmonization-engine .engine-validation-export {
  margin-top: 28px;
}
.harmonization-engine .engine-validation caption {
  text-align: left;
  padding-bottom: 18px;
  font-size: 12px;
}
.harmonization-engine .engine-validation .engine-facts dd {
  font-size: clamp(20px, 2.4vw, 28px);
  overflow-wrap: anywhere;
}
.harmonization-engine {
  min-width: 0;
}
.harmonization-engine > section {
  margin-bottom: 64px;
}
.harmonization-engine .page-header {
  align-items: flex-start;
  margin-bottom: 44px;
}
.harmonization-engine .engine-kicker {
  font-family: var(--font-data);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.09em;
  margin-bottom: 14px;
}
.harmonization-engine h2 {
  font-size: clamp(23px, 2.3vw, 29px);
  display: flex;
  gap: 10px;
  align-items: center;
}
.harmonization-engine h3 {
  font-size: 18px;
  margin: 0 0 12px;
}
.harmonization-engine p {
  line-height: 1.65;
}
.harmonization-engine .engine-section-heading {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: center;
  margin-bottom: 24px;
}
.harmonization-engine .engine-section-heading p {
  margin: 8px 0 0;
}
.harmonization-engine .engine-diagram {
  display: block;
  width: 100%;
  max-height: 270px;
  overflow: visible;
}
.harmonization-engine .engine-diagram-labels {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  text-align: center;
  gap: 18px;
  margin: 10px 0 22px;
}
.harmonization-engine .engine-diagram-labels strong {
  font-family: var(--font-heading);
  display: block;
  font-size: 19px;
  margin-bottom: 8px;
}
.harmonization-engine .engine-diagram-labels span {
  display: block;
  font-size: 12px;
  line-height: 1.8;
}
.harmonization-engine .engine-caption {
  font-size: 12px;
  line-height: 1.75;
  margin: 14px 0;
}
.harmonization-engine .engine-controls {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
}
.harmonization-engine label {
  display: flex;
  flex-direction: column;
  gap: 9px;
  font-size: 12px;
}
.harmonization-engine select {
  width: 100%;
  min-width: 0;
  padding: 10px 30px 10px 10px;
  min-height: 42px;
  font: inherit;
  color: inherit;
  background: transparent;
}
.harmonization-engine .engine-facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 28px;
  margin: 30px 0;
}
.harmonization-engine .engine-facts dt {
  font-size: 13px;
}
.harmonization-engine .engine-facts dd {
  font: 500 clamp(23px, 3vw, 35px) / 1.3 var(--font-heading);
  margin: 8px 0;
}
.harmonization-engine .engine-facts p {
  font-size: 12px;
  max-width: 330px;
  margin: 0;
}
.harmonization-engine .engine-request-state {
  padding: 20px 0;
  font-size: 13px;
}
.harmonization-engine .engine-stages {
  display: flex;
  gap: 14px;
  overflow-x: auto;
  margin: 32px 0;
}
.harmonization-engine .engine-stages button {
  flex: 1 0 130px;
  text-align: left;
  background: transparent;
  color: inherit;
  border: 0;
  border-bottom: 2px solid transparent;
  padding: 12px 0 15px;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
.harmonization-engine .engine-stages button[aria-selected="true"] {
  border-bottom-color: var(--blue);
  color: var(--blue);
}
.harmonization-engine .engine-stages button span {
  display: block;
  font: 12px var(--font-data);
  margin-bottom: 10px;
}
.harmonization-engine .engine-stage-content {
  min-height: 275px;
}
.harmonization-engine .engine-rules {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  margin: 24px 0;
  font-size: 13px;
}
.harmonization-engine pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 12px;
  line-height: 1.9;
  padding: 18px 0;
  background: transparent;
}
.harmonization-engine .engine-inline-result {
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: var(--font-data);
  font-size: 13px;
}
.harmonization-engine .engine-chart-controls {
  display: flex;
  gap: 24px;
  justify-content: space-between;
  align-items: end;
  margin-bottom: 32px;
  flex-wrap: wrap;
}
.harmonization-engine .engine-segmented {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.harmonization-engine .engine-segmented button[aria-pressed="true"] {
  color: var(--blue);
  border-bottom: 2px solid var(--blue);
}
.harmonization-engine .engine-chart-pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 32px;
}
.harmonization-engine .engine-chart-pair > div {
  min-width: 0;
}
.harmonization-engine .engine-chart-pair .engine-caption {
  min-height: 44px;
}
.harmonization-engine .engine-cell-select {
  max-width: 480px;
}
.harmonization-engine .engine-explanations {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 32px;
}
.harmonization-engine .engine-explanations p {
  font-size: 13px;
  margin: 0;
}
.harmonization-engine .engine-references {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  font-size: 12px;
}
.harmonization-engine .engine-references a {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}
.harmonization-engine summary {
  cursor: pointer;
  padding: 14px 0;
  font-size: 13px;
}
.harmonization-engine .engine-archive > summary {
  display: flex;
  gap: 10px;
  align-items: center;
  font-size: 17px;
}
.harmonization-engine .engine-archive > summary::after {
  content: "+";
  margin-left: auto;
}
.harmonization-engine .engine-archive[open] > summary::after {
  content: "−";
}
.harmonization-engine .engine-provenance-heading {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: center;
  margin: 24px 0;
}
.harmonization-engine .engine-moving .engine-dot {
  animation: engine-converge 1.5s ease-in-out forwards;
}
@keyframes engine-converge {
  0%,
  15% {
    transform: translate(0, 0);
  }
  100% {
    transform: translate(var(--dx), var(--dy));
  }
}
@media (max-width: 1100px) {
  .harmonization-engine .engine-controls {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .harmonization-engine .engine-chart-pair {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 640px) {
  .harmonization-engine > section {
    margin-bottom: 44px;
  }
  .harmonization-engine .engine-section-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 14px;
  }
  .harmonization-engine .engine-controls,
  .harmonization-engine .engine-facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 20px;
  }
  .harmonization-engine .engine-diagram-labels {
    gap: 8px;
  }
  .harmonization-engine .engine-diagram-labels span {
    font-size: 11px;
  }
  .harmonization-engine .engine-diagram-labels strong {
    font-size: 15px;
  }
  .harmonization-engine .engine-explanations {
    grid-template-columns: 1fr;
    gap: 22px;
  }
  .harmonization-engine .engine-chart-controls {
    align-items: stretch;
    flex-direction: column;
  }
  .harmonization-engine .engine-provenance-heading {
    flex-direction: column;
    align-items: flex-start;
  }
}
@media (prefers-reduced-motion: reduce) {
  .harmonization-engine .engine-moving .engine-dot {
    animation: none;
  }
}
`;

type AgreementMetrics = { n: number; mae: number | null; rmse: number | null; bias: number | null };
type ValidationRegion = {
  id: string;
  label: string;
  labels: string[];
  source: (number | null)[];
  reference: (number | null)[];
  candidate: (number | null)[];
  baseline: AgreementMetrics;
  calibrated: AgreementMetrics;
};
type ValidationEvidence = {
  version: string;
  analysis_id: string;
  calculation_code_sha256: string;
  dependency_versions: Record<string, string>;
  study_id: string;
  study: string;
  method: string;
  model_version: string;
  split: string;
  start: string;
  end_exclusive: string;
  source_sensor: string;
  reference_sensor: string;
  daynight: string;
  grid_size_m: number;
  units: string;
  paired_bins: number;
  unpaired_bins: number;
  protocol: {
    train_years: number[];
    validation_years: number[];
    test_years: number[];
    heldout_regions: string[];
  };
  metrics: {
    baseline: AgreementMetrics;
    candidate: AgreementMetrics;
    candidate_intervals_95: { available: boolean; blocks?: number; mae?: number[] };
  };
  regions: ValidationRegion[];
  quarterly: { quarter: number; baseline: AgreementMetrics; candidate: AgreementMetrics }[];
  trend: { available: boolean; mean_slope_error: number | null; mean_baseline_slope_error: number | null };
  seasonal_profile: {
    available: boolean;
    region_years?: number;
    years?: number;
    profile_mae?: number;
    baseline_profile_mae?: number;
  };
  limitations_or_rejection_reasons: string[];
  limitations: string[];
  source_files: unknown[];
  artifacts: { file: string; sha256: string; manifest_sha256: string; verification: string }[];
};

function agreementValue(value: number | null | undefined) {
  return value == null ? 'Unknown' : value.toLocaleString(undefined, { maximumSignificantDigits: 6 });
}

function HarmonizationValidation() {
  const [study, setStudy] = useState('jordan');
  const [split, setSplit] = useState('test_years');
  const [regionKey, setRegionKey] = useState('');
  const [revision, setRevision] = useState(0);
  const chartGroup = `validation-${useId()}`;
  const charts = useRef<HTMLDivElement>(null);
  const path = `/analytics/harmonization/validation?study=${study}&split=${split}`;
  const resource = useResource(path, (signal) => request<ValidationEvidence>(path, signal), revision);
  const data = resource.data;
  const region = data?.regions.find((item) => item.id === regionKey) ?? data?.regions[0];
  const labels = useMemo(() => region?.labels ?? [], [region]);
  const beforeSeries = useMemo(
    () => [
      { name: 'VIIRS S-NPP shared-grid activity', color: theme.orange, values: region?.source ?? [] },
      { name: 'MODIS Aqua reference', color: theme.blue, dashed: true, values: region?.reference ?? [] },
    ],
    [region],
  );
  const afterSeries = useMemo(
    () => [
      { name: 'Experimental candidate', color: theme.orange, values: region?.candidate ?? [] },
      { name: 'MODIS Aqua reference', color: theme.blue, dashed: true, values: region?.reference ?? [] },
    ],
    [region],
  );
  useEffect(() => {
    const instances = Array.from(charts.current?.querySelectorAll<HTMLElement>('.scientific-chart') ?? [])
      .map((node) => echarts.getInstanceByDom(node))
      .filter((instance) => instance !== undefined);
    if (!instances.length) return;
    instances.forEach((instance) => {
      instance.group = chartGroup;
    });
    echarts.connect(chartGroup);
    return () => {
      echarts.disconnect(chartGroup);
    };
  }, [data, region, chartGroup]);
  const interval = data?.metrics.candidate_intervals_95;
  const chartMetadata = data
    ? {
        analysis_id: data.analysis_id,
        study_id: data.study_id,
        model_version: data.model_version,
        region: region?.id,
        units: data.units,
        split,
        protocol: data.protocol,
        source_files: data.source_files,
        artifacts: data.artifacts,
        limitations: data.limitations,
        calculation_code_sha256: data.calculation_code_sha256,
        dependency_versions: data.dependency_versions,
        start: data.start,
        end_exclusive: data.end_exclusive,
        daynight: data.daynight,
        grid_size_m: data.grid_size_m,
        metrics: data.metrics,
      }
    : undefined;
  return (
    <section aria-labelledby="validation-heading" className="engine-validation">
      <div className="engine-section-heading">
        <div>
          <p className="engine-kicker">Held-out years & geographic regions</p>
          <h2 id="validation-heading">Scientific validation & regional evidence</h2>
          <p>Evaluate the published candidates against fixed MODIS Aqua reference observations.</p>
        </div>
        <button
          className="button secondary"
          onClick={() => setRevision((n) => n + 1)}
          disabled={resource.loading}
        >
          <RefreshCw size={15} /> Refresh evidence
        </button>
      </div>
      <div className="engine-validation-controls">
        <label>
          Validation study
          <select
            value={study}
            onChange={(e) => {
              setStudy(e.target.value);
              setRegionKey('');
            }}
          >
            <option value="jordan">Jordan · four study blocks</option>
            <option value="levant">Levant · Jordan, Syria & Lebanon</option>
          </select>
        </label>
        <label>
          Held-out evaluation
          <select
            value={split}
            onChange={(e) => {
              setSplit(e.target.value);
              setRegionKey('');
            }}
          >
            <option value="test_years">Held-out years</option>
            <option value="test_regions">Held-out regions</option>
            <option value="test_years_and_regions">Held-out years & regions</option>
          </select>
        </label>
      </div>
      {resource.loading && <p role="status">Verifying study artifacts and replaying held-out comparisons…</p>}
      {resource.error && (
        <div role="alert" className="connection-notice">
          <p>Validation evidence unavailable. {resource.error}</p>
          <p>Retry to load the verified benchmark. Live archive controls remain available above.</p>
        </div>
      )}
      {data && (
        <>
          <p className="engine-caption">
            Published 2013–2025 benchmark · daytime {data.source_sensor} → {data.reference_sensor} ·{' '}
            {data.grid_size_m / 1000} km equal-area cells · monthly summaries.
          </p>
          <p className="engine-caption">
            Training {data.protocol.train_years.join(', ')} · selection{' '}
            {data.protocol.validation_years.join(', ')} · temporal test {data.protocol.test_years.join(', ')}{' '}
            · geographic holdout {data.protocol.heldout_regions.join(', ')}. Candidate selection uses the
            validation years. The displayed tests retain their original held-out roles.
          </p>
          <dl className="engine-facts">
            <div>
              <dt>Paired evaluation bins</dt>
              <dd>{agreementValue(data.paired_bins)}</dd>
              <p>Region-month pairs with finite activity for both sensors in this held-out scope.</p>
            </div>
            <div>
              <dt>Unpaired region-months</dt>
              <dd>{agreementValue(data.unpaired_bins)}</dd>
              <p>Calendar bins with at least one missing sensor value. Their activity remains unknown.</p>
            </div>
            <div>
              <dt>Candidate status</dt>
              <dd>Experimental</dd>
              <p>{data.method.replaceAll('_', ' ')} · further validation required for operational use.</p>
            </div>
          </dl>
          <div className="table-scroll" role="region" aria-label="Held-out agreement metrics" tabIndex={0}>
            <table>
              <caption>Agreement to MODIS Aqua · all eligible region-month pairs · {data.units}</caption>
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Before calibration</th>
                  <th>Experimental candidate</th>
                  <th>Interpretation</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">MAE</th>
                  <td>{agreementValue(data.metrics.baseline.mae)}</td>
                  <td>{agreementValue(data.metrics.candidate.mae)}</td>
                  <td>Mean absolute difference from the sensor reference.</td>
                </tr>
                <tr>
                  <th scope="row">RMSE</th>
                  <td>{agreementValue(data.metrics.baseline.rmse)}</td>
                  <td>{agreementValue(data.metrics.candidate.rmse)}</td>
                  <td>Root mean squared difference, with more weight on large discrepancies.</td>
                </tr>
                <tr>
                  <th scope="row">Signed bias</th>
                  <td>{agreementValue(data.metrics.baseline.bias)}</td>
                  <td>{agreementValue(data.metrics.candidate.bias)}</td>
                  <td>Mean estimate minus reference. Positive values indicate a higher estimate.</td>
                </tr>
              </tbody>
            </table>
          </div>
          {interval?.available ? (
            <p className="engine-caption">
              Candidate MAE 95% interval · {agreementValue(interval.mae?.[0])}–
              {agreementValue(interval.mae?.[1])}. Fixed-model year-block bootstrap using {interval.blocks}{' '}
              held-out year blocks. This interval describes sample agreement variability.
            </p>
          ) : (
            <p className="engine-caption">
              Agreement intervals require at least three held-out year blocks with paired observations.
            </p>
          )}
          {!data.paired_bins && (
            <p role="status">
              This held-out scope has no paired observations. Error metrics and candidate comparisons remain
              unevaluated.
            </p>
          )}
          <div className="engine-section-heading engine-validation-subheading">
            <div>
              <h3>Compare equivalent regional histories</h3>
              <p className="engine-caption">
                Both charts use the same region, UTC calendar months, daytime stratum and activity units.
                Candidate values are shown for paired bins used in the selected evaluation.
              </p>
            </div>
            <label>
              Comparison region
              <select
                value={region?.id ?? ''}
                disabled={!data.regions.length}
                onChange={(e) => setRegionKey(e.target.value)}
              >
                {data.regions.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div ref={charts} className="engine-chart-pair">
            <div>
              <h3>Before calibration · {region?.label}</h3>
              <ScientificChart
                title="Regional activity before calibration"
                labels={labels}
                series={beforeSeries}
                metadata={chartMetadata}
              />
            </div>
            <div>
              <h3>Experimental candidate · {region?.label}</h3>
              <ScientificChart
                title="Regional activity after candidate calibration"
                labels={labels}
                series={afterSeries}
                metadata={chartMetadata}
              />
            </div>
          </div>
          <p className="engine-caption">
            The baseline already uses the study’s 5 km shared-grid activity metric. This evidence retains its
            own versioned scientific method alongside the live 0.01° illustration. Each region-month has equal
            weight in the overall error metrics. Geographic boundaries are approximate study geometries.
          </p>
          <div className="table-scroll" role="region" aria-label="Regional validation support" tabIndex={0}>
            <table>
              <thead>
                <tr>
                  <th>Evaluation region</th>
                  <th>Paired bins</th>
                  <th>Baseline MAE</th>
                  <th>Candidate MAE</th>
                  <th>Candidate RMSE</th>
                </tr>
              </thead>
              <tbody>
                {data.regions.map((item) => (
                  <tr key={item.id}>
                    <th scope="row">{item.label}</th>
                    <td>{item.calibrated.n}</td>
                    <td>{agreementValue(item.baseline.mae)}</td>
                    <td>{agreementValue(item.calibrated.mae)}</td>
                    <td>{agreementValue(item.calibrated.rmse)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3 className="engine-validation-subheading">Seasonal patterns & historical trends</h3>
          <dl className="engine-facts">
            <div>
              <dt>Centered seasonal-profile MAE</dt>
              <dd>{agreementValue(data.seasonal_profile.profile_mae)}</dd>
              <p>
                Candidate quarterly-profile error. Baseline{' '}
                {agreementValue(data.seasonal_profile.baseline_profile_mae)}. Requires all four quarters
                within region-years and at least three years.
              </p>
            </div>
            <div>
              <dt>Seasonal support</dt>
              <dd>
                {data.seasonal_profile.available
                  ? `${data.seasonal_profile.region_years} region-years`
                  : 'Unknown'}
              </dd>
              <p>Retrospective diagnostic support, with at least one paired month in each quarter.</p>
            </div>
            <div>
              <dt>Matched-calendar slope error</dt>
              <dd>{agreementValue(data.trend.mean_slope_error)}</dd>
              <p>
                Candidate absolute slope difference from the reference. Baseline{' '}
                {agreementValue(data.trend.mean_baseline_slope_error)}. Activity units per year, requiring
                three years and six common calendar months per region.
              </p>
            </div>
          </dl>
          {data.quarterly.length > 0 && (
            <details>
              <summary>Quarterly agreement and sample support</summary>
              <div className="table-scroll" role="region" aria-label="Quarterly agreement" tabIndex={0}>
                <table>
                  <thead>
                    <tr>
                      <th>Quarter</th>
                      <th>Paired bins</th>
                      <th>Baseline MAE</th>
                      <th>Candidate MAE</th>
                      <th>Candidate RMSE</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.quarterly.map((item) => (
                      <tr key={item.quarter}>
                        <th scope="row">Q{item.quarter}</th>
                        <td>{item.candidate.n}</td>
                        <td>{agreementValue(item.baseline.mae)}</td>
                        <td>{agreementValue(item.candidate.mae)}</td>
                        <td>{agreementValue(item.candidate.rmse)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
          <h3 className="engine-validation-subheading">Validation requirements & limitations</h3>
          <p>
            Physical fire accuracy requires independent reference measurements. Observation coverage remains
            unknown for these detection-only studies, so changes in the curves require instrument-aware
            interpretation.
          </p>
          <ul className="engine-validation-limitations">
            {data.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p>
            Further acceptance work requires independently audited swath, cloud, quality and overpass
            information, consistent product versions, and additional held-out regional and seasonal support.
          </p>
          <details>
            <summary>Inspect acceptance-check reasons</summary>
            <ul>
              {data.limitations_or_rejection_reasons.map((reason) => (
                <li key={reason}>
                  <code>{reason}</code>
                </li>
              ))}
            </ul>
          </details>
          <div className="engine-validation-export">
            <button
              className="button secondary"
              onClick={() =>
                downloadArtifact(
                  JSON.stringify(data, null, 2),
                  `pirx-validation-${study}-${split}.json`,
                  'application/json',
                )
              }
            >
              Export validation evidence <ArrowRight size={15} />
            </button>
            <details>
              <summary>Source provenance, artifact verification & model version</summary>
              <pre>
                {JSON.stringify(
                  {
                    analysis_id: data.analysis_id,
                    study_id: data.study_id,
                    model_version: data.model_version,
                    calculation_code_sha256: data.calculation_code_sha256,
                    dependency_versions: data.dependency_versions,
                    artifacts: data.artifacts,
                    source_files: data.source_files,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          </div>
        </>
      )}
    </section>
  );
}
