import { SectionCard } from '@ops-ui';
import type { ReactNode } from 'react';

export { SectionCard as Card };

export function Status({ error, loading }: { error?: string; loading?: boolean }) {
  if (loading) return <div className="notice">正在读取本地快照…</div>;
  if (error) {
    return <div className="notice notice--error"><strong>无法读取内容池</strong><span>{error}</span></div>;
  }
  return null;
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: string }) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}
