import clsx from 'clsx';
import { AnimatePresence, motion } from 'motion/react';

import { PREVIEW_DENSITY_CHILDREN_CLASS, type PreviewDensityLevel } from '../preview-density';
import type { TradingSystemNode } from '../types';

import NestedStructureBox from './nested-structure-box';
import PreviewStructureLeafBox from './preview-structure-leaf-box';

interface PreviewChildrenRowProps {
  density: PreviewDensityLevel;
  depth: number;
  node: TradingSystemNode;
  onSelect: (id: string) => void;
  selectedId: string | null;
}

const PreviewChildrenRow = ({ density, depth, node, onSelect, selectedId }: PreviewChildrenRowProps) => (
  <div className={clsx('flex flex-1', PREVIEW_DENSITY_CHILDREN_CLASS[density])}>
    <AnimatePresence mode="popLayout">
      {node.children.map((child, index) => (
        <motion.div
          layout
          className={clsx('min-w-0 flex flex-col', density === 'normal' ? 'flex-1' : 'flex-1 shrink-0')}
          key={child.id}
          transition={{ delay: index * 0.04, duration: 0.25 }}
        >
          {child.children.length > 0 ? (
            <NestedStructureBox
              depth={depth + 1}
              node={child}
              selectedId={selectedId}
              siblingCount={node.children.length}
              onSelect={onSelect}
            />
          ) : (
            <PreviewStructureLeafBox
              density={density}
              depth={depth + 1}
              node={child}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          )}
        </motion.div>
      ))}
    </AnimatePresence>
  </div>
);

export default PreviewChildrenRow;
