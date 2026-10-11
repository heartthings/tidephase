export const PUBLIC_SCREENS = [
  { hint: '今日冲击列表', id: 'catalyst', label: '催化解读' },
  { hint: '发酵中 · 题材热力', id: 'hot', label: '主线发酵' },
  { hint: '近期预测 · 准确率', id: 'verify', label: '预测闭环' }
] as const;

export type PublicScreenId = (typeof PUBLIC_SCREENS)[number]['id'];
