import { useQuery } from '@tanstack/react-query';
import { Card, Empty, Modal, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { BarChart, CandlestickChart, LineChart } from 'echarts/charts';
import {
  AxisPointerComponent,
  BrushComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TitleComponent,
  ToolboxComponent,
  TooltipComponent
} from 'echarts/components';
import * as echarts from 'echarts/core';
import { UniversalTransition } from 'echarts/features';
import { CanvasRenderer } from 'echarts/renderers';
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';

import { request } from '@/service/request';

echarts.use([
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
  ToolboxComponent,
  DataZoomComponent,
  BrushComponent,
  AxisPointerComponent,
  MarkLineComponent,
  CandlestickChart,
  LineChart,
  BarChart,
  UniversalTransition,
  CanvasRenderer
]);

export const route = {
  meta: {
    constant: true,
    i18nKey: 'route.(base)_interval-stats',
    icon: 'mdi:chart-timeline-variant',
    order: 5,
    title: 'interval-stats'
  }
};

interface DailyKlineBar {
  amount: number;
  close: number;
  date: string;
  high: number;
  low: number;
  open: number;
  volume: number;
}

interface PlateIntervalStat {
  code: string;
  intervalGrowthRateSum: number;
  intervalNetAmount: string;
  intervalNetAmountRaw: number;
  intervalStrength: number;
  intervalTurnover: string;
  intervalTurnoverRaw: number;
  name: string;
  netInflowStreakDays: number;
}

interface PlateDailyMetrics {
  date: string;
  growthRate: number | null;
  largeForce: number;
  strength: number;
  turnover: number;
}

type DetailLegendName = '主力净额(亿·累计)' | '强度(日内峰值)' | '成交额(原始)' | '涨幅(日末)';
type DetailLegendSelected = Record<DetailLegendName, boolean>;

function formatHumanNumber(v: number, suffix = ''): string {
  const abs = Math.abs(v);
  if (abs >= 1e8) return `${(v / 1e8).toFixed(2)}亿${suffix}`;
  if (abs >= 1e4) return `${(v / 1e4).toFixed(2)}万${suffix}`;
  return `${v.toFixed(2)}${suffix}`;
}

function formatAxisCompact(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1e12) return `${(v / 1e12).toFixed(2)}万亿`;
  if (abs >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(v / 1e4).toFixed(1)}万`;
  return `${Math.round(v)}`;
}

function formatAxisYi(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1000) return `${v.toFixed(0)}亿`;
  if (abs >= 10) return `${v.toFixed(1)}亿`;
  return `${v.toFixed(2)}亿`;
}

/** 日 K 日期序列上取最后 n 个交易日的起止 */
function lastNTradingWindow(dates: string[], n: number): { end: string; start: string } {
  if (!dates.length) {
    return { end: dayjs().format('YYYY-MM-DD'), start: dayjs().format('YYYY-MM-DD') };
  }
  if (dates.length <= n) {
    return { end: dates[dates.length - 1]!, start: dates[0]! };
  }
  return { end: dates[dates.length - 1]!, start: dates[dates.length - n]! };
}

type HighlightRange = { end: string; start: string } | null;

function buildShanghaiOption(list: DailyKlineBar[], highlight: HighlightRange) {
  const dates = list.map(d => d.date);
  const ohlc = list.map(d => [d.open, d.close, d.low, d.high] as [number, number, number, number]);
  const volumes = list.map(d => d.volume);
  const volColors = list.map((d, i) => {
    if (i === 0) return d.close >= d.open ? '#f5222d' : '#389e0d';
    const prev = list[i - 1]!;
    return d.close >= prev.close ? '#f5222d' : '#389e0d';
  });

  let d0: string | undefined;
  let d1: string | undefined;
  if (highlight) {
    d0 = highlight.start < highlight.end ? highlight.start : highlight.end;
    d1 = highlight.start < highlight.end ? highlight.end : highlight.start;
  }
  const hasHighlight = Boolean(highlight && d0 && d1 && dates.includes(d0) && dates.includes(d1));

  const markArea = hasHighlight
    ? {
        data: [[{ itemStyle: { borderColor: 'rgba(0,0,0,0)' }, name: '统计区间', xAxis: d0 }, { xAxis: d1 }]] as [
          object,
          object
        ][],
        itemStyle: { color: 'rgba(250, 140, 22, 0.16)' }
      }
    : undefined;

  const markAreaBottom = hasHighlight
    ? {
        data: [[{ xAxis: d0 }, { xAxis: d1 }]] as [object, object][],
        itemStyle: { color: 'rgba(250, 140, 22, 0.12)' }
      }
    : undefined;

  return {
    animation: false,
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    brush: {
      brushLink: 'all',
      brushMode: 'single',
      brushStyle: { borderColor: '#fa8c16', borderWidth: 1, color: 'rgba(250, 140, 22, 0.2)' },
      outOfBrush: { colorAlpha: 0.3 },
      seriesIndex: [0, 1],
      throttleDelay: 200,
      throttleType: 'debounce',
      xAxisIndex: [0, 1]
    },
    dataZoom: [
      { end: 100, start: 0, type: 'inside', xAxisIndex: [0, 1] },
      { bottom: 8, end: 100, height: 22, start: 0, type: 'slider', xAxisIndex: [0, 1] }
    ],
    grid: [
      { bottom: '38%', left: '6%', right: '3%', top: '16%' },
      { bottom: '12%', height: '18%', left: '6%', right: '3%', top: '70%' }
    ],
    series: [
      {
        barMinWidth: 2,
        data: ohlc,
        gridIndex: 0,
        itemStyle: {
          borderColor: '#d4380d',
          borderColor0: '#237804',
          color: '#f5222d',
          color0: '#52c41a'
        },
        markArea,
        name: '上证指数',
        type: 'candlestick',
        xAxisIndex: 0,
        yAxisIndex: 0
      },
      {
        data: volumes.map((v, i) => ({ itemStyle: { color: volColors[i] }, value: v })),
        gridIndex: 1,
        markArea: markAreaBottom,
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1
      }
    ],
    title: { left: 'center', text: '上证指数', top: 6 },
    toolbox: {
      feature: {
        brush: {
          title: { clear: '清除选区', lineX: '区间框选（横向）' },
          type: ['lineX', 'clear']
        },
        restore: {}
      },
      right: 12,
      top: 34
    },
    tooltip: {
      axisPointer: { type: 'cross' },
      borderWidth: 1,
      formatter(params: unknown) {
        const arr = Array.isArray(params) ? params : [params];
        const first = arr[0] as { axisValue?: string } | undefined;
        if (!first?.axisValue) return '';
        const idx = dates.indexOf(first.axisValue);
        const row = idx >= 0 ? list[idx] : null;
        if (!row) return first.axisValue;
        const pct = row.open !== 0 ? (((row.close - row.open) / row.open) * 100).toFixed(2) : '0.00';
        const parts = [
          `<div style="font-weight:600">${row.date}</div>`,
          `开: ${row.open.toFixed(2)}  高: ${row.high.toFixed(2)}`,
          `低: ${row.low.toFixed(2)}  收: ${row.close.toFixed(2)}`,
          `涨跌: ${(row.close - row.open).toFixed(2)} (${pct}%)`,
          `成交量: ${row.volume.toLocaleString()}  额: ${(row.amount / 1e8).toFixed(2)} 亿`
        ];
        return parts.join('<br/>');
      },
      trigger: 'axis'
    },
    xAxis: [
      {
        axisLabel: { show: false },
        data: dates,
        gridIndex: 0,
        scale: true,
        splitLine: { show: false },
        type: 'category'
      },
      {
        axisLabel: { rotate: 45 },
        data: dates,
        gridIndex: 1,
        scale: true,
        splitLine: { show: false },
        type: 'category'
      }
    ],
    yAxis: [
      { gridIndex: 0, scale: true, splitArea: { show: true }, splitNumber: 6 },
      { gridIndex: 1, scale: true, splitNumber: 2 }
    ]
  };
}

function buildPlateDetailOption(rows: PlateDailyMetrics[], selectedMap: DetailLegendSelected) {
  const dates = rows.map(r => (typeof r.date === 'string' ? r.date : (r as { date: string }).date));
  const strength = rows.map(r => r.strength ?? 0);
  const growth = rows.map(r => (r.growthRate !== null ? r.growthRate : 0));
  const mainYi = rows.map(r => (r.largeForce !== null ? r.largeForce / 10000 : 0));
  const turnover = rows.map(r => r.turnover ?? 0);

  const metricDefs: Array<{
    color: string;
    data: number[];
    isBar?: boolean;
    name: DetailLegendName;
    yAxisLabel: (value: number) => string;
  }> = [
    {
      color: '#5470c6',
      data: strength,
      name: '强度(日内峰值)',
      yAxisLabel(value) {
        return Number(value).toLocaleString();
      }
    },
    {
      color: '#91cc75',
      data: growth,
      name: '涨幅(日末)',
      yAxisLabel(value) {
        return `${Number(value).toFixed(2)}%`;
      }
    },
    {
      color: '#fac858',
      data: mainYi,
      name: '主力净额(亿·累计)',
      yAxisLabel(value) {
        return formatAxisYi(Number(value));
      }
    },
    {
      color: '#ee6666',
      data: turnover,
      isBar: true,
      name: '成交额(原始)',
      yAxisLabel(value) {
        return formatAxisCompact(Number(value));
      }
    }
  ];

  const activeDefs = metricDefs.filter(def => {
    if (def.name === '成交额(原始)') return true;
    return selectedMap[def.name] !== false;
  });
  const hiddenDefs = metricDefs.filter(def => !activeDefs.some(active => active.name === def.name));
  const panelCount = Math.max(activeDefs.length, 1);
  const chartTop = 16;
  const chartTotalHeight = 72;
  const gap = 4;
  const panelHeight = (chartTotalHeight - (panelCount - 1) * gap) / panelCount;
  const xAxisIndexList = Array.from({ length: panelCount }, (_, i) => i);

  return {
    animation: true,
    axisPointer: { link: [{ xAxisIndex: 'all' }], snap: true },
    dataZoom: [
      { end: 100, type: 'inside', xAxisIndex: xAxisIndexList },
      { bottom: 0, end: 100, height: 20, type: 'slider', xAxisIndex: xAxisIndexList }
    ],
    grid: activeDefs.map((_, idx) => ({
      backgroundColor: idx % 2 === 0 ? 'rgba(249,250,251,0.55)' : 'rgba(255,255,255,0.75)',
      borderColor: '#e5e7eb',
      borderWidth: 1,
      height: `${panelHeight}%`,
      left: '12%',
      right: '4%',
      show: true,
      top: `${chartTop + idx * (panelHeight + gap)}%`
    })),
    legend: {
      data: ['强度(日内峰值)', '涨幅(日末)', '主力净额(亿·累计)', '成交额(原始)'],
      left: 12,
      selected: selectedMap,
      top: 34
    },
    series: [
      ...activeDefs.map((def, idx) => ({
        data: def.data,
        itemStyle: { color: def.color },
        lineStyle: def.isBar ? undefined : { color: def.color, width: 2 },
        name: def.name,
        smooth: def.isBar ? undefined : true,
        symbol: def.isBar ? undefined : 'circle',
        symbolSize: def.isBar ? undefined : 6,
        type: def.isBar ? 'bar' : 'line',
        xAxisIndex: idx,
        yAxisIndex: idx
      })),
      // 为被隐藏维度保留“图例占位系列”，确保上方图例始终可见且可再次点亮
      ...hiddenDefs.map(def => ({
        data: [],
        itemStyle: { opacity: 0 },
        lineStyle: { opacity: 0 },
        name: def.name,
        showSymbol: false,
        silent: true,
        tooltip: { show: false },
        type: 'line' as const,
        xAxisIndex: 0,
        yAxisIndex: 0
      }))
    ],
    title: { left: 'center', text: '板块日维度：强度 / 涨幅 / 主力 / 成交', top: 6 },
    tooltip: {
      formatter(params: unknown) {
        const arr = Array.isArray(params) ? params : [params];
        if (!arr.length) return '';
        const first = arr[0] as { axisValue?: string } | undefined;
        const date = first?.axisValue ?? '';
        const lines = [`<div style="font-weight:600">${date}</div>`];
        (arr as Array<{ seriesName?: string; value?: number }>).forEach(item => {
          const name = item.seriesName ?? '';
          const value = Number(item.value ?? 0);
          let text = `${value}`;
          if (name.includes('涨幅')) text = `${value.toFixed(2)}%`;
          else if (name.includes('主力净额')) text = `${value.toFixed(2)} 亿`;
          else if (name.includes('成交额')) text = formatHumanNumber(value);
          else if (name.includes('强度')) text = value.toLocaleString();
          lines.push(`${name}: ${text}`);
        });
        return lines.join('<br/>');
      },
      trigger: 'axis'
    },
    xAxis: activeDefs.map((_, i) => ({
      axisLabel: { rotate: i === activeDefs.length - 1 ? 35 : 0, show: i === activeDefs.length - 1 },
      data: dates,
      gridIndex: i,
      type: 'category' as const
    })),
    yAxis: activeDefs.map((def, i) => ({
      axisLabel: {
        formatter(value: number) {
          return def.yAxisLabel(Number(value));
        }
      },
      gridIndex: i,
      scale: true,
      splitNumber: 3
    }))
  } as echarts.ComposeOption<Record<string, unknown>>;
}

// eslint-disable-next-line complexity
export default function IntervalStatsPage() {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);
  const datesRef = useRef<string[]>([]);

  const defaultEnd = dayjs();
  const defaultStart = defaultEnd.subtract(730, 'day');

  const klineWindow = useMemo(
    () => ({
      end: defaultEnd.format('YYYY-MM-DD'),
      start: defaultStart.format('YYYY-MM-DD')
    }),
    [defaultEnd, defaultStart]
  );

  const [statsRange, setStatsRange] = useState<{ end: string; start: string } | null>(null);
  const defaultRangeApplied = useRef(false);

  const { data: klineList = [], isFetching: klineLoading } = useQuery({
    queryFn: () =>
      request<DailyKlineBar[]>({
        method: 'GET',
        params: { endDate: klineWindow.end, startDate: klineWindow.start },
        url: '/market/index/shanghai/daily-k'
      }),
    queryKey: ['shanghai-daily-k', klineWindow.start, klineWindow.end]
  });

  useEffect(() => {
    if (!klineList.length || defaultRangeApplied.current) return;
    const dates = klineList.map(d => d.date);
    setStatsRange(lastNTradingWindow(dates, 5));
    defaultRangeApplied.current = true;
  }, [klineList]);

  const { data: plateStats = [], isFetching: statsLoading } = useQuery({
    enabled: Boolean(statsRange?.start && statsRange?.end),
    queryFn: () =>
      request<PlateIntervalStat[]>({
        method: 'GET',
        params: { endDate: statsRange!.end, startDate: statsRange!.start },
        url: '/trading/dashboard/plate/interval-stats'
      }),
    queryKey: ['plate-interval-stats', statsRange?.start, statsRange?.end]
  });

  const applyBrushRange = useCallback((dateFrom: string, dateTo: string) => {
    const start = dateFrom <= dateTo ? dateFrom : dateTo;
    const end = dateFrom <= dateTo ? dateTo : dateFrom;
    if (start === end) {
      // single day
    }
    setStatsRange({ end, start });
  }, []);

  const shanghaiOption = useMemo(
    () => (klineList.length ? buildShanghaiOption(klineList, statsRange) : null),
    [klineList, statsRange]
  );

  useEffect(() => {
    if (!chartRef.current) return () => {};
    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current, undefined, { renderer: 'canvas' });
    }
    const chart = chartInstance.current;
    if (!klineList.length || !shanghaiOption) {
      chart.clear();
      return () => {};
    }
    datesRef.current = klineList.map(d => d.date);
    chart.setOption(shanghaiOption, true);

    // 保持区间框选可视化：选择后将 brush 区域持续绘制在图上
    if (statsRange) {
      const dates = klineList.map(d => d.date);
      const startIdx = dates.indexOf(statsRange.start);
      const endIdx = dates.indexOf(statsRange.end);
      if (startIdx >= 0 && endIdx >= 0) {
        const lo = Math.min(startIdx, endIdx);
        const hi = Math.max(startIdx, endIdx);
        chart.dispatchAction({
          areas: [
            {
              brushType: 'lineX',
              coordRange: [lo, hi],
              xAxisIndex: 0
            },
            {
              brushType: 'lineX',
              coordRange: [lo, hi],
              xAxisIndex: 1
            }
          ],
          type: 'brush'
        });
      }
    }

    const onBrushEnd = (raw: unknown) => {
      const payload = raw as {
        areas?: { coordRange?: [number, number] | [string, string] }[];
        batch?: { areas?: { coordRange?: [number, number] | [string, string] }[] }[];
      };
      const areas = payload?.batch?.[0]?.areas ?? payload?.areas;
      if (!areas?.length) return;
      const coord = areas[0]?.coordRange;
      if (!coord || coord.length < 2) return;
      const dates = datesRef.current;
      if (!dates.length) return;
      const c0 = coord[0];
      const c1 = coord[1];
      if (typeof c0 === 'string' && typeof c1 === 'string') {
        applyBrushRange(c0, c1);
        return;
      }
      const i0 = typeof c0 === 'number' ? Math.round(c0) : dates.indexOf(String(c0));
      const i1 = typeof c1 === 'number' ? Math.round(c1) : dates.indexOf(String(c1));
      if (i0 < 0 || i1 < 0) return;
      const lo = Math.min(i0, i1);
      const hi = Math.max(i0, i1);
      const d0 = dates[lo];
      const d1 = dates[hi];
      if (d0 && d1) applyBrushRange(d0, d1);
    };
    chart.off('brushEnd');
    chart.on('brushEnd', onBrushEnd);
    return () => {
      chart.off('brushEnd', onBrushEnd);
    };
  }, [applyBrushRange, klineList, shanghaiOption, statsRange]);

  useEffect(() => {
    const ro = new ResizeObserver(() => chartInstance.current?.resize());
    if (chartRef.current) ro.observe(chartRef.current);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    return () => {
      chartInstance.current?.dispose();
      chartInstance.current = null;
    };
  }, []);

  const [sortState, setSortState] = useState<{ columnKey?: string; order?: 'ascend' | 'descend' }>({});
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailPlate, setDetailPlate] = useState<PlateIntervalStat | null>(null);
  const [detailLegendSelected, setDetailLegendSelected] = useState<DetailLegendSelected>({
    '主力净额(亿·累计)': true,
    '强度(日内峰值)': true,
    '成交额(原始)': true,
    '涨幅(日末)': true
  });
  const detailChartRef = useRef<HTMLDivElement>(null);
  const detailChart = useRef<echarts.ECharts | null>(null);

  const { data: dailyMetrics = [], isFetching: dailyLoading } = useQuery({
    enabled: detailOpen && Boolean(detailPlate?.code),
    queryFn: () =>
      request<PlateDailyMetrics[]>({
        method: 'GET',
        params: { code: detailPlate!.code },
        url: '/trading/dashboard/plate/daily-metrics'
      }),
    queryKey: ['plate-daily-metrics', detailPlate?.code]
  });

  useLayoutEffect(() => {
    if (!detailOpen) {
      detailChart.current?.dispose();
      detailChart.current = null;
      return () => {};
    }
    // Modal 内容经 Portal 挂载，偶发在 effect 首帧 ref 仍不可用；缓一帧再试避免「有数据但不画图」
    let cancelled = false;
    const paintChart = () => {
      if (cancelled || !detailChartRef.current) return;
      if (!detailChart.current) {
        detailChart.current = echarts.init(detailChartRef.current, undefined, { renderer: 'canvas' });
      }
      if (dailyMetrics.length) {
        detailChart.current.setOption(buildPlateDetailOption(dailyMetrics, detailLegendSelected), true);
        detailChart.current.off('legendselectchanged');
        detailChart.current.on('legendselectchanged', rawEvt => {
          const evt = rawEvt as { selected?: Record<string, boolean> };
          const selected = evt.selected ?? {};
          // 成交额必须常显：若被点击取消，立即恢复选中状态
          if (selected['成交额(原始)'] === false) {
            detailChart.current?.dispatchAction({ name: '成交额(原始)', type: 'legendSelect' });
            selected['成交额(原始)'] = true;
          }
          setDetailLegendSelected(prev => ({
            ...prev,
            '主力净额(亿·累计)': selected['主力净额(亿·累计)'] ?? prev['主力净额(亿·累计)'],
            '强度(日内峰值)': selected['强度(日内峰值)'] ?? prev['强度(日内峰值)'],
            '成交额(原始)': true,
            '涨幅(日末)': selected['涨幅(日末)'] ?? prev['涨幅(日末)']
          }));
        });
        detailChart.current.resize();
      } else {
        detailChart.current.clear();
      }
    };
    paintChart();
    if (!detailChartRef.current && dailyMetrics.length) {
      let frames = 0;
      let rafId = 0;
      const MAX_FRAMES = 20;
      const tryLater = () => {
        if (cancelled) return;
        if (detailChartRef.current) {
          paintChart();
          return;
        }
        frames += 1;
        if (frames < MAX_FRAMES) {
          rafId = requestAnimationFrame(tryLater);
        }
      };
      rafId = requestAnimationFrame(tryLater);
      return () => {
        cancelled = true;
        cancelAnimationFrame(rafId);
      };
    }
    return () => {
      cancelled = true;
    };
  }, [detailOpen, dailyMetrics, detailLegendSelected]);

  useEffect(() => {
    if (!detailOpen || !detailChartRef.current) return () => {};
    const ro = new ResizeObserver(() => detailChart.current?.resize());
    ro.observe(detailChartRef.current);
    return () => ro.disconnect();
  }, [detailOpen]);

  const sortedPlateStats = useMemo(() => {
    const data = [...plateStats];
    const { columnKey, order } = sortState;
    if (!columnKey || !order) return data;
    const dir = order === 'ascend' ? 1 : -1;
    const num = (a: number | undefined, b: number | undefined) => dir * ((a ?? 0) - (b ?? 0));
    const str = (a: string, b: string) => dir * a.localeCompare(b, 'zh-CN');
    data.sort((x, y) => {
      switch (columnKey) {
        case 'code':
          return str(x.code, y.code);
        case 'intervalGrowthRateSum':
          return num(x.intervalGrowthRateSum, y.intervalGrowthRateSum);
        case 'intervalNetAmount':
          return num(x.intervalNetAmountRaw, y.intervalNetAmountRaw);
        case 'intervalStrength':
          return num(x.intervalStrength, y.intervalStrength);
        case 'intervalTurnover':
          return num(x.intervalTurnoverRaw, y.intervalTurnoverRaw);
        case 'name':
          return str(x.name, y.name);
        case 'netInflowStreakDays':
          return num(x.netInflowStreakDays, y.netInflowStreakDays);
        default:
          return 0;
      }
    });
    return data;
  }, [plateStats, sortState]);

  const columns: ColumnsType<PlateIntervalStat> = useMemo(
    () => [
      {
        dataIndex: 'code',
        key: 'code',
        title: '板块代码',
        width: 120
      },
      {
        dataIndex: 'name',
        ellipsis: true,
        key: 'name',
        title: '板块名称'
      },
      {
        dataIndex: 'intervalStrength',
        key: 'intervalStrength',
        render: v => (v ?? 0).toLocaleString(),
        sorter: true,
        sortOrder: sortState.columnKey === 'intervalStrength' ? sortState.order : undefined,
        title: '区间强度',
        width: 120
      },
      {
        dataIndex: 'intervalGrowthRateSum',
        key: 'intervalGrowthRateSum',
        render: v => (v ?? 0).toFixed(4),
        sorter: true,
        sortOrder: sortState.columnKey === 'intervalGrowthRateSum' ? sortState.order : undefined,
        title: '区间涨幅',
        width: 140
      },
      {
        dataIndex: 'intervalNetAmount',
        key: 'intervalNetAmount',
        render: v => <Typography.Text style={{ whiteSpace: 'nowrap' }}>{v ?? '-'}</Typography.Text>,
        sorter: true,
        sortOrder: sortState.columnKey === 'intervalNetAmount' ? sortState.order : undefined,
        title: '区间净额',
        width: 140
      },
      {
        dataIndex: 'intervalTurnover',
        key: 'intervalTurnover',
        render: v => <Typography.Text style={{ whiteSpace: 'nowrap' }}>{v ?? '-'}</Typography.Text>,
        sorter: true,
        sortOrder: sortState.columnKey === 'intervalTurnover' ? sortState.order : undefined,
        title: '区间成交',
        width: 150
      },
      {
        dataIndex: 'netInflowStreakDays',
        key: 'netInflowStreakDays',
        sorter: true,
        sortOrder: sortState.columnKey === 'netInflowStreakDays' ? sortState.order : undefined,
        title: '连续净流入天数',
        width: 150
      }
    ],
    [sortState]
  );

  return (
    <div className="h-full flex flex-col gap-16px pb-16px">
      <div className="fixed right-24px top-132px z-[1000] border border-orange-200 rounded-8px bg-orange-50 px-12px py-8px shadow-md">
        <Typography.Text type="secondary">
          当前统计区间：
          <Typography.Text strong>{statsRange?.start ?? '—'}</Typography.Text> ~{' '}
          <Typography.Text strong>{statsRange?.end ?? '—'}</Typography.Text>
        </Typography.Text>
      </div>
      <Card
        size="small"
        title="区间统计"
      >
        <Typography.Paragraph
          className="mb-12px text-13px text-gray-600"
          type="secondary"
        >
          上证日K 与统计区间。默认使用<strong>最近 5 个交易日</strong> 作为统计区间，并在图中以
          <Typography.Text type="warning"> 橙色带状区域 </Typography.Text>
          标出。可用工具栏「区间框选」或下方滑块调整日期；下方板块表汇总当前区间。点击行可查看该板块历史日维度走势。
        </Typography.Paragraph>
        <div
          className="h-420px w-full"
          ref={chartRef}
        />
        {klineLoading && <Typography.Text type="secondary">K 线加载中…</Typography.Text>}
        {!klineLoading && !klineList.length && <Empty description="暂无 K 线数据" />}
      </Card>

      <Card
        size="small"
        title="板块区间汇总"
      >
        {!sortedPlateStats.length && !statsLoading ? (
          <Empty description="暂无板块异动数据或所选区间无数据" />
        ) : (
          <Table<PlateIntervalStat>
            columns={columns}
            dataSource={sortedPlateStats}
            loading={statsLoading}
            pagination={{ pageSize: 50, showSizeChanger: true }}
            rowKey="code"
            scroll={{ x: 1100 }}
            onChange={(_p, _f, sorter) => {
              const s = Array.isArray(sorter) ? sorter[0] : sorter;
              let field: unknown;
              if (s && 'field' in s) {
                field = s.field;
              } else if (s && 'columnKey' in s) {
                field = s.columnKey;
              }
              if (!s || field === undefined || !s.order) {
                setSortState({});
                return;
              }
              setSortState({ columnKey: String(field), order: s.order });
            }}
            onRow={record => ({
              onClick: () => {
                setDetailPlate(record);
                setDetailLegendSelected({
                  '主力净额(亿·累计)': true,
                  '强度(日内峰值)': true,
                  '成交额(原始)': true,
                  '涨幅(日末)': true
                });
                setDetailOpen(true);
              },
              style: { cursor: 'pointer' }
            })}
          />
        )}
      </Card>

      <Modal
        destroyOnClose
        footer={null}
        open={detailOpen}
        title={detailPlate ? `板块日走势 — ${detailPlate.name} (${detailPlate.code})` : '板块日走势'}
        width={1000}
        afterOpenChange={open => {
          if (open) {
            requestAnimationFrame(() => {
              detailChart.current?.resize();
            });
          }
        }}
        onCancel={() => {
          setDetailOpen(false);
          setDetailPlate(null);
        }}
      >
        <Typography.Paragraph
          className="text-13px text-gray-600"
          type="secondary"
        >
          三列折线同轴对比：<strong>强度</strong>（日内峰值）、<strong>涨幅</strong>（当日最后一条记录）、
          <strong>主力净额</strong>（万元累计换算为 亿）；下方柱状为<strong>成交额</strong>
          日累计。时间范围为库中该板块全部数据。
        </Typography.Paragraph>
        {dailyLoading && <Typography.Text type="secondary">加载中…</Typography.Text>}
        {!dailyLoading && !dailyMetrics.length && (
          <Empty
            className="py-24px"
            description="暂无该板块日数据"
          />
        )}
        <div
          className="h-500px w-full"
          ref={detailChartRef}
        />
      </Modal>
    </div>
  );
}
