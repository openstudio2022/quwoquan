import type { ReactNode } from 'react';

type TrendTone = 'positive' | 'negative' | 'warning';

type KpiCardProps = {
  label: string;
  value: string;
  icon: ReactNode;
  trendLabel: string;
  trendTone: TrendTone;
  description: string;
};

export function KpiCard({
  label,
  value,
  icon,
  trendLabel,
  trendTone,
  description,
}: KpiCardProps) {
  return (
    <section className="section-card kpi-card">
      <div className="kpi-card__header">
        <div className="kpi-card__label">{label}</div>
        {icon}
      </div>
      <div className="kpi-card__value">{value}</div>
      <div className={`kpi-card__trend kpi-card__trend--${trendTone}`}>{trendLabel}</div>
      <div className="item-subtitle">{description}</div>
    </section>
  );
}
