export interface ExperimentItem {
  id: string;
  name: string;
  enabled: boolean;
  policyVersion: string;
  buckets: Array<{ name: string; weightPct: number }>;
  bucketStats: Record<string, number>;
  assignedSubjects: number;
}

export interface ReleaseItem {
  releaseId: string;
  service: string;
  configPath: string;
  grayStages: number[];
  releaseState: string;
}

export interface ReportItem {
  id: string;
  reporterId: string;
  targetType: string;
  targetId: string;
  reason: string;
  description?: string;
  status: string;
  reviewerId?: string;
  resolution?: string;
  createdAt: string;
  resolvedAt?: string;
}

export interface ServiceCatalogItem {
  id: string;
  service: string;
  plane: string;
  owner: string;
  health: string;
  summary: string;
}

export interface OnboardingDomainItem {
  domain: string;
  display_name: string;
  template_role: string;
  rollout_group: string;
  acceptance_status: string;
  metadata_paths: string[];
  service_names: string[];
  control_planes: Record<string, { enabled: boolean; object_types: string[]; config_prefixes: string[] }>;
  minimum_package: {
    metadata_files: string[];
    codegen_targets: string[];
    test_evidence: Record<string, string[]>;
  };
  deployment: {
    plane_binding_domain: string;
    plane_binding_source: string;
    legacy_binding_source: string;
  };
  replication: {
    source_template: string;
    next_copy_targets: string[];
    copy_notes: string[];
  };
  blocking_gaps: string[];
}

export interface PlaneBindingItem {
  id: string;
  env: string;
  process: string;
  domain: string;
  planes: string[];
}

export interface EnvironmentTopologyItem {
  id: string;
  env: string;
  process: string;
  domains: string[];
}

export interface DependencyItem {
  id: string;
  dependency: string;
  profile: string;
  latency: string;
  status: string;
}

export interface CapacityProfileItem {
  id: string;
  plane: string;
  resourceClass: string;
  scaling: string;
  splitTrigger: string;
}

export interface GovernanceBindingItem {
  id: string;
  title: string;
  subtitle: string;
  status: string;
}

export interface GovernanceTemplateItem {
  id: string;
  title: string;
  summary: string;
  status: string;
}

export interface GateRuleItem {
  id: string;
  rule: string;
  stage: string;
  status: string;
  summary: string;
}

export interface RunbookItem {
  id: string;
  title: string;
  subtitle: string;
  status: string;
  lastRunAt?: string;
}

export interface PlatformAuditItem {
  auditId: string;
  objectType: string;
  objectId: string;
  action: string;
  dangerLevel: string;
  actor: string;
  environment: string;
  requestId: string;
  traceId: string;
  workflowRef?: string;
  rollbackToken?: string;
  at: string;
}

export interface PlatformApprovalItem {
  objectType: string;
  objectId: string;
  mode: string;
  actor: string;
  decision: string;
  at: string;
}

export interface PlatformProjectionSummary {
  approvalCount: number;
  auditCount: number;
  runbookCount: number;
  releaseServices: string[];
}

export interface SLOPolicyItem {
  id: string;
  service: string;
  objective: string;
  window: string;
  status: string;
}

export interface AlertTemplateItem {
  id: string;
  title: string;
  severity: string;
  status: string;
}

export interface DashboardCardItem {
  id: string;
  title: string;
  summary: string;
}

export interface ModerationCaseItem {
  id: string;
  targetType: string;
  targetId: string;
  reason: string;
  status: string;
  assignedQueue: string;
  evidenceRefs: string[];
  updatedAt: string;
  resolution?: string;
}

export interface RecoveryCaseItem {
  id: string;
  userId: string;
  status: string;
  evidenceRefs: string[];
  updatedAt: string;
  decision?: string;
}

export interface AppealCaseItem {
  id: string;
  targetType: string;
  targetId: string;
  status: string;
  evidenceRefs: string[];
  updatedAt: string;
  decision?: string;
}

export interface RecommendationPolicyItem {
  id: string;
  name: string;
  status: string;
  policyVersion: string;
  guardrailSnapshot: Record<string, unknown>;
  updatedAt: string;
}

export interface WorkflowItem {
  objectType: string;
  objectId: string;
  workflowId: string;
  state: string;
  updatedAt: string;
}

export interface ProductApprovalItem {
  objectType: string;
  objectId: string;
  mode: string;
  actor: string;
  decision: string;
  at: string;
}

export interface ProductProjectionSummary {
  workflowCount: number;
  approvalCount: number;
  auditCount: number;
  pendingDualReview: number;
  activeObjectTypes: string[];
}

function envBaseUrl(key: 'VITE_PRODUCT_OPS_BASE_URL' | 'VITE_PLATFORM_OPS_BASE_URL' | 'VITE_CONTENT_SERVICE_BASE_URL') {
  const importMetaEnv = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env;
  const processEnv = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env;
  return (importMetaEnv?.[key] ?? processEnv?.[key] ?? '').trim();
}

