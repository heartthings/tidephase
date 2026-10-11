import { Icon } from '@iconify/react';
import { Button, Empty, Spin, Tree } from 'antd';
import type { DataNode, TreeProps } from 'antd/es/tree';
import { motion } from 'motion/react';

import type { TradingSystemNode } from '../types';
import { findNode } from '../utils';

import styles from './structure-tree-panel.module.scss';
import TreeNodeRow from './tree-node-row';

interface StructureTreePanelProps {
  allowDrop?: TreeProps['allowDrop'];
  canAddChild: (parentId: string | null) => boolean;
  dragLoading?: boolean;
  expandedKeys: string[];
  loading?: boolean;
  onAddChild: (parentId: string) => void;
  onAddRoot: () => void;
  onDelete: (id: string) => void | Promise<void>;
  onDrop?: TreeProps['onDrop'];
  onEdit: (id: string) => void;
  onExpand: (keys: string[]) => void;
  onSelect: (id: string | null) => void;
  selectedId: string | null;
  tree: TradingSystemNode[];
  treeData: DataNode[];
}

const StructureTreePanel = ({
  allowDrop,
  canAddChild,
  dragLoading,
  expandedKeys,
  loading,
  onAddChild,
  onAddRoot,
  onDelete,
  onDrop,
  onEdit,
  onExpand,
  onSelect,
  selectedId,
  tree,
  treeData
}: StructureTreePanelProps) => {
  const { t } = useTranslation();

  const rowLabels = {
    addChild: t('page.tradingSystem.addChild'),
    deleteConfirm: t('page.tradingSystem.deleteConfirm'),
    editNode: t('page.tradingSystem.editNode')
  };

  const renderTreeBody = () => {
    if (loading) {
      return (
        <div className="h-full flex-center py-48px">
          <Spin />
        </div>
      );
    }
    if (tree.length === 0) {
      return (
        <div className={styles.emptyWrap}>
          <Empty
            description={t('page.tradingSystem.emptyTree')}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        </div>
      );
    }
    return (
      <Tree
        blockNode
        allowDrop={allowDrop}
        className={styles.tree}
        expandedKeys={expandedKeys}
        selectedKeys={selectedId ? [selectedId] : []}
        showLine={{ showLeafIcon: false }}
        treeData={treeData}
        draggable={{
          icon: (
            <Icon
              className="text-15px"
              icon="mdi:drag-vertical"
            />
          ),
          nodeDraggable: () => !dragLoading
        }}
        switcherIcon={({ expanded }) => (
          <Icon
            className="text-14px text-icon opacity-70 transition-transform"
            icon={expanded ? 'mdi:chevron-down' : 'mdi:chevron-right'}
          />
        )}
        titleRender={node => {
          const id = String(node.key);
          const treeNode = findNode(tree, id);

          return (
            <TreeNodeRow
              addable={canAddChild(id)}
              isSelected={selectedId === id}
              labels={rowLabels}
              nodeId={id}
              title={node.title as string}
              treeNode={treeNode}
              onAddChild={onAddChild}
              onDelete={onDelete}
              onEdit={onEdit}
            />
          );
        }}
        onDrop={onDrop}
        onExpand={keys => onExpand(keys as string[])}
        onSelect={keys => onSelect(keys[0] ? String(keys[0]) : null)}
      />
    );
  };

  return (
    <motion.div
      animate={{ opacity: 1, x: 0 }}
      className={`${styles.panel} h-full flex flex-col overflow-hidden border border-[var(--color-border)] rounded-12px border-solid shadow-sm`}
      initial={{ opacity: 0, x: -16 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className={`${styles.header} px-16px py-14px`}>
        <div className="flex items-center gap-10px">
          <span className="h-36px w-36px flex-center rounded-10px bg-primary/12 text-primary shadow-sm">
            <Icon
              className="text-20px"
              icon="mdi:sitemap"
            />
          </span>
          <div className="min-w-0 flex-1">
            <p className="m-0 text-15px font-600">{t('page.tradingSystem.treeTitle')}</p>
            <p className="text-secondary m-0 mt-2px text-12px leading-relaxed">
              {t('page.tradingSystem.treeSubtitle')}
            </p>
          </div>
        </div>
        <Button
          block
          className={`${styles.addRootBtn} mt-14px`}
          icon={<Icon icon="mdi:plus" />}
          type="primary"
          onClick={onAddRoot}
        >
          {t('page.tradingSystem.addRoot')}
        </Button>
      </div>

      <div className={`${styles.treeWrap} min-h-0 flex-1`}>{renderTreeBody()}</div>
    </motion.div>
  );
};

export default StructureTreePanel;
