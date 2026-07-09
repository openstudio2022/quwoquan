import type { ReactNode } from 'react';

type PageScaffoldProps = {
  title: string;
  subtitle: string;
  meta?: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
};

export function PageScaffold({
  title,
  subtitle,
  meta,
  actions,
  footer,
  children,
}: PageScaffoldProps) {
  return (
    <div className="page-scaffold">
      <header className="page-header">
        <div className="page-header__inner">
          <div>
            <h1 className="page-title">{title}</h1>
            <p className="page-subtitle">{subtitle}</p>
            {meta ? <div className="page-meta">{meta}</div> : null}
          </div>
          {actions}
        </div>
      </header>
      <main className="page-body">
        <div className="page-body__inner">{children}</div>
      </main>
      {footer ? (
        <footer className="page-footer">
          <div className="page-footer__inner">{footer}</div>
        </footer>
      ) : null}
    </div>
  );
}