async function fetchJSON<T>(baseUrl: string, path: string): Promise<T> {
  if (!baseUrl) {
    throw new Error('base url not configured');
  }
  const response = await fetch(`${baseUrl}${path}`);
  if (!response.ok) {
    throw new Error(`request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchExperiments(): Promise<ExperimentItem[]> {
  const payload = await fetchJSON<{ items: ExperimentItem[] }>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    '/v1/control-plane/product/experiments',
  );
  return payload.items;
}

export async function fetchReleases(): Promise<ReleaseItem[]> {
  const payload = await fetchJSON<{ items: ReleaseItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/v1/control-plane/platform/releases',
  );
  return payload.items;
}

export async function fetchReports(): Promise<ReportItem[]> {
  const payload = await fetchJSON<{ items: ReportItem[] }>(
    envBaseUrl('VITE_CONTENT_SERVICE_BASE_URL'),
    '/v1/content/reports?limit=10',
  );
  return payload.items;
}

export async function fetchServiceCatalog(): Promise<ServiceCatalogItem[]> {
  const payload = await fetchJSON<{ items: ServiceCatalogItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/v1/control-plane/platform/catalog/services',
  );
  return payload.items;
}

export async function fetchOnboardingDomains(): Promise<OnboardingDomainItem[]> {
  const payload = await fetchJSON<{ items: OnboardingDomainItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/v1/control-plane/platform/onboarding/domains',
  );
  return payload.items;
}

export async function fetchPlaneBindings(): Promise<PlaneBindingItem[]> {
  const payload = await fetchJSON<{ items: PlaneBindingItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/v1/control-plane/platform/topology/planes',
  );
  return payload.items;
}

export async function fetchEnvironmentTopologies(): Promise<EnvironmentTopologyItem[]> {
  const payload = await fetchJSON<{ items: EnvironmentTopologyItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/v1/control-plane/platform/topology/environments',
  );
  return payload.items;
}

export async function fetchDependencies(): Promise<DependencyItem[]> {
  const payload = await fetchJSON<{ items: DependencyItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/v1/control-plane/platform/topology/dependencies',
  );
  return payload.items;
}

export async function fetchCapacityProfiles(): Promise<CapacityProfileItem[]> {
  const payload = await fetchJSON<{ items: CapacityProfileItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/v1/control-plane/platform/topology/capacity',
  );
  return payload.items;
}

export async function fetchGovernanceBindings(): Promise<GovernanceBindingItem[]> {
  const payload = await fetchJSON<{ items: GovernanceBindingItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/v1/control-plane/platform/governance/bindings',
  );
  return payload.items;
}

export async function fetchGovernanceTemplates(): Promise<GovernanceTemplateItem[]> {
  const payload = await fetchJSON<{ items: GovernanceTemplateItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/v1/control-plane/platform/governance/templates',
  );
  return payload.items;
}

export async function fetchGateRules(): Promise<GateRuleItem[]> {
  const payload = await fetchJSON<{ items: GateRuleItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/v1/control-plane/platform/gates',
  );
  return payload.items;
}

export async function fetchRunbooks(): Promise<RunbookItem[]> {
  const payload = await fetchJSON<{ items: RunbookItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/v1/control-plane/platform/runbooks',
  );
  return payload.items;
}

export async function fetchPlatformAudits(): Promise<PlatformAuditItem[]> {
  const payload = await fetchJSON<{ items: PlatformAuditItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/v1/control-plane/platform/audits',
  );
  return payload.items;
}

export async function fetchPlatformApprovals(): Promise<PlatformApprovalItem[]> {
  const payload = await fetchJSON<{ items: PlatformApprovalItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/v1/control-plane/platform/approvals',
  );
  return payload.items;
}

export async function fetchPlatformProjectionSummary(): Promise<PlatformProjectionSummary> {
  return fetchJSON<PlatformProjectionSummary>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/v1/control-plane/platform/projections/summary',
  );
}

export async function fetchSLOPolicies(): Promise<SLOPolicyItem[]> {
  const payload = await fetchJSON<{ items: SLOPolicyItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/v1/control-plane/platform/observability/slos',
  );
  return payload.items;
}

export async function fetchAlertTemplates(): Promise<AlertTemplateItem[]> {
  const payload = await fetchJSON<{ items: AlertTemplateItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/v1/control-plane/platform/observability/alerts',
  );
  return payload.items;
}

export async function fetchDashboardCards(): Promise<DashboardCardItem[]> {
  const payload = await fetchJSON<{ items: DashboardCardItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/v1/control-plane/platform/observability/dashboards/cards',
  );
  return payload.items;
}

export async function fetchModerationCases(): Promise<ModerationCaseItem[]> {
  const payload = await fetchJSON<{ items: ModerationCaseItem[] }>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    '/v1/control-plane/product/moderation/cases',
  );
  return payload.items;
}

export async function fetchRecoveryCases(): Promise<RecoveryCaseItem[]> {
  const payload = await fetchJSON<{ items: RecoveryCaseItem[] }>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    '/v1/control-plane/product/recovery/cases',
  );
  return payload.items;
}

export async function fetchAppealCases(): Promise<AppealCaseItem[]> {
  const payload = await fetchJSON<{ items: AppealCaseItem[] }>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    '/v1/control-plane/product/appeal/cases',
  );
  return payload.items;
}

export async function fetchRecommendationPolicies(): Promise<RecommendationPolicyItem[]> {
  const payload = await fetchJSON<{ items: RecommendationPolicyItem[] }>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    '/v1/control-plane/product/recommendation/policies',
  );
  return payload.items;
}

export async function fetchProductWorkflows(): Promise<WorkflowItem[]> {
  const payload = await fetchJSON<{ items: WorkflowItem[] }>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    '/v1/control-plane/product/workflows',
  );
  return payload.items;
}

export async function fetchProductApprovals(): Promise<ProductApprovalItem[]> {
  const payload = await fetchJSON<{ items: ProductApprovalItem[] }>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    '/v1/control-plane/product/approvals',
  );
  return payload.items;
}

export async function fetchProductProjectionSummary(): Promise<ProductProjectionSummary> {
  return fetchJSON<ProductProjectionSummary>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    '/v1/control-plane/product/projections/summary',
  );
}
