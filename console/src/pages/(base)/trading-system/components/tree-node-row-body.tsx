import clsx from 'clsx';

import { TREE_DESCRIPTION_MAX_LENGTH } from '../constants';
import type { TradingSystemNode } from '../types';

import styles from './structure-tree-panel.module.scss';
import TruncatedTreeText from './truncated-tree-text';

interface TreeNodeRowBodyProps {
  isChild: boolean;
  nameColor?: string;
  title: string;
  treeNode: TradingSystemNode | null;
}

const TreeNodeRowBody = ({ isChild, nameColor, title, treeNode }: TreeNodeRowBodyProps) => (
  <div className={styles.body}>
    <div className={styles.nameRow}>
      <TruncatedTreeText
        className={styles.name}
        style={nameColor ? { color: nameColor } : undefined}
        text={title}
      />
      {treeNode ? <span className={clsx(styles.level, isChild && styles.levelChild)}>L{treeNode.level}</span> : null}
    </div>
    {treeNode?.description ? (
      <TruncatedTreeText
        className={styles.desc}
        maxLength={TREE_DESCRIPTION_MAX_LENGTH}
        text={treeNode.description}
      />
    ) : null}
  </div>
);

export default TreeNodeRowBody;
