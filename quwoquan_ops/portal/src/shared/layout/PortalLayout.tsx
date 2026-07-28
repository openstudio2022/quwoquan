import { ChevronDown, LogOut } from 'lucide-react';
import { useMemo } from 'react';
import { NavLink, Outlet } from 'react-router-dom';

import { portalMenu } from '../../generated/control-plane/portalMenu.generated.js';
import { portalShell } from '../../generated/control-plane/portalShell.generated.js';
import { getPortalIcon } from '../navigation/icons.js';
import { usePortalScope } from './PortalContext.js';
import { usePortalAuth } from '../auth/portalAuth.js';

export function buildMenuGroups(hasPermission: (permission: string) => boolean) {
  const visibleMenus = portalMenu.menus.filter((item) =>
    hasPermission(item.permission_scope),
  );
  const visibleMenuIds = new Set(visibleMenus.map((item) => item.menu_id));
  const roots = visibleMenus
    .filter(
      (item) =>
        !('parent_menu_id' in item) ||
        !item.parent_menu_id ||
        !visibleMenuIds.has(item.parent_menu_id),
    )
    .sort((a, b) => a.order - b.order);

  return roots.map((root) => ({
    root,
    children: visibleMenus
      .filter((item) => 'parent_menu_id' in item && item.parent_menu_id === root.menu_id)
      .sort((a, b) => a.order - b.order)
      .map((child) => ({
        child,
        grandchildren: visibleMenus
          .filter((item) => 'parent_menu_id' in item && item.parent_menu_id === child.menu_id)
          .sort((a, b) => a.order - b.order),
      })),
  }));
}

export function PortalLayout() {
  const { environment, setEnvironment } = usePortalScope();
  const { claims, hasPermission, logout } = usePortalAuth();
  const menuGroups = useMemo(() => buildMenuGroups(hasPermission), [hasPermission]);

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
                    {children.map(({ child, grandchildren }) => {
                      const ChildIcon = getPortalIcon(child.icon);
                      return (
                        <div key={child.menu_id} className="portal-subnav-group">
                          <NavLink
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
                          {grandchildren.length ? (
                            <div className="portal-subnav-list">
                              {grandchildren.map((grandchild) => {
                                const GrandchildIcon = getPortalIcon(grandchild.icon);
                                return (
                                  <NavLink
                                    key={grandchild.menu_id}
                                    to={grandchild.route_path}
                                    className={({ isActive }) =>
                                      `portal-nav-item portal-nav-item--nested ${isActive ? 'portal-nav-item--active' : ''}`
                                    }
                                  >
                                    <span className="portal-nav-item__left">
                                      <GrandchildIcon size={16} />
                                      <span>{grandchild.label}</span>
                                    </span>
                                    <span className="portal-nav-item__badge">{grandchild.object_types.length}</span>
                                  </NavLink>
                                );
                              })}
                            </div>
                          ) : null}
                        </div>
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
              <strong>{environment}</strong>
              <ChevronDown size={16} />
            </div>
          </div>
          <div className="portal-topbar__right">
            <select
              className="portal-select"
              value={environment}
              onChange={(event) => setEnvironment(event.target.value)}
            >
              {portalShell.supported_environments.map((environment) => (
                <option key={environment} value={environment}>
                  {environment}
                </option>
              ))}
            </select>
            <button type="button" className="portal-button portal-button--ghost" onClick={logout} title="退出登录">
              <LogOut size={16} />
              {claims.name || claims.email || claims.sub || 'operator'}
            </button>
          </div>
        </header>
        <Outlet />
      </div>
    </div>
  );
}
