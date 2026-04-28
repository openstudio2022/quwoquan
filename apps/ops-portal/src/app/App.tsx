import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { AuditPage } from '../domains/overview/AuditPage.js';
import { OverviewDashboardPage } from '../domains/overview/OverviewDashboardPage.js';
import { SettingsPage } from '../domains/overview/SettingsPage.js';
import { PlatformDependencyPage } from '../domains/platform/PlatformDependencyPage.js';
import { PlatformConfigPage } from '../domains/platform/PlatformConfigPage.js';
import { PlatformDomainOnboardingPage } from '../domains/platform/PlatformDomainOnboardingPage.js';
import { PlatformGatePage } from '../domains/platform/PlatformGatePage.js';
import { PlatformGovernancePage } from '../domains/platform/PlatformGovernancePage.js';
import { PlatformObservabilityPage } from '../domains/platform/PlatformObservabilityPage.js';
import { PlatformRolloutPage } from '../domains/platform/PlatformRolloutPage.js';
import { PlatformRunbookPage } from '../domains/platform/PlatformRunbookPage.js';
import { PlatformServiceCatalogPage } from '../domains/platform/PlatformServiceCatalogPage.js';
import { ExperimentsPage } from '../domains/product/ExperimentsPage.js';
import { GovernancePage } from '../domains/product/GovernancePage.js';
import { ProductDashboardPage } from '../domains/product/ProductDashboardPage.js';
import { RecommendationPage } from '../domains/product/RecommendationPage.js';
import { SegmentsPage } from '../domains/product/SegmentsPage.js';
import { PortalLayout } from '../shared/layout/PortalLayout.js';

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
