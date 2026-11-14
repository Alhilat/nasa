import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { BarChart, LineChart } from 'echarts/charts';
import { AriaComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { SVGRenderer } from 'echarts/renderers';

echarts.use([BarChart, LineChart, AriaComponent, GridComponent, LegendComponent, TooltipComponent, SVGRenderer]);
type Series = { name: string; values: (number | null)[]; color: string; dashed?: boolean };
export default function ScientificChart({ labels, series, title, kind = 'line' }: {
  labels: string[]; series: Series[]; title: string; kind?: 'line' | 'bar'; metadata?: unknown;
}) {
  const target = useRef<HTMLDivElement>(null), instance = useRef<echarts.ECharts | null>(null);
  const hasData = series.some(s => s.values.some(value => value !== null));
  useEffect(() => {
    if (!target.current || !hasData) return;
    const chart = echarts.init(target.current, undefined, { renderer: 'svg' }); instance.current = chart;
    chart.setOption({ animation: false, backgroundColor: '#101b2c', color: series.map(s => s.color),
      aria: { enabled: true },
      tooltip: { trigger: 'axis', renderMode: 'richText', backgroundColor: '#152338', borderColor: '#35465b', textStyle: { color: '#e4eaf2' } },
      legend: { bottom: 0, type: 'scroll', textStyle: { color: '#b7c3d4', fontSize: 11 } },
      grid: { top: 25, right: 18, bottom: 65, left: 55 },
      xAxis: { type: 'category', data: labels, axisLabel: { color: '#a0b0c6', fontSize: 10, hideOverlap: true }, axisLine: { lineStyle: { color: '#304158' } }, axisTick: { show: false } },
      yAxis: { type: 'value', min: 0, minInterval: 1, axisLabel: { color: '#a0b0c6', fontSize: 10 }, splitLine: { lineStyle: { color: '#243147', type: 'dashed' } } },
      series: series.map(s => ({ name: s.name, type: kind, data: s.values, connectNulls: false,
        symbol: 'circle', symbolSize: 4, showSymbol: labels.length < 30, barMaxWidth: 35,
        lineStyle: { width: 2, type: s.dashed ? 'dashed' : 'solid' }, itemStyle: { color: s.color },
      })),
    });
    const resize = new ResizeObserver(() => chart.resize()); resize.observe(target.current);
    return () => { resize.disconnect(); chart.dispose(); instance.current = null; };
  }, [labels, series, hasData, kind]);
  return <div className="scientific-chart-wrap">
    {hasData ? <><div ref={target} className="scientific-chart" role="img" aria-label={title} />
      <details className="chart-data"><summary>View accessible data table</summary><div className="table-scroll"><table><caption className="sr-only">{title}</caption><thead><tr><th>Period / sensor</th>{series.map(s => <th key={s.name}>{s.name}</th>)}</tr></thead><tbody>{labels.map((label, i) => <tr key={label}><th scope="row">{label}</th>{series.map(s => <td key={s.name}>{s.values[i] ?? 'Unknown'}</td>)}</tr>)}</tbody></table></div></details></>
      : <div className="chart-empty"><span>No comparable chart values</span><small>Missing observations remain unknown; no values are estimated.</small></div>}
  </div>;
}
