import { request } from '../request';
import { HOME_URLS } from '../urls/home';

export interface HomeSummary {
  id: string;
  tradingPlanContent: string;
  tradingPlanNoteId: string;
  updatedTime: string;
}

export function fetchHomeSummary() {
  return request<HomeSummary>({
    method: 'get',
    url: HOME_URLS.SUMMARY
  });
}
