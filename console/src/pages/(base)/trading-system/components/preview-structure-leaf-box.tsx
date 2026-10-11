import clsx from 'clsx';
import { motion } from 'motion/react';

import { PREVIEW_DESCRIPTION_VISIBLE_MAX_LEVEL } from '../constants';
import { getNodeVisualTheme } from '../node-color';
import {
  PREVIEW_DENSITY_LEAF_CLASS,
  type PreviewDensityLevel,
  shouldHideDescriptionInPreview
} from '../preview-density';
import type { TradingSystemNode } from '../types';

import PreviewDescriptionHost from './preview-description-host';
import PreviewNodeDescription from './preview-node-description';
import PreviewNodeTitle from './preview-node-title';

interface PreviewStructureLeafBoxProps {
  density: PreviewDensityLevel;
  depth: number;
  node: TradingSystemNode;
  onSelect: (id: string) => void;
  selectedId: string | null;
}

const PreviewStructureLeafBox = ({ density, depth, node, onSelect, selectedId }: PreviewStructureLeafBoxProps) => {
  const theme = getNodeVisualTheme(node.color, depth);
  const isSelected = selectedId === node.id;
  const hideDescription =
    shouldHideDescriptionInPreview(density, node.level) || node.level > PREVIEW_DESCRIPTION_VISIBLE_MAX_LEVEL;

  return (
    <PreviewDescriptionHost
      description={node.description}
      level={node.level}
    >
      <motion.div
        layout
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.9 }}
        initial={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.22 }}
        whileHover={{ y: density === 'normal' ? -2 : 0 }}
        className={clsx(
          'w-full flex flex-1 flex-col cursor-pointer justify-center rounded-8px border border-solid text-center transition-shadow',
          PREVIEW_DENSITY_LEAF_CLASS[density],
          density !== 'normal' && 'flex-shrink-0',
          isSelected && 'ring-2 ring-primary ring-offset-1'
        )}
        style={{
          background: theme.label,
          borderColor: theme.border
        }}
        onClick={e => {
          e.stopPropagation();
          onSelect(node.id);
        }}
      >
        <PreviewNodeTitle
          accentColor={theme.accent}
          density={density}
          name={node.name}
        />
        {!hideDescription && node.description ? (
          <PreviewNodeDescription
            compact
            className="m-0 mt-4px"
            description={node.description}
            level={node.level}
          />
        ) : null}
      </motion.div>
    </PreviewDescriptionHost>
  );
};

export default PreviewStructureLeafBox;
