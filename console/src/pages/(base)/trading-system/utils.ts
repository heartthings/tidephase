import { PREVIEW_DESCRIPTION_MAX_LENGTH } from './constants';
import type { TradingSystemNode } from './types';

export function formatPreviewDescription(text: string, maxLength: number = PREVIEW_DESCRIPTION_MAX_LENGTH): string {
  const value = text.trim();
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength)}...`;
}

export function isPreviewDescriptionTruncated(
  text: string,
  maxLength: number = PREVIEW_DESCRIPTION_MAX_LENGTH
): boolean {
  return text.trim().length > maxLength;
}

export function mapApiNodeToUi(node: Api.TradingSystem.Node): TradingSystemNode {
  return {
    children: (node.children ?? []).map(mapApiNodeToUi),
    color: node.color ?? null,
    createdTime: node.createdTime,
    description: node.description ?? '',
    id: node.id,
    level: node.level,
    name: node.name,
    parentId: node.parentId,
    sortOrder: node.sortOrder,
    updatedTime: node.updatedTime
  };
}

export function findNode(nodes: TradingSystemNode[], id: string): TradingSystemNode | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    const found = findNode(node.children, id);
    if (found) return found;
  }
  return null;
}

export function canAddChildToNode(node: TradingSystemNode, maxLevel: number): boolean {
  return node.level < maxLevel;
}

export function toAntTreeData(nodes: TradingSystemNode[]): {
  children?: ReturnType<typeof toAntTreeData>;
  isLeaf?: boolean;
  key: string;
  title: string;
}[] {
  return nodes.map(node => ({
    children: node.children.length > 0 ? toAntTreeData(node.children) : undefined,
    isLeaf: node.children.length === 0,
    key: node.id,
    title: node.name
  }));
}

export function collectExpandedKeys(nodes: TradingSystemNode[]): string[] {
  const keys: string[] = [];
  const walk = (list: TradingSystemNode[]) => {
    list.forEach(node => {
      if (node.children.length > 0) {
        keys.push(node.id);
        walk(node.children);
      }
    });
  };
  walk(nodes);
  return keys;
}

export function collectAllNodeIds(nodes: TradingSystemNode[]): string[] {
  const ids: string[] = [];
  const walk = (list: TradingSystemNode[]) => {
    list.forEach(node => {
      ids.push(node.id);
      if (node.children.length > 0) walk(node.children);
    });
  };
  walk(nodes);
  return ids;
}
