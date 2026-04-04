function envBaseUrl(key) {
    const importMetaEnv = import.meta.env;
    const processEnv = globalThis.process?.env;
    return (importMetaEnv?.[key] ?? processEnv?.[key] ?? '').trim();
}
async function fetchJSON(baseUrl, path) {
    if (!baseUrl) {
        throw new Error('base url not configured');
    }
    const response = await fetch(`${baseUrl}${path}`);
    if (!response.ok) {
        throw new Error(`request failed: ${response.status}`);
    }
    return (await response.json());
}
function withQuery(path, query = {}) {
    const params = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => {
        if (value === undefined || value === null || value === '') {
            return;
        }
        params.set(key, String(value));
    });
    const encoded = params.toString();
    return encoded ? `${path}?${encoded}` : path;
}
export async function fetchExperiments() {
    const payload = await fetchJSON(envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'), '/v1/control-plane/product/experiments');
    return payload.items;
}
export async function fetchReleases() {
    const payload = await fetchJSON(envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'), '/v1/control-plane/platform/releases');
    return payload.items;
}
export async function fetchReports() {
    const payload = await fetchJSON(envBaseUrl('VITE_CONTENT_SERVICE_BASE_URL'), '/v1/content/reports?limit=10');
    return payload.items;
}
export async function fetchServiceCatalog() {
    const payload = await fetchJSON(envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'), '/v1/control-plane/platform/catalog/services');
    return payload.items;
}
export async function fetchOnboardingDomains() {
    const payload = await fetchJSON(envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'), '/v1/control-plane/platform/onboarding/domains');
    return payload.items;
}
export async function fetchPlaneBindings() {
    const payload = await fetchJSON(envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'), '/v1/control-plane/platform/topology/planes');
    return payload.items;
}
export async function fetchEnvironmentTopologies() {
    const payload = await fetchJSON(envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'), '/v1/control-plane/platform/topology/environments');
    return payload.items;
}
export async function fetchDependencies() {
    const payload = await fetchJSON(envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'), '/v1/control-plane/platform/topology/dependencies');
    return payload.items;
}
export async function fetchCapacityProfiles() {
    const payload = await fetchJSON(envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'), '/v1/control-plane/platform/topology/capacity');
    return payload.items;
}
export async function fetchGovernanceBindings() {
    const payload = await fetchJSON(envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'), '/v1/control-plane/platform/governance/bindings');
    return payload.items;
}
export async function fetchGovernanceTemplates() {
    const payload = await fetchJSON(envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'), '/v1/control-plane/platform/governance/templates');
    return payload.items;
}
export async function fetchGateRules() {
    const payload = await fetchJSON(envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'), '/v1/control-plane/platform/gates');
    return payload.items;
}
export async function fetchRunbooks() {
    const payload = await fetchJSON(envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'), '/v1/control-plane/platform/runbooks');
    return payload.items;
}
export async function fetchPlatformAudits() {
    const payload = await fetchJSON(envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'), '/v1/control-plane/platform/audits');
    return payload.items;
}
export async function fetchPlatformApprovals() {
    const payload = await fetchJSON(envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'), '/v1/control-plane/platform/approvals');
    return payload.items;
}
export async function fetchPlatformProjectionSummary() {
    return fetchJSON(envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'), '/v1/control-plane/platform/projections/summary');
}
export async function fetchSLOPolicies() {
    const payload = await fetchJSON(envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'), '/v1/control-plane/platform/observability/slos');
    return payload.items;
}
export async function fetchAlertTemplates() {
    const payload = await fetchJSON(envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'), '/v1/control-plane/platform/observability/alerts');
    return payload.items;
}
export async function fetchDashboardCards() {
    const payload = await fetchJSON(envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'), '/v1/control-plane/platform/observability/dashboards/cards');
    return payload.items;
}
export async function fetchModerationCases() {
    const payload = await fetchJSON(envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'), '/v1/control-plane/product/moderation/cases');
    return payload.items;
}
export async function fetchRecoveryCases() {
    const payload = await fetchJSON(envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'), '/v1/control-plane/product/recovery/cases');
    return payload.items;
}
export async function fetchAppealCases() {
    const payload = await fetchJSON(envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'), '/v1/control-plane/product/appeal/cases');
    return payload.items;
}
export async function fetchRecommendationPolicies() {
    const payload = await fetchJSON(envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'), '/v1/control-plane/product/recommendation/policies');
    return payload.items;
}
export async function fetchProductWorkflows() {
    const payload = await fetchJSON(envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'), '/v1/control-plane/product/workflows');
    return payload.items;
}
export async function fetchProductApprovals() {
    const payload = await fetchJSON(envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'), '/v1/control-plane/product/approvals');
    return payload.items;
}
export async function fetchProductProjectionSummary() {
    return fetchJSON(envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'), '/v1/control-plane/product/projections/summary');
}
export async function fetchProductEventSummary(query = {}) {
    return fetchJSON(envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'), withQuery('/v1/ops/events/summary', query));
}
export async function fetchProductEventDrilldown(query = {}) {
    return fetchJSON(envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'), withQuery('/v1/ops/events/drilldown', query));
}
