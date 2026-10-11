import clsx from 'clsx';

import { type NodeVisualTheme, getNodeVisualTheme } from '../node-color';
import type { TradingSystemNode } from '../types';

import styles from './structure-tree-panel.module.scss';
import TreeNodeRowActions from './tree-node-row-actions';
import TreeNodeRowBody from './tree-node-row-body';
import TreeNodeRowLeading from './tree-node-row-leading';

interface TreeNodeRowProps {
  addable: boolean;
  isSelected: boolean;
  labels: {
    addChild: string;
    deleteConfirm: string;
    editNode: string;
  };
  nodeId: string;
  onAddChild: (id: string) => void;
  onDelete: (id: string) => void | Promise<void>;
  onEdit: (id: string) => void;
  title: string;
  treeNode: TradingSystemNode | null;
}

interface RowClassNameParams {
  depth: number;
  hasChildren: boolean;
  isChild: boolean;
  isSelected: boolean;
}

function getRowClassName({ depth, hasChildren, isChild, isSelected }: RowClassNameParams) {
  return clsx(
    styles.nodeRow,
    hasChildren && styles.nodeRowParent,
    isChild && styles.nodeRowChild,
    isChild && depth === 3 && styles.nodeRowDepth3,
    isChild && depth === 4 && styles.nodeRowDepth4,
    isChild && depth >= 5 && styles.nodeRowDepth5,
    isSelected && styles.nodeRowSelected
  );
}

function getRowStyle(accentTheme: NodeVisualTheme | null, isSelected: boolean) {
  if (!accentTheme) return undefined;
  return {
    borderColor: isSelected ? accentTheme.border : 'transparent',
    boxShadow: isSelected ? `0 2px 12px ${accentTheme.border}` : undefined
  };
}

const TreeNodeRow = ({
  addable,
  isSelected,
  labels,
  nodeId,
  onAddChild,
  onDelete,
  onEdit,
  title,
  treeNode
}: TreeNodeRowProps) => {
  const hasChildren = (treeNode?.children.length ?? 0) > 0;
  const accentTheme = treeNode?.color ? getNodeVisualTheme(treeNode.color, 0) : null;
  const depth = treeNode?.level ?? 1;
  const isChild = depth > 1;

  return (
    <div
      className={getRowClassName({ depth, hasChildren, isChild, isSelected })}
      style={getRowStyle(accentTheme, isSelected)}
    >
      <TreeNodeRowLeading
        accentTheme={accentTheme}
        hasChildren={hasChildren}
        isChild={isChild}
      />
      <TreeNodeRowBody
        isChild={isChild}
        nameColor={accentTheme?.accent}
        title={title}
        treeNode={treeNode}
      />
      <TreeNodeRowActions
        addable={addable}
        labels={labels}
        nodeId={nodeId}
        onAddChild={onAddChild}
        onDelete={onDelete}
        onEdit={onEdit}
      />
    </div>
  );
};

export default TreeNodeRow;
