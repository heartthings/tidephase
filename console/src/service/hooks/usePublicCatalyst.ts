import { useQuery } from '@tanstack/react-query';

import {
  fetchPublicCatalystActiveMessages,
  fetchPublicCatalystDashboard,
  fetchPublicCatalystImpacts,
  fetchPublicCatalystSystemStates
} from '../api/publicCatalyst';

type QueryOptions = { enabled?: boolean };

export function usePublicCatalystDashboard(date: string, options?: QueryOptions) {
  return useQuery({
    enabled: options?.enabled !== false,
    queryFn: () => fetchPublicCatalystDashboard(date),
    queryKey: ['public-catalyst', 'dashboard', date],
    refetchInterval: 1000 * 60 * 5,
    staleTime: 1000 * 60
  });
}

export function usePublicCatalystImpacts(date: string, options?: QueryOptions) {
  return useQuery({
    enabled: options?.enabled !== false,
    queryFn: () => fetchPublicCatalystImpacts(date),
    queryKey: ['public-catalyst', 'impacts', date],
    staleTime: 1000 * 60
  });
}

export function usePublicCatalystSystemStates(date: string, options?: QueryOptions) {
  return useQuery({
    enabled: options?.enabled !== false,
    queryFn: () => fetchPublicCatalystSystemStates(date),
    queryKey: ['public-catalyst', 'system-states', date],
    staleTime: 1000 * 60
  });
}

export function usePublicCatalystActiveMessages(options?: QueryOptions) {
  return useQuery({
    enabled: options?.enabled !== false,
    queryFn: fetchPublicCatalystActiveMessages,
    queryKey: ['public-catalyst', 'active-messages'],
    refetchInterval: 1000 * 60 * 5,
    staleTime: 1000 * 60
  });
}
