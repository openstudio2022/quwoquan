import type { ReactNode } from 'react';

export type PortalFrameProps = {
  sidebar: ReactNode;
  topbar?: ReactNode;
  children: ReactNode;
};

export function PortalFrame({ sidebar, topbar, children }: PortalFrameProps) {
  return (
    <div className="portal-root">
      <aside className="portal-sidebar">{sidebar}</aside>
      <div className="portal-content">
        {topbar ? <header className="portal-topbar">{topbar}</header> : null}
        {children}
      </div>
    </div>
  );
}
