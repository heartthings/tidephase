type Props = { value?: number | null; suffix?: string; className?: string };

export function Pct({ value, suffix = '%', className = '' }: Props) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <span className={`gs-flat ${className}`}>—</span>;
  }
  const cls = value > 0 ? 'gs-up' : value < 0 ? 'gs-down' : 'gs-flat';
  const sign = value > 0 ? '+' : '';
  return (
    <span className={`${cls} ${className}`}>
      {sign}
      {value.toFixed(2)}
      {suffix}
    </span>
  );
}
