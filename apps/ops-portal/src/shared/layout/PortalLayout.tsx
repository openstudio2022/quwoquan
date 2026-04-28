import { Bell, ChevronDown, Search } from 'lucide-react';
import { NavLink, Outlet } from 'react-router-dom';

import { portalMenu } from '../../generated/control-plane/portalMenu.generated.js';
import { portalShell } from '../../generated/control-plane/portalShell.generated.js';
import { getPortalIcon } from '../navigation/icons.js';

function buildMenuGroups() {
  const roots = [...portalMenu.menus]
    .filter((item) => !('parent_menu_id' in item) || !item.parent_menu_id)
    .sort((a, b) => a.order - b.order);

  return roots.map((root) => ({
    root,
    children: portalMenu.menus
      .filter((item) => 'parent_menu_id' in item && item.parent_menu_id === root.menu_id)
      .sort((a, b) => a.order - b.order),
  }));
}

const menuGroups = buildMenuGroups();

export function PortalLayout() {
  return (
    <div className="portal-root">
      <aside className="portal-sidebar">
        <div className="portal-brand">
          <div className="portal-brand__logo">Q</div>
          <div>
            <div className="portal-brand__title">{portalShell.title}</div>
            <div className="portal-brand__subtitle">{portalShell.portal_id}</div>
          </div>
        </div>

        <nav className="portal-nav">
          {menuGroups.map(({ root, children }) => {
            const RootIcon = getPortalIcon(root.icon);
            return (
              <div className="portal-nav-group" key={root.menu_id}>
                <NavLink
                  to={root.route_path}
                  className={({ isActive }) =>
                    `portal-nav-item ${isActive ? 'portal-nav-item--active' : ''}`
                  }
                >
                  <span className="portal-nav-item__left">
                    <RootIcon size={18} />
                    <span>{root.label}</span>
                  </span>
                  {!children.length ? <span className="portal-nav-item__badge">{root.domain}</span> : null}
                </NavLink>

                {children.length ? (
                  <>
                    <div className="portal-nav-group__title">{root.label}</div>
                    {children.map((child) => {
                      const ChildIcon = getPortalIcon(child.icon);
                      return (
                        <NavLink
                          key={child.menu_id}
                          to={child.route_path}
                          className={({ isActive }) =>
                            `portal-nav-item ${isActive ? 'portal-nav-item--active' : ''}`
                          }
                        >
                          <span className="portal-nav-item__left">
                            <ChildIcon size={18} />
                            <span>{child.label}</span>
                          </span>
                          <span className="portal-nav-item__badge">{child.object_types.length}</span>
                        </NavLink>
                      );
                    })}
                  </>
                ) : null}
              </div>
            );
          })}
        </nav>
      </aside>

      <div className="portal-content">
        <header className="portal-topbar">
          <div className="portal-topbar__left">
            <div className="portal-pill">
              环境
              <strong>{portalShell.default_environment}</strong>
              <ChevronDown size={16} />
            </div>
            <div className="portal-pill">
              工作域
              <strong>{portalShell.default_domain}</strong>
            </div>
            <div className="portal-search">
              <Search size={16} color="#6B7280" />
              <input placeholder={portalShell.global_search.placeholder} />
            </div>
          </div>
          <div className="portal-topbar__right">
            <select className="portal-select" defaultValue={portalShell.default_environment}>
              {portalShell.supported_environments.map((environment) => (
                <option key={environment} value={environment}>
                  {environment}
                </option>
              ))}
            </select>
            <div className="portal-pill">
              <Bell size={16} />
              {portalShell.notification_channels.length} 类通知
            </div>
          </div>
        </header>
        <Outlet />
      </div>
    </div>
  );
}
