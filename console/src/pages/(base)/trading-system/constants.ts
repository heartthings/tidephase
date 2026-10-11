export const MAX_NODE_DEPTH = 5;

/** 右侧预览中节点描述的最大展示字符数 */
export const PREVIEW_DESCRIPTION_MAX_LENGTH = 20;

/** 右侧预览中始终展示描述的最大层级（L1、L2）；超过则悬停显示 */
export const PREVIEW_DESCRIPTION_VISIBLE_MAX_LEVEL = 2;

/** 左侧树中节点描述的最大展示字符数 */
export const TREE_DESCRIPTION_MAX_LENGTH = 10;

/** 左侧树面板固定宽度（px） */
export const TREE_PANEL_WIDTH = 360;

/** Depth-based palette for nested visualization (0-indexed) */
export const DEPTH_THEMES = [
  {
    accent: '#3b82f6',
    bg: 'rgba(59, 130, 246, 0.08)',
    border: 'rgba(59, 130, 246, 0.45)',
    label: 'rgba(37, 99, 235, 0.12)'
  },
  {
    accent: '#0ea5e9',
    bg: 'rgba(14, 165, 233, 0.08)',
    border: 'rgba(14, 165, 233, 0.42)',
    label: 'rgba(2, 132, 199, 0.12)'
  },
  {
    accent: '#f59e0b',
    bg: 'rgba(245, 158, 11, 0.1)',
    border: 'rgba(245, 158, 11, 0.45)',
    label: 'rgba(217, 119, 6, 0.14)'
  },
  {
    accent: '#f97316',
    bg: 'rgba(249, 115, 22, 0.09)',
    border: 'rgba(249, 115, 22, 0.42)',
    label: 'rgba(234, 88, 12, 0.12)'
  },
  {
    accent: '#8b5cf6',
    bg: 'rgba(139, 92, 246, 0.09)',
    border: 'rgba(139, 92, 246, 0.45)',
    label: 'rgba(124, 58, 237, 0.14)'
  }
] as const;
