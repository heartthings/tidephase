import { request } from '../request';
import { MARKET_URLS } from '../urls';

export function fetchMarketDynamics(date: string) {
  return request<
    Array<{
      comment: string;
      date: string;
      id: string;
      stock: string;
      time: string;
    }>
  >({
    method: 'get',
    params: { date },
    url: MARKET_URLS.DYNAMIC_NEWS
  });
}

export function fetchMarketRadars(date: string) {
  return request<
    Array<{
      content: string;
      date: string;
      id: string;
      lbStatus: string;
      status: string;
      stockName: string;
      time: string;
    }>
  >({
    method: 'get',
    params: { date },
    url: MARKET_URLS.MARKET_RADARS
  });
}
