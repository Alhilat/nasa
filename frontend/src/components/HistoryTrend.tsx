import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent, ToolboxComponent } from 'echarts/components';
import { SVGRenderer } from 'echarts/renderers';
import type { HistoryResult } from '../history';

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, ToolboxComponent, SVGRenderer]);

export default function HistoryTrend({ result, sensor }: { result: HistoryResult; sensor: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const rows = result.monthly.filter(r => r.sensor_code === sensor);
    const chart = echarts.init(ref.current, undefined, { renderer: 'svg' });
    chart.setOption({
      animation: false, legend: { top: 0, textStyle: { fontSize: 10 } },
      tooltip: { trigger: 'axis', renderMode: 'richText' },
      toolbox: { feature: { saveAsImage: { type: 'svg', name: `firescope-${sensor}-${result.analysis_id.slice(0, 12)}` } } },
      grid: { top: 55, right: 25, bottom: 45, left: 55 },
      xAxis: { type: 'category', data: rows.map(r => r.month) },
      yAxis: { type: 'value', min: 0, minInterval: 1, name: 'Detections' },
      series: [
        { name: 'Archived count (may be incomplete)', data: rows.map(r => r.count), color: '#d7653e' },
        { name: 'Prior complete-year median', data: rows.map(r => r.historical_median), color: '#497d87', lineStyle: { type: 'dashed' } },
        { name: 'Upper percentile threshold', data: rows.map(r => r.upper_threshold), color: '#a87d25', lineStyle: { type: 'dotted' } },
      ].map(series => ({ type: 'line', connectNulls: false, symbolSize: 4, ...series })),
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [result, sensor]);
  return <div ref={ref} className="history-trend" role="img" aria-label={`${sensor} monthly archived detections, prior-year medians and upper percentile thresholds. Exact values and completeness are in the monthly table below.`} />;
}
