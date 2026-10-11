export interface PlateForceItem {
  code: string;
  growthRate?: number | null;
  latestCje?: number | null;
  latestLargeForce: number;
  latestStrong?: number | null;
  name: string;
}

export interface ShanghaiIndexSnapshot {
  changePct: number | null;
  close: number | null;
  date: string | null;
}

export function formatYi(value: number): string {
  const abs = Math.abs(value);
  const sign = value >= 0 ? '+' : '-';
  if (abs >= 100) {
    return `${sign}${abs.toFixed(1)}亿`;
  }
  if (abs >= 10) {
    return `${sign}${abs.toFixed(1)}亿`;
  }
  return `${sign}${abs.toFixed(2)}亿`;
}

export function pickTopByAbs(items: PlateForceItem[], limitPerSide: number): PlateForceItem[] {
  const inflow = items
    .filter(d => d.latestLargeForce > 0)
    .sort((a, b) => b.latestLargeForce - a.latestLargeForce)
    .slice(0, limitPerSide);
  const outflow = items
    .filter(d => d.latestLargeForce < 0)
    .sort((a, b) => a.latestLargeForce - b.latestLargeForce)
    .slice(0, limitPerSide);
  return [...inflow, ...outflow];
}

export function sessionTitle(now = new Date()): string {
  const h = now.getHours();
  const m = now.getMinutes();
  const mins = h * 60 + m;
  if (mins < 9 * 60 + 30) return '盘前资金流向';
  if (mins < 11 * 60 + 31) return '午盘资金流向';
  if (mins < 13 * 60) return '午间资金流向';
  if (mins < 15 * 60 + 1) return '尾盘资金流向';
  return '收盘资金流向';
}
