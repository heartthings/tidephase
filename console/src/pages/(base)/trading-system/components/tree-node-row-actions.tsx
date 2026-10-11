import { Icon } from '@iconify/react';
import { Popconfirm, Tooltip } from 'antd';
import clsx from 'clsx';

import styles from './structure-tree-panel.module.scss';

interface TreeNodeRowActionsProps {
  addable: boolean;
  labels: {
    addChild: string;
    deleteConfirm: string;
    editNode: string;
  };
  nodeId: string;
  onAddChild: (id: string) => void;
  onDelete: (id: string) => void | Promise<void>;
  onEdit: (id: string) => void;
}

const TreeNodeRowActions = ({ addable, labels, nodeId, onAddChild, onDelete, onEdit }: TreeNodeRowActionsProps) => (
  <div className={styles.actions}>
    {addable ? (
      <Tooltip title={labels.addChild}>
        <span
          className={styles.actionBtn}
          role="button"
          tabIndex={0}
          onClick={e => {
            e.stopPropagation();
            onAddChild(nodeId);
          }}
          onKeyDown={e => {
            if (e.key === 'Enter') {
              e.stopPropagation();
              onAddChild(nodeId);
            }
          }}
        >
          <Icon icon="mdi:plus" />
        </span>
      </Tooltip>
    ) : null}
    <Tooltip title={labels.editNode}>
      <span
        className={styles.actionBtn}
        role="button"
        tabIndex={0}
        onClick={e => {
          e.stopPropagation();
          onEdit(nodeId);
        }}
        onKeyDown={e => {
          if (e.key === 'Enter') {
            e.stopPropagation();
            onEdit(nodeId);
          }
        }}
      >
        <Icon icon="mdi:pencil-outline" />
      </span>
    </Tooltip>
    <Popconfirm
      title={labels.deleteConfirm}
      onConfirm={e => {
        e?.stopPropagation();
        onDelete(nodeId);
      }}
    >
      <span
        className={clsx(styles.actionBtn, styles.actionBtnDanger)}
        role="button"
        tabIndex={0}
        onClick={e => e.stopPropagation()}
        onKeyDown={e => e.stopPropagation()}
      >
        <Icon icon="mdi:trash-can-outline" />
      </span>
    </Popconfirm>
  </div>
);

export default TreeNodeRowActions;
