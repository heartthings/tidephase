import { DEPTH_THEMES } from './constants';

/** 推荐色盘（与体系层级默认色协调） */
export const RECOMMENDED_NODE_COLORS = [
  '#3B82F6',
  '#2563EB',
  '#0EA5E9',
  '#06B6D4',
  '#10B981',
  '#059669',
  '#14B8A6',
  '#22C55E',
  '#84CC16',
  '#65A30D',
  '#EAB308',
  '#F59E0B',
  '#F97316',
  '#EA580C',
  '#EF4444',
  '#DC2626',
  '#F43F5E',
  '#EC4899',
  '#DB2777',
  '#D946EF',
  '#A855F7',
  '#8B5CF6',
  '#6366F1',
  '#4F46E5',
  '#64748B',
  '#475569',
  '#78716C',
  '#A16207'
] as const;

export interface NodeVisualTheme {
  accent: string;
  bg: string;
  border: string;
  label: string;
}

function parseHexColor(hex: string): { b: number; g: number; r: number } | null {
  const normalized = hex.trim().replace(/^#/, '');
  if (!/^[0-9A-Fa-f]{3}$|^[0-9A-Fa-f]{6}$/.test(normalized)) return null;

  const full =
    normalized.length === 3
      ? normalized
          .split('')
          .map(ch => ch + ch)
          .join('')
      : normalized;

  return {
    b: Number.parseInt(full.slice(4, 6), 16),
    g: Number.parseInt(full.slice(2, 4), 16),
    r: Number.parseInt(full.slice(0, 2), 16)
  };
}

export function normalizeHexColor(hex: string): string {
  const rgb = parseHexColor(hex);
  if (!rgb) return hex;
  const toHex = (n: number) => n.toString(16).padStart(2, '0').toUpperCase();
  return `#${toHex(rgb.r)}${toHex(rgb.g)}${toHex(rgb.b)}`;
}

export function themeFromHex(hex: string): NodeVisualTheme | null {
  const rgb = parseHexColor(hex);
  if (!rgb) return null;
  const accent = normalizeHexColor(hex);
  const { b, g, r } = rgb;
  return {
    accent,
    bg: `rgba(${r}, ${g}, ${b}, 0.08)`,
    border: `rgba(${r}, ${g}, ${b}, 0.45)`,
    label: `rgba(${r}, ${g}, ${b}, 0.14)`
  };
}

export function getNodeVisualTheme(color: string | null | undefined, depth: number): NodeVisualTheme {
  if (color) {
    const custom = themeFromHex(color);
    if (custom) return custom;
  }
  return DEPTH_THEMES[Math.min(depth, DEPTH_THEMES.length - 1)];
}

/** 创建/编辑提交时的 color 字段 */
export function formatColorForApi(
  color: string | undefined,
  mode: 'create' | 'edit',
  previousColor?: string | null
): string | undefined {
  if (color) return normalizeHexColor(color);
  if (mode === 'create') return undefined;
  if (previousColor) return '';
  return undefined;
}
