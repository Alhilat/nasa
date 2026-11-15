import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { ChartNoAxesCombined } from 'lucide-react';
import type { Summary } from '../types';
import { visualTheme as theme } from '../visualTheme';

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

export default function ActivityChart({ summary }: { summary: Summary | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || !summary?.daily.length) return;
    const chart = echarts.init(ref.current);
    const days = [...new Set(summary.daily.map(d => d.day))].sort();
    // Native sensor series remain separate. Missing sensor/day bins remain unknown.
    const sensors = [...new Set(summary.daily.map(d => d.sensor_code))];
    chart.setOption({
      animation: false,
      backgroundColor: theme.surface,
      textStyle: { fontFamily: theme.fontUI },
      tooltip: { trigger: 'axis', renderMode: 'richText', backgroundColor: theme.white, borderWidth: 0, textStyle: { color: theme.text, fontFamily: theme.fontData } },
      grid: { top: 18, right: 18, bottom: 30, left: 45 },
      xAxis: { type: 'category', data: days, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: theme.muted, fontFamily: theme.fontData, fontSize: 11 } },
      yAxis: { type: 'value', minInterval: 1, axisLabel: { color: theme.muted, fontFamily: theme.fontData, fontSize: 11 }, splitLine: { lineStyle: { color: theme.rule, opacity: 0.3 } } },
      series: sensors.map((sensor, index) => ({
        name: sensor, type: 'line', connectNulls: false, symbolSize: 5,
        lineStyle: { width: 2, type: index % 2 ? 'dashed' : 'solid' },
        itemStyle: { color: sensor.startsWith('MODIS') ? theme.orange : theme.viirs },
        data: days.map(day => summary.daily.find(d => d.day === day && d.sensor_code === sensor)?.count ?? null),
      })),
    });
    const resize = new ResizeObserver(() => chart.resize());
    resize.observe(ref.current);
    return () => { resize.disconnect(); chart.dispose(); };
  }, [summary]);

  return summary?.daily.length
    ? <div ref={ref} className="activity-chart" aria-label="Daily observation counts by native sensor" role="img" />
    : <div className="chart-empty"><ChartNoAxesCombined size={25} strokeWidth={1.4} /><span>Your archive’s activity will appear here</span><small>Daily counts by sensor · no data loaded</small></div>;
}
