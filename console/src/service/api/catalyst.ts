import { request } from '../request';
import { CATALYST_URLS } from '../urls/catalyst';

export function fetchCatalystDashboard(date: string) {
  return request<Api.Catalyst.Dashboard>({
    method: 'get',
    params: { date },
    url: CATALYST_URLS.DASHBOARD
  });
}

export function fetchCatalystImpacts(date: string) {
  return request<Api.Catalyst.Impact[]>({
    method: 'get',
    params: { date, limit: 200 },
    url: CATALYST_URLS.IMPACTS
  });
}

export function fetchCatalystSystemStates(date: string) {
  return request<Api.Catalyst.SystemState[]>({
    method: 'get',
    params: { date, limit: 10 },
    url: CATALYST_URLS.SYSTEM_STATES
  });
}

export function fetchCatalystActiveMessages() {
  return request<Api.Catalyst.ActiveMessage[]>({
    method: 'get',
    url: CATALYST_URLS.ACTIVE_MESSAGES
  });
}

export function fetchCatalystAccuracy() {
  return request<Api.Catalyst.Accuracy>({
    method: 'get',
    url: CATALYST_URLS.ACCURACY
  });
}
