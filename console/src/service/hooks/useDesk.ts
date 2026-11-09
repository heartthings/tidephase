import { useQuery } from '@tanstack/react-query';

import { fetchConsoleDesk } from '../api/desk';

export function useConsoleDesk(date?: string) {
  return useQuery({
    queryFn: () => fetchConsoleDesk(date),
    queryKey: ['console', 'desk', date || 'latest'],
    refetchInterval: 120_000,
    staleTime: 60_000
  });
}
