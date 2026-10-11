import type { TradingSystemNode } from './types';
import { findNode } from './utils';

export const ROOT_PARENT_ID = '0';

export interface TreeDropParams {
  dragId: string;
  dropId: string;
  dropPosition: number;
  dropToGap: boolean;
}

export function cloneTree(nodes: TradingSystemNode[]): TradingSystemNode[] {
  return nodes.map(node => ({
    ...node,
    children: cloneTree(node.children)
  }));
}

function loopTree(
  nodes: TradingSystemNode[],
  id: string,
  callback: (item: TradingSystemNode, index: number, arr: TradingSystemNode[]) => void
): boolean {
  for (const [index, node] of nodes.entries()) {
    if (node.id === id) {
      callback(node, index, nodes);
      return true;
    }
    if (node.children.length && loopTree(node.children, id, callback)) {
      return true;
    }
  }
  return false;
}

export function isDescendantOf(tree: TradingSystemNode[], candidateId: string, ancestorId: string): boolean {
  const ancestor = findNode(tree, ancestorId);
  if (!ancestor) return false;

  const walk = (node: TradingSystemNode): boolean => {
    if (node.id === candidateId) return true;
    return node.children.some(walk);
  };

  return walk(ancestor);
}

export function getSubtreeDepth(node: TradingSystemNode): number {
  if (!node.children.length) return 1;
  return 1 + Math.max(...node.children.map(child => getSubtreeDepth(child)));
}

export function findParentContext(
  tree: TradingSystemNode[],
  nodeId: string,
  parentId: string = ROOT_PARENT_ID
): { parentId: string; siblings: TradingSystemNode[] } | null {
  for (const node of tree) {
    if (node.id === nodeId) {
      return { parentId, siblings: tree };
    }
    const found = findParentContext(node.children, nodeId, node.id);
    if (found) return found;
  }
  return null;
}

/** 根据 Ant Design Tree 的 drop 规则计算移动后的 parentId 与 sortOrder */
export function resolveMoveAfterDrop(
  sourceTree: TradingSystemNode[],
  params: TreeDropParams
): { parentId: string; sortOrder: number } | null {
  const { dragId, dropId, dropPosition, dropToGap } = params;
  const data = cloneTree(sourceTree);
  let dragObj: TradingSystemNode | undefined;

  loopTree(data, dragId, (_item, index, arr) => {
    dragObj = arr[index];
    arr.splice(index, 1);
  });

  if (!dragObj) return null;

  const dropNode = findNode(data, dropId);
  const dropHasChildren = (dropNode?.children.length ?? 0) > 0;

  if (!dropToGap) {
    loopTree(data, dropId, item => {
      item.children = [dragObj!, ...item.children];
    });
  } else if (dropHasChildren && dropPosition === 1) {
    loopTree(data, dropId, item => {
      item.children = [dragObj!, ...item.children];
    });
  } else {
    let targetArr: TradingSystemNode[] = [];
    let targetIndex = 0;
    loopTree(data, dropId, (_item, index, arr) => {
      targetArr = arr;
      targetIndex = index;
    });
    if (dropPosition === -1) {
      targetArr.splice(targetIndex, 0, dragObj);
    } else {
      targetArr.splice(targetIndex + 1, 0, dragObj);
    }
  }

  const ctx = findParentContext(data, dragId);
  if (!ctx) return null;

  const sortOrder = ctx.siblings.findIndex(n => n.id === dragId);
  if (sortOrder < 0) return null;

  return { parentId: ctx.parentId, sortOrder };
}

/** 计算拖拽落点下，被拖节点移动后的层级 */
export function resolveDropTargetLevel(tree: TradingSystemNode[], dropId: string, dropToGap: boolean): number {
  const dropNode = findNode(tree, dropId);
  if (!dropNode) return 1;

  if (!dropToGap) {
    return dropNode.level + 1;
  }

  const ctx = findParentContext(tree, dropId);
  if (!ctx || ctx.parentId === ROOT_PARENT_ID) return 1;

  const parent = findNode(tree, ctx.parentId);
  return parent ? parent.level + 1 : 1;
}
