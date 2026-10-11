import { useQuery } from '@tanstack/react-query';
import { Empty, Select, Spin } from 'antd';
import dayjs from 'dayjs';
import { useEffect, useMemo, useState } from 'react';

import { ForceBubbleChart } from '@/features/capital-flow/ForceBubbleChart';
import '@/features/capital-flow/capital-flow.css';
import {
  type PlateForceItem,
  type ShanghaiIndexSnapshot,
  pickTopByAbs,
  sessionTitle
} from '@/features/capital-flow/types';
import { request } from '@/service/request';

export const route = {
  meta: {
    constant: true,
    i18nKey: 'route.(base)_capital-flow',
    icon: 'mdi:chart-bubble',
    order: 4,
    title: 'capital-flow'
  }
};

interface PlateApiItem {
  code: string;
  latestCje?: number | null;
  latestGrowthRate?: number | null;
  latestLargeForce?: number | string | null;
  latestStrong?: number | null;
  name: string;
}

interface DailyKlineBar {
  close: number;
  date: string;
}

const LIMIT_OPTIONS = [
  { label: '每侧 Top 20', value: 20 },
  { label: '每侧 Top 30', value: 30 },
  { label: '每侧 Top 40', value: 40 }
];

function toNumber(v: number | string | null | undefined): number {
  if (v === null || v === undefined) return 0;
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
}

export default function CapitalFlowPage() {
  const [limitPerSide, setLimitPerSide] = useState(30);
  const [nowTick, setNowTick] = useState(() => new Date());
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const apply = () => setReducedMotion(mq.matches);
    apply();
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => setNowTick(new Date()), 30_000);
    return () => window.clearInterval(id);
  }, []);

  const {
    data: plates = [],
    dataUpdatedAt,
    isFetching
  } = useQuery({
    queryFn: async () => {
      const list = await request<PlateApiItem[]>({
        method: 'GET',
        url: '/trading/dashboard/plates'
      });
      return (list ?? [])
        .map(
          (p): PlateForceItem => ({
            code: p.code,
            growthRate: p.latestGrowthRate,
            latestCje: p.latestCje,
            latestLargeForce: toNumber(p.latestLargeForce),
            latestStrong: p.latestStrong,
            name: p.name
          })
        )
        .filter(p => p.latestLargeForce !== 0);
    },
    queryKey: ['capital-flow-plates'],
    refetchInterval: 60_000
  });

  const { data: indexSnap } = useQuery({
    queryFn: async (): Promise<ShanghaiIndexSnapshot> => {
      const end = dayjs().format('YYYY-MM-DD');
      const start = dayjs().subtract(14, 'day').format('YYYY-MM-DD');
      const bars = await request<DailyKlineBar[]>({
        method: 'GET',
        params: { endDate: end, startDate: start },
        url: '/market/index/shanghai/daily-k'
      });
      if (!bars?.length) {
        return { changePct: null, close: null, date: null };
      }
      const last = bars[bars.length - 1];
      const prev = bars.length > 1 ? bars[bars.length - 2] : null;
      const changePct = prev && prev.close ? ((last.close - prev.close) / prev.close) * 100 : null;
      return { changePct, close: last.close, date: last.date };
    },
    queryKey: ['capital-flow-shanghai-index'],
    refetchInterval: 60_000
  });

  const visible = useMemo(() => pickTopByAbs(plates, limitPerSide), [plates, limitPerSide]);

  const updatedText = dataUpdatedAt ? dayjs(dataUpdatedAt).format('HH:mm:ss') : '--:--:--';

  let changeCls = '';
  if (indexSnap?.changePct !== null && indexSnap?.changePct !== undefined) {
    changeCls = indexSnap.changePct >= 0 ? 'up' : 'down';
  }
  let changeText = '--';
  if (indexSnap?.changePct !== null && indexSnap?.changePct !== undefined) {
    changeText = `${indexSnap.changePct >= 0 ? '▲' : '▼'}${Math.abs(indexSnap.changePct).toFixed(2)}%`;
  }

  const indexCloseText =
    indexSnap?.close !== null && indexSnap?.close !== undefined ? indexSnap.close.toFixed(2) : '--';

  return (
    <div className="cf-page">
      <header className="cf-header">
        <div className="cf-title-block">
          <span className="cf-date">{dayjs(nowTick).format('MM月DD日')}</span>
          <h1 className="cf-title">{sessionTitle(nowTick)}</h1>
        </div>
        <div className="cf-legend">
          <span className="cf-legend-item">
            <i className="cf-dot cf-dot--in" />
            主力净流入
          </span>
          <span className="cf-legend-item">
            <i className="cf-dot cf-dot--out" />
            主力净流出
          </span>
        </div>
        <div className="cf-index">
          上证指数
          <strong>{indexCloseText}</strong>
          <span className={changeCls}> {changeText}</span>
        </div>
      </header>

      <div className="cf-toolbar">
        <span className="cf-meta">
          展示 {visible.length} / {plates.length} 个板块 · 每分钟刷新 · 上次更新 {updatedText}
        </span>
        <Select
          options={LIMIT_OPTIONS}
          style={{ width: 140 }}
          value={limitPerSide}
          onChange={setLimitPerSide}
        />
      </div>

      <Spin spinning={isFetching && plates.length === 0}>
        {visible.length === 0 ? (
          <div className="cf-empty">
            <Empty description="暂无板块主力净额数据，请确认盘中爬虫已开启并完成入库" />
          </div>
        ) : (
          <ForceBubbleChart
            items={visible}
            reducedMotion={reducedMotion}
          />
        )}
      </Spin>
    </div>
  );
}
