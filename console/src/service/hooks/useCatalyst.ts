import { useQuery } from '@tanstack/react-query';

import {
  fetchCatalystActiveMessages,
  fetchCatalystDashboard,
  fetchCatalystImpacts,
  fetchCatalystSystemStates
} from '../api/catalyst';

type QueryOptions = { enabled?: boolean };

export function useCatalystDashboard(date: string, options?: QueryOptions) {
  return useQuery({
    enabled: options?.enabled !== false,
    queryFn: () => fetchCatalystDashboard(date),
    queryKey: ['catalyst', 'dashboard', date],
    refetchInterval: 1000 * 60 * 5,
    staleTime: 1000 * 60
  });
}

export function useCatalystImpacts(date: string, options?: QueryOptions) {
  return useQuery({
    enabled: options?.enabled !== false,
    queryFn: () => fetchCatalystImpacts(date),
    queryKey: ['catalyst', 'impacts', date],
    staleTime: 1000 * 60
  });
}

export function useCatalystSystemStates(date: string, options?: QueryOptions) {
  return useQuery({
    enabled: options?.enabled !== false,
    queryFn: () => fetchCatalystSystemStates(date),
    queryKey: ['catalyst', 'system-states', date],
    staleTime: 1000 * 60
  });
}

export function useCatalystActiveMessages(options?: QueryOptions) {
  return useQuery({
    enabled: options?.enabled !== false,
    queryFn: fetchCatalystActiveMessages,
    queryKey: ['catalyst', 'active-messages'],
    refetchInterval: 1000 * 60 * 5,
    staleTime: 1000 * 60
  });
}
