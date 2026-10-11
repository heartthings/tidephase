import { useQuery } from '@tanstack/react-query';

import { fetchMarketDynamics, fetchMarketRadars } from '../api/market';

export type MarketDynamicItem = {
  comment: string;
  date: string;
  id: string;
  stock: string;
  time: string;
};

export type MarketRadarItem = {
  content: string;
  date: string;
  id: string;
  lbStatus: string;
  status: string;
  stockName: string;
  time: string;
};

export function useMarketDynamics(date: string) {
  return useQuery<MarketDynamicItem[]>({
    queryFn: () => fetchMarketDynamics(date),
    queryKey: ['market', 'dynamic', date],
    staleTime: 1000 * 60
  });
}

export function useMarketRadars(date: string) {
  return useQuery<MarketRadarItem[]>({
    queryFn: () => fetchMarketRadars(date),
    queryKey: ['market', 'radar', date],
    staleTime: 1000 * 60
  });
}
