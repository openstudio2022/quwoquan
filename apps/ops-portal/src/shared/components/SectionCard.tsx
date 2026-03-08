import type { ReactNode } from 'react';

type SectionCardProps = {
  title: string;
  subtitle?: string;
  aside?: ReactNode;
  children: ReactNode;
};

export function SectionCard({ title, subtitle, aside, children }: SectionCardProps) {
  return (
    <section className="section-card">
      <div className="section-card__header">
        <div>
          <h2 className="section-card__title">{title}</h2>
          {subtitle ? <div className="section-card__subtitle">{subtitle}</div> : null}
        </div>
        {aside}
      </div>
      <div className="section-card__body">{children}</div>
    </section>
  );
}
