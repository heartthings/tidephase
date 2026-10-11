import { publicCatalystRequest } from '../request/publicCatalyst';
import { PUBLIC_CATALYST_URLS } from '../urls/publicCatalyst';

export function fetchPublicCatalystDashboard(date: string) {
  return publicCatalystRequest<Api.Catalyst.Dashboard>({
    method: 'get',
    params: { date },
    url: PUBLIC_CATALYST_URLS.DASHBOARD
  });
}

export function fetchPublicCatalystImpacts(date: string) {
  return publicCatalystRequest<Api.Catalyst.Impact[]>({
    method: 'get',
    params: { date, limit: 200 },
    url: PUBLIC_CATALYST_URLS.IMPACTS
  });
}

export function fetchPublicCatalystSystemStates(date: string) {
  return publicCatalystRequest<Api.Catalyst.SystemState[]>({
    method: 'get',
    params: { date, limit: 10 },
    url: PUBLIC_CATALYST_URLS.SYSTEM_STATES
  });
}

export function fetchPublicCatalystActiveMessages() {
  return publicCatalystRequest<Api.Catalyst.ActiveMessage[]>({
    method: 'get',
    url: PUBLIC_CATALYST_URLS.ACTIVE_MESSAGES
  });
}
