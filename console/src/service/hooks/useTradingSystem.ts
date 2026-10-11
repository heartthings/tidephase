import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { mapApiNodeToUi } from '@/pages/(base)/trading-system/utils';

import {
  createTradingSystemNode,
  deleteTradingSystemNode,
  fetchTradingSystemNode,
  fetchTradingSystemTree,
  moveTradingSystemNode,
  updateTradingSystemNodeById
} from '../api/trading-system';
import { QUERY_KEYS } from '../keys';

export function useTradingSystemTreeQuery() {
  return useQuery({
    queryFn: async () => {
      const res = await fetchTradingSystemTree();
      return {
        maxLevel: res.maxLevel,
        nodes: res.nodes.map(mapApiNodeToUi)
      };
    },
    queryKey: QUERY_KEYS.TRADING_SYSTEM.TREE
  });
}

export function useTradingSystemNodeQuery(id: string | null, enabled: boolean) {
  return useQuery({
    enabled: enabled && Boolean(id),
    queryFn: async () => {
      const node = await fetchTradingSystemNode(id!);
      return mapApiNodeToUi(node);
    },
    queryKey: QUERY_KEYS.TRADING_SYSTEM.NODE(id ?? ''),
    staleTime: 0
  });
}

export function useTradingSystemMutations() {
  const queryClient = useQueryClient();

  const invalidateTree = () => {
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.TRADING_SYSTEM.TREE });
  };

  const createMutation = useMutation({
    mutationFn: createTradingSystemNode,
    onSuccess: () => {
      invalidateTree();
    }
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, ...params }: Api.TradingSystem.UpdateNodeByIdParams & { id: string }) =>
      updateTradingSystemNodeById(id, params),
    onSuccess: () => {
      invalidateTree();
    }
  });

  const moveMutation = useMutation({
    mutationFn: ({ id, ...params }: Api.TradingSystem.MoveNodeParams & { id: string }) =>
      moveTradingSystemNode(id, params),
    onSuccess: () => {
      invalidateTree();
    }
  });

  const deleteMutation = useMutation({
    mutationFn: deleteTradingSystemNode,
    onSuccess: () => {
      invalidateTree();
    }
  });

  return {
    create: createMutation,
    delete: deleteMutation,
    move: moveMutation,
    update: updateMutation
  };
}
