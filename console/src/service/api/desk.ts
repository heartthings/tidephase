import { request } from '../request';
import { DESK_URLS } from '../urls/desk';

export type DeskIndex = {
  amountYi?: number | null;
  close?: number | null;
  code: string;
  high?: number | null;
  low?: number | null;
  name: string;
  open?: number | null;
  pct?: number | null;
  volumeYi?: number | null;
};

export type DeskPoolItem = {
  amountYi?: number | null;
  boardDays?: number | null;
  breakTimes?: number | null;
  close?: number | null;
  code: string;
  circMvYi?: number | null;
  firstSeal?: string;
  industry?: string;
  lastSeal?: string;
  name: string;
  pct?: number | null;
  reason?: string;
  sealYi?: number | null;
  theme?: string;
  turnover?: number | null;
};

export type DeskLiveItem = {
  content: string;
  id: string;
  pct?: string;
  plate: string;
  stocks?: string[];
  time: string;
};

export type DeskPayload = {
  asOf: string;
  auction: Array<{ amountYi?: number | null; code: string; name: string; pct?: number | null; sector?: string }>;
  breadth: {
    avgPct?: number | null;
    downN?: number | null;
    flatN?: number | null;
    limitDownZone?: number | null;
    limitUpZone?: number | null;
    medianPct?: number | null;
    upN?: number | null;
  };
  cognitions: Array<{ confidence?: number | null; id: string; status: string; title: string; type: string }>;
  coverage: Array<{ at: string; job: string; note: string; rows?: number | null; source: string; status: string }>;
  date: string;
  dtPool: DeskPoolItem[];
  freshness: Array<{ latest?: string | null; rows: number; table: string }>;
  indices: DeskIndex[];
  isTradingDay: boolean;
  leaders: {
    down: Array<{ amountYi?: number | null; code: string; name: string; pct?: number | null }>;
    up: Array<{ amountYi?: number | null; code: string; name: string; pct?: number | null }>;
  };
  live: DeskLiveItem[];
  messages: Array<{ content: string; id: string; source: string; time: string; title: string }>;
  northbound: Array<{ buyYi?: number | null; date: string; hgtYi?: number | null; netYi?: number | null; sellYi?: number | null; sgtYi?: number | null }>;
  overnight: Array<{ close?: number | null; code: string; name: string; pct?: number | null }>;
  predictions: Array<{ at: string; id: string; status: string; title: string }>;
  sectors: {
    gainers: Array<{ down?: number | null; inflowYi?: number | null; name: string; pct?: number | null; up?: number | null }>;
    inflow: Array<{ amountYi?: number | null; inflowYi?: number | null; name: string; pct?: number | null }>;
    losers: Array<{ inflowYi?: number | null; name: string; pct?: number | null }>;
  };
  sentiment: Record<string, number | null | undefined>;
  topicCount: number;
  zbPool: DeskPoolItem[];
  ztPool: DeskPoolItem[];
};

export function fetchConsoleDesk(date?: string) {
  return request<DeskPayload>({
    method: 'get',
    params: date ? { date } : undefined,
    url: DESK_URLS.DESK
  });
}
