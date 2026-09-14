import { PortalFrame } from '@ops-ui';
import { Boxes, LayoutDashboard, Search } from 'lucide-react';
import { NavLink, Outlet } from 'react-router-dom';

export function Layout() {
  const sidebar = <>
    <div className="portal-brand"><div className="portal-brand__logo"><Boxes /></div><div><div className="portal-brand__title">内容池工作台</div><div className="portal-brand__subtitle">仅本机 · 离线复核</div></div></div>
    <nav className="portal-nav">
      <NavLink end to="/" className={({ isActive }) => `portal-nav-item ${isActive ? 'active' : ''}`}><span><LayoutDashboard size={18} />总览</span></NavLink>
      <NavLink to="/explore" className={({ isActive }) => `portal-nav-item ${isActive ? 'active' : ''}`}><span><Search size={18} />探索内容</span></NavLink>
    </nav>
    <div className="local-note">Canonical 发布根只读。候选与人工结论不代表已入池。</div>
  </>;
  const topbar = <><strong>Data Portal</strong><span className="badge badge--neutral">loopback only</span></>;
  return <PortalFrame sidebar={sidebar} topbar={topbar}><Outlet /></PortalFrame>;
}
