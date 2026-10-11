/** 右侧预览同级子节点密度：随数量自动缩小展示 */
export type PreviewDensityLevel = 'compact' | 'dense' | 'normal';

const PREVIEW_NAME_MAX_LENGTH: Record<PreviewDensityLevel, number> = {
  compact: 6,
  dense: 3,
  normal: 999
};

export function getPreviewDensityLevel(siblingCount: number): PreviewDensityLevel {
  if (siblingCount <= 2) return 'normal';
  if (siblingCount <= 4) return 'compact';
  return 'dense';
}

export function formatPreviewNodeName(name: string, density: PreviewDensityLevel): string {
  const value = name.trim();
  const maxLen = PREVIEW_NAME_MAX_LENGTH[density];
  if (value.length <= maxLen) return value;
  return `${value.slice(0, maxLen)}…`;
}

export function isPreviewNodeNameTruncated(name: string, density: PreviewDensityLevel): boolean {
  return name.trim().length > PREVIEW_NAME_MAX_LENGTH[density];
}

export function shouldHideDescriptionInPreview(density: PreviewDensityLevel, nodeLevel: number): boolean {
  if (density === 'dense') return true;
  if (density === 'compact' && nodeLevel > 2) return true;
  return false;
}

export const PREVIEW_DENSITY_CHILDREN_CLASS: Record<PreviewDensityLevel, string> = {
  compact: 'min-h-64px gap-6px overflow-x-auto p-8px',
  dense: 'min-h-48px gap-4px overflow-x-auto p-6px',
  normal: 'min-h-80px gap-8px p-10px'
};

export const PREVIEW_DENSITY_LEAF_CLASS: Record<PreviewDensityLevel, string> = {
  compact: 'min-h-52px min-w-64px shrink-0 px-8px py-8px text-11px',
  dense: 'min-h-44px min-w-48px shrink-0 px-4px py-6px text-10px',
  normal: 'min-h-64px px-12px py-10px text-12px'
};

export const PREVIEW_DENSITY_HEADER_CLASS: Record<PreviewDensityLevel, string> = {
  compact: 'px-8px py-6px text-12px',
  dense: 'px-6px py-5px text-11px',
  normal: 'px-10px py-8px text-13px'
};
