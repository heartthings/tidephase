import { Icon } from '@iconify/react';
import clsx from 'clsx';

import type { NodeVisualTheme } from '../node-color';

import styles from './structure-tree-panel.module.scss';

interface TreeNodeRowLeadingProps {
  accentTheme: NodeVisualTheme | null;
  hasChildren: boolean;
  isChild: boolean;
}

const TreeNodeRowLeading = ({ accentTheme, hasChildren, isChild }: TreeNodeRowLeadingProps) => (
  <>
    {isChild ? (
      <span
        aria-hidden
        className={styles.branchMark}
        style={accentTheme ? { color: accentTheme.accent } : undefined}
      >
        <Icon icon="mdi:subdirectory-arrow-right" />
      </span>
    ) : null}

    <span
      className={clsx(styles.accent, !accentTheme && styles.accentDefault)}
      style={accentTheme ? { background: accentTheme.accent } : undefined}
    />

    <span
      className={clsx(styles.iconWrap, hasChildren ? styles.iconWrapFolder : styles.iconWrapLeaf)}
      style={
        accentTheme
          ? {
              background: accentTheme.label,
              color: accentTheme.accent
            }
          : undefined
      }
    >
      <Icon
        className="text-16px"
        icon={hasChildren ? 'mdi:folder-outline' : 'mdi:file-document-outline'}
      />
    </span>
  </>
);

export default TreeNodeRowLeading;
