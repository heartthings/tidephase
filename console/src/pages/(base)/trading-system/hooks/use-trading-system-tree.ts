import type { TreeProps } from 'antd/es/tree';
import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  useTradingSystemMutations,
  useTradingSystemNodeQuery,
  useTradingSystemTreeQuery
} from '@/service/hooks/useTradingSystem';

import { MAX_NODE_DEPTH } from '../constants';
import { formatColorForApi } from '../node-color';
import {
  ROOT_PARENT_ID,
  getSubtreeDepth,
  isDescendantOf,
  resolveDropTargetLevel,
  resolveMoveAfterDrop
} from '../tree-drag';
import type { NodeFormValues, NodeOperateType } from '../types';
import { canAddChildToNode, collectAllNodeIds, findNode, mapApiNodeToUi, toAntTreeData } from '../utils';

interface ModalState {
  open: boolean;
  operateType: NodeOperateType;
  parentId: string | null;
  targetId: string | null;
}

function normalizeDescription(description?: string): string | undefined {
  const value = description?.trim();
  return value || undefined;
}

const initialModalState: ModalState = {
  open: false,
  operateType: 'add',
  parentId: null,
  targetId: null
};

export function useTradingSystemTree() {
  const { t } = useTranslation();
  const { data, isFetching: treeLoading, refetch } = useTradingSystemTreeQuery();
  const { create, delete: remove, move, update } = useTradingSystemMutations();

  const tree = data?.nodes ?? [];
  const maxLevel = data?.maxLevel ?? MAX_NODE_DEPTH;

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expandedKeys, setExpandedKeys] = useState<string[]>([]);
  const [modal, setModal] = useState<ModalState>(initialModalState);

  const isEditModal = modal.open && modal.operateType === 'edit' && Boolean(modal.targetId);
  const { data: editNode, isFetching: editLoading } = useTradingSystemNodeQuery(modal.targetId, isEditModal);

  /** 树数据刷新后仅剔除已删除节点的展开 key，不自动展开 */
  useEffect(() => {
    const validIds = new Set(collectAllNodeIds(tree));
    setExpandedKeys(prev => {
      const next = prev.filter(key => validIds.has(key));
      return next.length === prev.length ? prev : next;
    });
  }, [tree]);

  const antTreeData = useMemo(() => toAntTreeData(tree), [tree]);

  const selectedNode = useMemo(() => (selectedId ? findNode(tree, selectedId) : null), [selectedId, tree]);

  const canAddChild = useCallback(
    (parentId: string | null) => {
      if (!parentId) return true;
      const parent = findNode(tree, parentId);
      if (!parent) return false;
      return canAddChildToNode(parent, maxLevel);
    },
    [maxLevel, tree]
  );

  const allowDrop = useCallback<NonNullable<TreeProps['allowDrop']>>(
    ({ dragNode, dropNode, dropPosition }) => {
      const dragId = String(dragNode.key);
      const dropId = String(dropNode.key);

      if (dragId === dropId) return false;
      if (isDescendantOf(tree, dropId, dragId)) return false;

      const dragNodeData = findNode(tree, dragId);
      if (!dragNodeData) return false;

      const dropToGap = dropPosition !== 0;
      const targetLevel = resolveDropTargetLevel(tree, dropId, dropToGap);
      const subtreeEndLevel = targetLevel + getSubtreeDepth(dragNodeData) - 1;

      return subtreeEndLevel <= maxLevel;
    },
    [maxLevel, tree]
  );

  const handleDrop = useCallback<NonNullable<TreeProps['onDrop']>>(
    async info => {
      const dragId = String(info.dragNode.key);
      const dropId = String(info.node.key);

      if (dragId === dropId) return;

      const dragNodeData = findNode(tree, dragId);
      if (!dragNodeData) return;

      const dropPos = info.node.pos.split('-');
      const dropPosition = info.dropPosition - Number(dropPos[dropPos.length - 1]);

      if (!info.dropToGap) {
        if (!canAddChild(dropId)) {
          window.$message?.warning(t('page.tradingSystem.maxDepthReached'));
          return;
        }
      } else {
        const dropToGap = true;
        const targetLevel = resolveDropTargetLevel(tree, dropId, dropToGap);
        const subtreeEndLevel = targetLevel + getSubtreeDepth(dragNodeData) - 1;
        if (subtreeEndLevel > maxLevel) {
          window.$message?.warning(t('page.tradingSystem.maxDepthReached'));
          return;
        }
      }

      const moveTarget = resolveMoveAfterDrop(tree, {
        dragId,
        dropId,
        dropPosition,
        dropToGap: info.dropToGap
      });
      if (!moveTarget) return;

      try {
        await move.mutateAsync({
          color: dragNodeData.color ?? undefined,
          description: normalizeDescription(dragNodeData.description),
          id: dragId,
          name: dragNodeData.name,
          parentId: moveTarget.parentId,
          sortOrder: moveTarget.sortOrder
        });

        if (!info.dropToGap) {
          setExpandedKeys(prev => [...new Set([...prev, dropId])]);
        }
      } catch {
        // 错误提示由 request 统一处理
      }
    },
    [canAddChild, maxLevel, move, t, tree]
  );

  const openAddRoot = useCallback(() => {
    setModal({ open: true, operateType: 'add', parentId: null, targetId: null });
  }, []);

  const openAddChild = useCallback(
    (parentId: string) => {
      if (!canAddChild(parentId)) return;
      setExpandedKeys(prev => (prev.includes(parentId) ? prev : [...prev, parentId]));
      setModal({ open: true, operateType: 'addChild', parentId, targetId: null });
    },
    [canAddChild]
  );

  const openEdit = useCallback((targetId: string) => {
    setModal({ open: true, operateType: 'edit', parentId: null, targetId });
  }, []);

  const closeModal = useCallback(() => {
    setModal(initialModalState);
  }, []);

  const submitModal = useCallback(
    async (values: NodeFormValues) => {
      const { color, description, name } = values;

      if (modal.operateType === 'edit' && modal.targetId) {
        const colorPayload = formatColorForApi(color, 'edit', editNode?.color);
        await update.mutateAsync({
          ...(colorPayload !== undefined ? { color: colorPayload } : {}),
          description: normalizeDescription(description),
          id: modal.targetId,
          name
        });
        closeModal();
        return;
      }

      const parentId = modal.operateType === 'addChild' ? modal.parentId : null;
      if (parentId && !canAddChild(parentId)) {
        window.$message?.warning(t('page.tradingSystem.maxDepthReached'));
        return;
      }

      const createColor = formatColorForApi(color, 'create');
      const created = await create.mutateAsync({
        ...(createColor ? { color: createColor } : {}),
        description: normalizeDescription(description),
        name,
        parentId: parentId ?? ROOT_PARENT_ID
      });

      if (parentId) {
        setExpandedKeys(prev => [...new Set([...prev, parentId])]);
      }
      setSelectedId(mapApiNodeToUi(created).id);
      closeModal();
    },
    [canAddChild, closeModal, create, editNode?.color, modal, t, update]
  );

  const deleteNode = useCallback(
    async (id: string) => {
      await remove.mutateAsync(id);
      if (selectedId === id) setSelectedId(null);
    },
    [remove, selectedId]
  );

  const modalInitialValues = useMemo((): NodeFormValues | undefined => {
    if (!isEditModal || !editNode) return undefined;
    return {
      color: editNode.color ?? undefined,
      description: editNode.description,
      name: editNode.name
    };
  }, [editNode, isEditModal]);

  const modalSubmitting = create.isPending || update.isPending;
  const dragLoading = move.isPending;

  return {
    allowDrop,
    antTreeData,
    canAddChild,
    closeModal,
    deleteNode,
    dragLoading,
    editLoading,
    expandedKeys,
    handleDrop,
    modal,
    modalInitialValues,
    modalSubmitting,
    openAddChild,
    openAddRoot,
    openEdit,
    refetchTree: refetch,
    selectedId,
    selectedNode,
    setExpandedKeys,
    setSelectedId,
    submitModal,
    tree,
    treeLoading
  };
}
