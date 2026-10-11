import { Icon } from '@iconify/react';
import { Empty, Spin, Tag } from 'antd';
import clsx from 'clsx';
import { AnimatePresence, motion } from 'motion/react';

import { PREVIEW_DESCRIPTION_VISIBLE_MAX_LEVEL } from '../constants';
import { getNodeVisualTheme } from '../node-color';
import { getPreviewDensityLevel } from '../preview-density';
import type { TradingSystemNode } from '../types';

import NestedStructureBox from './nested-structure-box';
import PreviewDescriptionHost from './preview-description-host';
import PreviewNodeDescription from './preview-node-description';
import PreviewStructureLeafBox from './preview-structure-leaf-box';

interface StructureCanvasPanelProps {
  loading?: boolean;
  onSelect: (id: string) => void;
  selectedId: string | null;
  selectedNode: TradingSystemNode | null;
  tree: TradingSystemNode[];
}

interface RootChildrenRowProps {
  onSelect: (id: string) => void;
  root: TradingSystemNode;
  selectedId: string | null;
}

const RootChildrenRow = ({ onSelect, root, selectedId }: RootChildrenRowProps) => {
  const density = getPreviewDensityLevel(root.children.length);

  return (
    <div className={clsx('min-h-100px flex', density === 'normal' ? 'gap-12px' : 'gap-6px overflow-x-auto')}>
      <AnimatePresence mode="popLayout">
        {root.children.map((child, childIndex) => (
          <motion.div
            layout
            className={clsx('min-w-0 flex flex-col', density === 'normal' ? 'flex-1' : 'flex-1 shrink-0')}
            key={child.id}
            transition={{ delay: childIndex * 0.05, duration: 0.28 }}
          >
            {child.children.length > 0 ? (
              <NestedStructureBox
                depth={1}
                node={child}
                selectedId={selectedId}
                siblingCount={root.children.length}
                onSelect={onSelect}
              />
            ) : (
              <PreviewStructureLeafBox
                density={density}
                depth={1}
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
};

const StructureCanvasPanel = ({ loading, onSelect, selectedId, selectedNode, tree }: StructureCanvasPanelProps) => {
  const { t } = useTranslation();

  const renderCanvasBody = () => {
    if (loading) {
      return (
        <div className="h-full flex-center py-48px">
          <Spin />
        </div>
      );
    }
    if (tree.length === 0) {
      return (
        <div className="h-full flex-center">
          <Empty description={t('page.tradingSystem.emptyCanvas')} />
        </div>
      );
    }
    return (
      <div className="flex flex-col gap-20px">
        <AnimatePresence mode="popLayout">
          {tree.map((root, rootIndex) => {
            const theme = getNodeVisualTheme(root.color, 0);
            return (
              <motion.section
                layout
                animate={{ opacity: 1, y: 0 }}
                className="flex gap-12px"
                exit={{ opacity: 0, y: -12 }}
                initial={{ opacity: 0, y: 16 }}
                key={root.id}
                transition={{ delay: rootIndex * 0.06, duration: 0.32 }}
              >
                <div
                  className={clsx(
                    'w-36px flex shrink-0 items-center justify-center border rounded-10px border-solid py-12px'
                  )}
                  style={{
                    background: theme.label,
                    borderColor: theme.border,
                    writingMode: 'vertical-rl'
                  }}
                >
                  <span
                    className="text-13px font-700 tracking-4px"
                    style={{ color: theme.accent }}
                  >
                    {root.name}
                  </span>
                </div>

                <div
                  className="min-w-0 flex-1 border-2 rounded-12px border-solid p-14px"
                  style={{
                    background: theme.bg,
                    borderColor: theme.border
                  }}
                >
                  {root.description ? (
                    <div className="m-0 mb-12px text-center">
                      <PreviewNodeDescription
                        className="text-12px"
                        description={root.description}
                        level={root.level}
                      />
                    </div>
                  ) : null}

                  {root.children.length > 0 ? (
                    <RootChildrenRow
                      root={root}
                      selectedId={selectedId}
                      onSelect={onSelect}
                    />
                  ) : (
                    <div className="text-secondary py-24px text-center text-12px">
                      {t('page.tradingSystem.noChildrenHint')}
                    </div>
                  )}
                </div>
              </motion.section>
            );
          })}
        </AnimatePresence>
      </div>
    );
  };

  return (
    <motion.div
      animate={{ opacity: 1, x: 0 }}
      className="h-full flex flex-col overflow-hidden border border-[var(--color-border)] rounded-12px border-solid bg-[var(--color-bg-container)] shadow-sm"
      initial={{ opacity: 0, x: 16 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="flex flex-wrap items-center justify-between gap-8px border-b border-[var(--color-border)] border-solid px-16px py-14px">
        <div className="flex items-center gap-8px">
          <span className="h-28px w-28px flex-center rounded-8px bg-[rgba(139,92,246,0.12)] text-[#8b5cf6]">
            <Icon icon="mdi:layers-triple-outline" />
          </span>
          <div>
            <p className="m-0 text-15px font-600">{t('page.tradingSystem.canvasTitle')}</p>
            <p className="text-secondary m-0 text-12px">{t('page.tradingSystem.canvasSubtitle')}</p>
          </div>
        </div>
        {selectedNode ? (
          <motion.div
            animate={{ opacity: 1, y: 0 }}
            className="max-w-full flex flex-wrap items-center gap-6px"
            initial={{ opacity: 0, y: 4 }}
          >
            <PreviewDescriptionHost
              description={selectedNode.description}
              level={selectedNode.level}
            >
              <Tag
                color={selectedNode.color ? undefined : 'processing'}
                style={
                  selectedNode.color
                    ? {
                        background: getNodeVisualTheme(selectedNode.color, 0).label,
                        borderColor: getNodeVisualTheme(selectedNode.color, 0).border,
                        color: getNodeVisualTheme(selectedNode.color, 0).accent
                      }
                    : undefined
                }
              >
                {selectedNode.name}
              </Tag>
              {selectedNode.description && selectedNode.level <= PREVIEW_DESCRIPTION_VISIBLE_MAX_LEVEL ? (
                <PreviewNodeDescription
                  className="text-12px"
                  description={selectedNode.description}
                  level={selectedNode.level}
                />
              ) : null}
            </PreviewDescriptionHost>
          </motion.div>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-16px">{renderCanvasBody()}</div>
    </motion.div>
  );
};

export default StructureCanvasPanel;
