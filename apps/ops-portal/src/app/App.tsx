import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { AuditPage } from '../domains/overview/AuditPage';
import { OverviewDashboardPage } from '../domains/overview/OverviewDashboardPage';
import { SettingsPage } from '../domains/overview/SettingsPage';
import { PlatformDependencyPage } from '../domains/platform/PlatformDependencyPage';
import { PlatformConfigPage } from '../domains/platform/PlatformConfigPage';
import { PlatformDomainOnboardingPage } from '../domains/platform/PlatformDomainOnboardingPage';
import { PlatformGatePage } from '../domains/platform/PlatformGatePage';
import { PlatformGovernancePage } from '../domains/platform/PlatformGovernancePage';
import { PlatformObservabilityPage } from '../domains/platform/PlatformObservabilityPage';
import { PlatformRolloutPage } from '../domains/platform/PlatformRolloutPage';
import { PlatformRunbookPage } from '../domains/platform/PlatformRunbookPage';
import { PlatformServiceCatalogPage } from '../domains/platform/PlatformServiceCatalogPage';
import { ExperimentsPage } from '../domains/product/ExperimentsPage';
import { GovernancePage } from '../domains/product/GovernancePage';
import { ProductDashboardPage } from '../domains/product/ProductDashboardPage';
import { RecommendationPage } from '../domains/product/RecommendationPage';
import { SegmentsPage } from '../domains/product/SegmentsPage';
import { PortalLayout } from '../shared/layout/PortalLayout';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<PortalLayout />}>
          <Route path="/" element={<OverviewDashboardPage />} />
          <Route path="/platform" element={<Navigate to="/platform/catalog" replace />} />
          <Route path="/platform/catalog" element={<PlatformServiceCatalogPage />} />
          <Route path="/platform/onboarding" element={<PlatformDomainOnboardingPage />} />
          <Route path="/platform/config" element={<PlatformConfigPage />} />
          <Route path="/platform/governance" element={<PlatformGovernancePage />} />
          <Route path="/platform/rollout" element={<PlatformRolloutPage />} />
          <Route path="/platform/dependency" element={<PlatformDependencyPage />} />
          <Route path="/platform/observability" element={<PlatformObservabilityPage />} />
          <Route path="/platform/runbook" element={<PlatformRunbookPage />} />
          <Route path="/platform/gates" element={<PlatformGatePage />} />
          <Route path="/product" element={<Navigate to="/product/dashboard" replace />} />
          <Route path="/product/dashboard" element={<ProductDashboardPage />} />
          <Route path="/product/governance" element={<GovernancePage />} />
          <Route path="/product/recommendation" element={<RecommendationPage />} />
          <Route path="/product/experiments" element={<ExperimentsPage />} />
          <Route path="/product/segments" element={<SegmentsPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
