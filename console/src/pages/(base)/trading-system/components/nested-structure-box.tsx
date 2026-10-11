import { Icon } from '@iconify/react';
import clsx from 'clsx';
import { motion } from 'motion/react';

import { PREVIEW_DESCRIPTION_VISIBLE_MAX_LEVEL } from '../constants';
import { getNodeVisualTheme } from '../node-color';
import {
  PREVIEW_DENSITY_HEADER_CLASS,
  getPreviewDensityLevel,
  shouldHideDescriptionInPreview
} from '../preview-density';
import type { TradingSystemNode } from '../types';

import PreviewChildrenRow from './preview-children-row';
import PreviewDescriptionHost from './preview-description-host';
import PreviewNodeDescription from './preview-node-description';
import PreviewNodeTitle from './preview-node-title';

interface NestedStructureBoxProps {
  depth: number;
  node: TradingSystemNode;
  onSelect: (id: string) => void;
  selectedId: string | null;
  /** 与同级节点数量，用于动态缩略展示 */
  siblingCount?: number;
}

const NestedStructureBox = ({ depth, node, onSelect, selectedId, siblingCount = 1 }: NestedStructureBoxProps) => {
  const theme = getNodeVisualTheme(node.color, depth);
  const isSelected = selectedId === node.id;
  const hasChildren = node.children.length > 0;
  const childrenDensity = getPreviewDensityLevel(node.children.length);
  const selfDensity = getPreviewDensityLevel(siblingCount);
  const hideSelfDescription =
    shouldHideDescriptionInPreview(selfDensity, node.level) || node.level > PREVIEW_DESCRIPTION_VISIBLE_MAX_LEVEL;

  return (
    <PreviewDescriptionHost
      description={node.description}
      level={node.level}
    >
      <motion.div
        layout
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.92, y: 8 }}
        initial={{ opacity: 0, scale: 0.96, y: 12 }}
        role="button"
        tabIndex={0}
        transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
        whileHover={{ scale: selfDensity === 'normal' ? 1.01 : 1 }}
        whileTap={{ scale: 0.99 }}
        className={clsx(
          'relative min-w-0 w-full flex flex-1 flex-col overflow-hidden rounded-10px border-2 border-solid transition-shadow',
          selfDensity !== 'normal' && 'min-w-0 shrink-0',
          isSelected && 'ring-2 ring-primary ring-offset-2'
        )}
        style={{
          background: theme.bg,
          borderColor: theme.border
        }}
        onClick={e => {
          e.stopPropagation();
          onSelect(node.id);
        }}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onSelect(node.id);
          }
        }}
      >
        <div
          className={clsx('border-b border-solid text-center font-600', PREVIEW_DENSITY_HEADER_CLASS[selfDensity])}
          style={{ borderColor: theme.border }}
        >
          <PreviewNodeTitle
            accentColor={theme.accent}
            density={selfDensity}
            name={node.name}
          />
        </div>

        {!hideSelfDescription && node.description ? (
          <div className="px-10px py-6px text-center">
            <PreviewNodeDescription
              description={node.description}
              level={node.level}
            />
          </div>
        ) : null}

        {hasChildren ? (
          <PreviewChildrenRow
            density={childrenDensity}
            depth={depth}
            node={node}
            selectedId={selectedId}
            onSelect={onSelect}
          />
        ) : (
          <div className="text-secondary flex flex-col items-center justify-center gap-4px px-10px py-16px text-11px">
            <Icon
              className="text-20px opacity-40"
              icon="mdi:shape-outline"
              style={{ color: theme.accent }}
            />
          </div>
        )}
      </motion.div>
    </PreviewDescriptionHost>
  );
};

export default NestedStructureBox;
