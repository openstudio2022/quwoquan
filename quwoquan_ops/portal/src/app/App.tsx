import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { portalMenu } from '../generated/control-plane/portalMenu.generated.js';
import { AuditPage } from '../domains/overview/AuditPage.js';
import { OverviewDashboardPage } from '../domains/overview/OverviewDashboardPage.js';
import { PlatformConfigPage } from '../domains/platform/PlatformConfigPage.js';
import { PlatformDomainOnboardingPage } from '../domains/platform/PlatformDomainOnboardingPage.js';
import { PlatformObservabilityPage } from '../domains/platform/PlatformObservabilityPage.js';
import { PlatformRolloutPage } from '../domains/platform/PlatformRolloutPage.js';
import { PlatformServiceCatalogPage } from '../domains/platform/PlatformServiceCatalogPage.js';
import { EntityHomepageGovernancePage } from '../domains/product/EntityHomepageGovernancePage.js';
import { GovernancePage } from '../domains/product/GovernancePage.js';
import { ProductDashboardPage } from '../domains/product/ProductDashboardPage.js';
import { ProductL1L4MetricsPage } from '../domains/product/ProductL1L4MetricsPage.js';
import { RecommendationPage } from '../domains/product/RecommendationPage.js';
import { PortalScopeProvider } from '../shared/layout/PortalContext.js';
import { PortalLayout } from '../shared/layout/PortalLayout.js';
import { PortalLoginPage } from '../shared/auth/PortalLoginPage.js';
import { PortalAuthProvider, usePortalAuth } from '../shared/auth/portalAuth.js';

function portalRoutePath(menuId: string): string {
  const menu = portalMenu.menus.find((item) => item.menu_id === menuId);
  if (!menu) {
    throw new Error(`generated portal route is missing: ${menuId}`);
  }
  return menu.route_path;
}

function AuthenticatedRoutes() {
  const { loading, token } = usePortalAuth();
  if (loading) {
    return <PortalLoginPage />;
  }
  if (!token) {
    return <PortalLoginPage />;
  }
  return (
    <PortalScopeProvider>
      <Routes>
        <Route element={<PortalLayout />}>
          <Route path="/" element={<OverviewDashboardPage />} />
          <Route path="/platform" element={<Navigate to="/platform/catalog" replace />} />
          <Route path="/platform/catalog" element={<PlatformServiceCatalogPage />} />
          <Route path="/platform/onboarding" element={<PlatformDomainOnboardingPage />} />
          <Route path="/platform/config" element={<Navigate to="/platform/config/snapshot" replace />} />
          <Route path="/platform/config/snapshot" element={<PlatformConfigPage />} />
          <Route path="/platform/config/drift" element={<PlatformConfigPage />} />
          <Route path="/platform/rollout" element={<PlatformRolloutPage />} />
          <Route path="/platform/observability" element={<PlatformObservabilityPage />} />
          <Route path="/product" element={<Navigate to="/product/dashboard" replace />} />
          <Route path="/product/dashboard" element={<ProductDashboardPage />} />
          <Route path="/product/l1-l4" element={<Navigate to="/product/l1-l4/environment" replace />} />
          <Route path="/product/l1-l4/environment" element={<ProductL1L4MetricsPage />} />
          <Route path="/product/l1-l4/service" element={<ProductL1L4MetricsPage />} />
          <Route path="/product/governance" element={<GovernancePage />} />
          <Route
            path={portalRoutePath('entity-homepage-governance')}
            element={<EntityHomepageGovernancePage />}
          />
          <Route path="/product/recommendation" element={<RecommendationPage />} />
          <Route path="/audit" element={<AuditPage />} />
        </Route>
      </Routes>
    </PortalScopeProvider>
  );
}

export function App() {
  return (
    <PortalAuthProvider>
      <BrowserRouter>
        <AuthenticatedRoutes />
      </BrowserRouter>
    </PortalAuthProvider>
  );
}
