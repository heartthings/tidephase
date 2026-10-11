import LazyAnimate from '@/features/animate/LazyMotion';

import NodeOperateModal from './components/node-operate-modal';
import StructureCanvasPanel from './components/structure-canvas-panel';
import StructureTreePanel from './components/structure-tree-panel';
import { TREE_PANEL_WIDTH } from './constants';
import { useTradingSystemTree } from './hooks/use-trading-system-tree';

export const route = {
  meta: {
    constant: true,
    i18nKey: 'route.(base)_trading-system',
    icon: 'mdi:book-open-page-variant',
    order: 2,
    title: 'trading-system'
  }
};

const TradingSystem = () => {
  const {
    allowDrop,
    antTreeData,
    canAddChild,
    closeModal,
    deleteNode,
    dragLoading,
    editLoading,
    expandedKeys,
    handleDrop,
    modal,
    modalInitialValues,
    modalSubmitting,
    openAddChild,
    openAddRoot,
    openEdit,
    selectedId,
    selectedNode,
    setExpandedKeys,
    setSelectedId,
    submitModal,
    tree,
    treeLoading
  } = useTradingSystemTree();

  return (
    <LazyAnimate>
      <div className="h-full min-h-600px flex flex-col gap-12px lg:flex-row">
        <div
          className="h-420px shrink-0 lg:h-full"
          style={{
            maxWidth: TREE_PANEL_WIDTH,
            minWidth: TREE_PANEL_WIDTH,
            width: TREE_PANEL_WIDTH
          }}
        >
          <StructureTreePanel
            allowDrop={allowDrop}
            canAddChild={canAddChild}
            dragLoading={dragLoading}
            expandedKeys={expandedKeys}
            loading={treeLoading}
            selectedId={selectedId}
            tree={tree}
            treeData={antTreeData}
            onAddChild={openAddChild}
            onAddRoot={openAddRoot}
            onDelete={deleteNode}
            onDrop={handleDrop}
            onEdit={openEdit}
            onExpand={setExpandedKeys}
            onSelect={setSelectedId}
          />
        </div>

        <div className="min-h-420px min-w-0 flex-1">
          <StructureCanvasPanel
            loading={treeLoading}
            selectedId={selectedId}
            selectedNode={selectedNode}
            tree={tree}
            onSelect={setSelectedId}
          />
        </div>
      </div>

      <NodeOperateModal
        confirmLoading={modalSubmitting}
        formLoading={editLoading}
        initialValues={modalInitialValues}
        open={modal.open}
        operateType={modal.operateType}
        onClose={closeModal}
        onSubmit={submitModal}
      />
    </LazyAnimate>
  );
};

export default TradingSystem;
