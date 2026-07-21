import {
  RuntimeError,
  fallbackRuntimeErrorResponse,
  isRuntimeErrorResponse,
} from "../runtime/errors/runtimeError.js";
import { productControlPlane } from "../../generated/control-plane/productControlPlane.generated.js";
import { eventCatalog } from "../../generated/telemetry/eventCatalog.generated.js";
import { getPortalAccessToken, notifyPortalAuthExpired } from "../auth/portalAuth.js";

export type ProductTelemetryNetworkClass =
  (typeof eventCatalog.network_classes)[number];

export interface ReleaseItem {
  releaseId: string;
  service: string;
  configPath: string;
  grayStages: number[];
  releaseState: string;
  stageState?: string;
  fromConfig?: string;
  toConfig?: string;
  currentStage?: number;
  updatedAt?: string;
  workflowRef?: string;
  rollbackToken?: string;
}

export interface ReportItem {
  id: string;
  version: number;
  targetType: string;
  targetId: string;
  reason: string;
  status: string;
  createdAt: string;
  updatedAt: string;
}

export interface HomepageCandidateItem {
  homepageId: string;
  canonicalEntityId: string;
  title: string;
  subtitle?: string;
  homepageType: string;
  coverUrl?: string;
  city?: string;
  address?: string;
  status: 'candidate' | 'published' | 'offline';
}

export interface HomepageClaimRequestItem {
  claimRequestId: string;
  version: number;
  homepageId: string;
  requesterPersonaId: string;
  claimTier: string;
  businessLicenseUrl?: string;
  contactPhone?: string;
  identityCardFrontUrl?: string;
  identityCardBackUrl?: string;
  note?: string;
  status: 'pending_review' | 'approved' | 'rejected';
  reviewerAccountId?: string;
  reviewNote?: string;
  createdAt: string;
  updatedAt: string;
  reviewedAt?: string;
}

export interface HomepageStatusReportItem {
  reportId: string;
  version: number;
  homepageId: string;
  reporterPersonaId: string;
  reason: string;
  description?: string;
  evidenceUrls?: string[];
  status: 'pending_review' | 'confirmed_offline' | 'dismissed';
  reviewerAccountId?: string;
  reviewNote?: string;
  createdAt: string;
  updatedAt: string;
  reviewedAt?: string;
}

export interface CursorSlice<T> {
  items: T[];
  nextCursor?: string;
}

export interface IntakeHomepageCandidatePayload {
  title: string;
  subtitle?: string;
  homepageType: string;
  canonicalEntityId: string;
  categoryTags?: string[];
  coverUrl?: string;
  address?: string;
  city?: string;
  introductionMarkdown?: string;
}

export interface PostModerationCaseItem {
  id: string;
  version: number;
  postId: string;
  postVersion: number;
  contentDigest: string;
  status: 'pending' | 'reviewed' | 'approved' | 'rejected' | 'superseded';
  reviewerId?: string;
  decisionReason?: string;
  createdAt: string;
  updatedAt: string;
  decidedAt?: string;
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
    current_binding_source: string;
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

export interface RuntimeClusterItem {
  id: string;
  environment: string;
  cluster: string;
  plane: string;
  services: string[];
  status: string;
}

export interface RuntimeServiceItem {
  id: string;
  environment: string;
  cluster: string;
  service: string;
  plane: string;
  instances: number;
  status: string;
}

export interface RuntimeInstanceItem {
  id: string;
  environment: string;
  cluster: string;
  service: string;
  plane: string;
  status: string;
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
  activeAlerts: number;
  releaseServices: string[];
}

// ActiveAlertItem 对齐 platform-ops-service 的 Alertmanager 回流对象：
// firing 由 webhook 建立，acknowledged 由值班人认领，resolved 归档。
export interface ActiveAlertItem {
  id: string;
  fingerprint: string;
  alertName: string;
  severity: string;
  service?: string;
  labels: Record<string, string>;
  annotations: Record<string, string>;
  startsAt?: string;
  endsAt?: string;
  status: string;
  ackedBy?: string;
  ackedAt?: string;
  updatedAt: string;
}

export interface ConfigKeyItem {
  key: string;
  kind: string;
  owner?: string;
  default: unknown;
  scope: string;
  reload: string;
  rollout?: string;
  riskLevel?: string;
  uiEditable: boolean;
}

export interface ConfigSnapshotFile {
  path: string;
  role: string;
  sha256: string;
  content: string;
}

export interface ConfigSnapshotView {
  domain: string;
  service: string;
  environment: string;
  files: ConfigSnapshotFile[];
  releaseVersions: string[];
  mergedSha256?: string;
  snapshotSource: string;
}

export interface ConfigDomainItem {
  domain: string;
  label: string;
  services?: string[];
  description: string;
}

export interface ConfigInstanceReportItem {
  id: string;
  environment: string;
  cluster: string;
  service: string;
  instanceId: string;
  configVersion?: string;
  imageVersion?: string;
  desiredHash?: string;
  effectiveHash?: string;
  inSync: boolean;
  source?: string;
  updatedAt?: string;
  lastError?: string;
}

export interface ConfigInstanceReportSummary {
  inSyncInstances: number;
  outOfSyncInstances: number;
  totalInstances: number;
}

export interface EffectiveConfigValue {
  key: string;
  value: unknown;
  scopeLevel: string;
  scopeId: string;
  sourceLayer: string;
  metadata?: Record<string, unknown>;
}

export interface EffectiveConfigResponse {
  scope: {
    environment?: string;
    cluster?: string;
    service?: string;
  };
  resolvedAt: string;
  effectiveHash: string;
  desiredHash: string;
  values: EffectiveConfigValue[];
  source: string;
}

export interface PlatformTriageServiceDriftItem {
  service: string;
  totalInstances: number;
  inSyncInstances: number;
  outOfSyncInstances: number;
}

export interface PlatformTriageOutOfSyncInstanceItem {
  id: string;
  environment: string;
  cluster: string;
  service: string;
  instanceId: string;
  desiredHash?: string;
  effectiveHash?: string;
  source?: string;
  lastError?: string;
  inSync: boolean;
}

export interface PlatformTriageSummaryResponse {
  scope: Record<string, string>;
  projectionSummary: PlatformProjectionSummary;
  configDrift: ConfigInstanceReportSummary;
  serviceDrift: PlatformTriageServiceDriftItem[];
  outOfSyncInstances: PlatformTriageOutOfSyncInstanceItem[];
  backlogCandidates: ControlPlaneBacklogCandidate[];
  runtimeReady: boolean;
  source: string;
}

export interface ControlPlaneMutationReceipt {
  objectType: string;
  objectId: string;
  intent: string;
  payloadDigest: string;
  idempotencyKey: string;
  committedAt: string;
  replayed: boolean;
}

// PremiumPoolEntryItem 对齐 product-ops-service 全局精选池条目：
// upsert/rollback/takedown 全部真实落库并经 outbox 事件广播给 content-service。
export interface PremiumPoolEntryItem {
  id: string;
  contentId: string;
  scope: string;
  status: string;
  qualityScore: number;
  qualityAdmission: string;
  supplySource?: string;
  sourceTaskId?: string;
  auditId: string;
  rollbackToken: string;
  featuredAt: string;
  expiresAt: string;
  takedownEjected: boolean;
  updatedAt: string;
}

export type PremiumPoolMutationResponse =
  | {
      entry: PremiumPoolEntryItem;
      approvalCount: number;
      approvalState: string;
      pending: boolean;
      payloadDigest: string;
      approverActors: string[];
    }
  | {
      entry: PremiumPoolEntryItem;
      pending: false;
      receipt: ControlPlaneMutationReceipt;
    };

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
  l1l4Cards?: Array<{
    level: string;
    label: string;
    metric: string;
  }>;
}

export interface ProductEventSummary {
  totalCount: number;
  sessionCount: number;
  dimensions: Record<string, Record<string, number>>;
  sourceKind: 'raw_records' | 'hourly_rollup';
  freshness: string;
  generatedThrough?: string;
  lagSeconds?: number;
  actualFrom: string;
  actualTo: string;
}

export interface ProductEventDrilldownItem {
  rowKey: string;
  logType: 'event' | 'error';
  eventType: string;
  sessionId: string;
  pageName: string;
  occurredAt: string;
  deviceManufacturer: string;
  deviceModel: string;
  appVersion: string;
  networkClass: ProductTelemetryNetworkClass;
  durationMs?: number;
  result?: string;
  failReasonCode?: string;
  errorCode?: string;
  operationId?: string;
  httpStatus?: number;
  callStack?: string[];
  tClickToFirstFrameMs?: number;
  tFirstFrameToShellMs?: number;
  tShellToContentMs?: number;
  tClickToContentMs?: number;
  hasError?: boolean;
  journey?: string;
  action?: string;
  ingestedAt: string;
}

export interface ProductEventDrilldown {
  totalCount: number;
  items: ProductEventDrilldownItem[];
  sourceKind: 'raw_records' | 'hourly_rollup';
  freshness: string;
  generatedThrough?: string;
  lagSeconds?: number;
  actualFrom: string;
  actualTo: string;
}

export interface RuntimeLogSummary {
  totalCount: number;
  dimensions: Record<string, Record<string, number>>;
  sourceKind: 'raw_records' | 'hourly_rollup';
  freshness: string;
  generatedThrough?: string;
  lagSeconds?: number;
  actualFrom: string;
  actualTo: string;
}

export interface RuntimeLogDrilldownItem {
  rowKey: string;
  recordId?: string;
  occurredAt: string;
  observedAt: string;
  logKind: 'access' | 'runtime' | 'exception' | 'event' | 'audit';
  severity: 'DEBUG' | 'INFO' | 'WARN' | 'ERROR' | 'FATAL';
  signal: string;
  message: string;
  errorCode?: string;
  fingerprint?: string;
  resource: Record<string, string>;
  correlation?: Record<string, string>;
  attributes?: Record<string, string>;
  ingestedAt: string;
}

export interface RuntimeLogDrilldown {
  totalCount: number;
  items: RuntimeLogDrilldownItem[];
  sourceKind: 'raw_records' | 'hourly_rollup';
  freshness: string;
  generatedThrough?: string;
  lagSeconds?: number;
  actualFrom: string;
  actualTo: string;
}

export interface ControlPlaneBacklogCandidate {
  id: string;
  category: string;
  severity: string;
  title: string;
  summary?: string;
  owner?: string;
  nextAction: string;
  drilldownRoute?: string;
  repairEntry?: string;
  alertId?: string;
  auditRoute?: string;
  evidence?: Record<string, unknown>;
}

export interface ProductEventQuery {
  logType?: 'event' | 'error';
  eventType?: string;
  pageName?: string;
  appVersion?: string;
  networkClass?: ProductTelemetryNetworkClass;
  result?: string;
  errorCode?: string;
  sessionId?: string;
  from?: string;
  to?: string;
  limit?: number;
  revealSession?: boolean;
}

export interface RuntimeLogQuery {
  signal?: string;
  severity?: RuntimeLogDrilldownItem['severity'];
  errorCode?: string;
  fingerprint?: string;
  sourceType?: 'app' | 'service' | 'data' | 'portal';
  service?: string;
  appVersion?: string;
  /** 按用户维度检索（服务端要求 sensitive 权限；与 revealCorrelation 同门）。 */
  actorHash?: string;
  /** 日志文本检索（SLS 全文索引短语匹配 / memory contains）。 */
  messageContains?: string;
  from?: string;
  to?: string;
  limit?: number;
  revealCorrelation?: boolean;
}

export interface RecommendationBehaviorMetricSeries {
  labels: Record<string, string>;
  value: number;
}

export interface RecommendationBehaviorMetrics {
  source: 'recommendation_behavior_by_attribution_total';
  freshness: 'process_realtime';
  series: RecommendationBehaviorMetricSeries[];
}

export interface ControlPlaneScopeQuery {
  env?: string;
  cluster?: string;
  service?: string;
  instance?: string;
  level?: string;
}

export interface ProductMetricItem {
  id: string;
  level: string;
  environment: string;
  cluster?: string;
  service?: string;
  instanceId?: string;
  label: string;
  metric: string;
  value: number;
  unit: string;
  status: string;
  trend: string;
  description: string;
  source?: string;
}

export interface ProductL1L4AlertState {
  id: string;
  level: string;
  metric: string;
  state: string;
  severity: string;
  summary: string;
  value: number;
  threshold: number;
  source: string;
  owner?: string;
  repairEntry?: string;
  alertId?: string;
  auditRoute?: string;
}

export interface ProductL1L4MetricsCoverage {
  totalMetrics: number;
  liveMetrics: number;
  unavailableMetrics: number;
  eventSignals: number;
}

export interface ProductL1L4MetricsResponse {
  scope: Record<string, string>;
  source: string;
  freshness: string;
  window: string;
  coverage: ProductL1L4MetricsCoverage;
  alerts: ProductL1L4AlertState[];
  items: ProductMetricItem[];
}

export interface ProductTriageSummaryResponse {
  projectionSummary: ProductProjectionSummary;
  eventSummary: ProductEventSummary;
  visitSummary: {
    totalVisits: number;
    items: Array<Record<string, unknown>>;
  };
  topEventHotspots: Record<string, Array<{ value: string; count: number }>>;
  recentEvents: ProductEventDrilldownItem[];
  backlogCandidates: ControlPlaneBacklogCandidate[];
  runtimeReady: boolean;
  source: string;
}

function envBaseUrl(
  key:
    | 'VITE_PRODUCT_OPS_BASE_URL'
    | 'VITE_PLATFORM_OPS_BASE_URL'
    | 'VITE_CONTENT_SERVICE_BASE_URL'
    | 'VITE_ENTITY_SERVICE_BASE_URL',
) {
  const importMetaEnv = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env;
  const processEnv = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env;
  return (importMetaEnv?.[key] ?? processEnv?.[key] ?? '').trim();
}

async function fetchJSON<T>(baseUrl: string, path: string): Promise<T> {
  if (!baseUrl) {
    throw new RuntimeError(
      fallbackRuntimeErrorResponse({
        code: "OPS.CONFIG.base_url_missing",
        requestPath: path,
      }),
    );
  }
  let response: Response;
  try {
    const token = getPortalAccessToken();
    response = await fetch(`${baseUrl}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
  } catch (error) {
    throw new RuntimeError(
      fallbackRuntimeErrorResponse({
        code: "OPS.NETWORK.fetch_failed",
        requestPath: path,
        cause: error,
      }),
    );
  }
  if (!response.ok) {
    if (response.status === 401) {
      notifyPortalAuthExpired();
    }
    const text = await response.text();
    let decoded: unknown;
    try {
      decoded = text ? JSON.parse(text) : undefined;
    } catch {
      decoded = undefined;
    }
    throw new RuntimeError(
      isRuntimeErrorResponse(decoded)
        ? decoded
        : fallbackRuntimeErrorResponse({
            code:
              response.status >= 500
                ? "OPS.UNAVAILABLE.control_plane_unavailable"
                : "OPS.NETWORK.request_failed",
            statusCode: response.status,
            requestPath: path,
            requestId: response.headers.get("X-Request-Id") ?? undefined,
            traceId: response.headers.get("X-Trace-Id") ?? undefined,
          }),
    );
  }
  try {
    return (await response.json()) as T;
  } catch (error) {
    throw new RuntimeError(
      fallbackRuntimeErrorResponse({
        code: "OPS.CONTRACT.invalid_json_response",
        statusCode: response.status,
        requestPath: path,
        requestId: response.headers.get("X-Request-Id") ?? undefined,
        traceId: response.headers.get("X-Trace-Id") ?? undefined,
        cause: error,
      }),
    );
  }
}

async function postJSON<T>(baseUrl: string, path: string, payload: unknown): Promise<T> {
  return mutateJSON<T>(baseUrl, 'POST', path, payload);
}

async function mutateJSON<T>(
  baseUrl: string,
  method: 'POST' | 'PATCH',
  path: string,
  payload: unknown,
  extraHeaders: Record<string, string> = {},
): Promise<T> {
  if (!baseUrl) {
    throw new RuntimeError(
      fallbackRuntimeErrorResponse({
        code: "OPS.CONFIG.base_url_missing",
        requestPath: path,
      }),
    );
  }
  let response: Response;
  try {
    const token = getPortalAccessToken();
    response = await fetch(`${baseUrl}${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...extraHeaders,
      },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    throw new RuntimeError(
      fallbackRuntimeErrorResponse({
        code: "OPS.NETWORK.fetch_failed",
        requestPath: path,
        cause: error,
      }),
    );
  }
  if (!response.ok) {
    if (response.status === 401) {
      notifyPortalAuthExpired();
    }
    const text = await response.text();
    let decoded: unknown;
    try {
      decoded = text ? JSON.parse(text) : undefined;
    } catch {
      decoded = undefined;
    }
    throw new RuntimeError(
      isRuntimeErrorResponse(decoded)
        ? decoded
        : fallbackRuntimeErrorResponse({
            code:
              response.status >= 500
                ? "OPS.UNAVAILABLE.control_plane_unavailable"
                : "OPS.NETWORK.request_failed",
            statusCode: response.status,
            requestPath: path,
            requestId: response.headers.get("X-Request-Id") ?? undefined,
            traceId: response.headers.get("X-Trace-Id") ?? undefined,
          }),
    );
  }
  try {
    return (await response.json()) as T;
  } catch (error) {
    throw new RuntimeError(
      fallbackRuntimeErrorResponse({
        code: "OPS.CONTRACT.invalid_json_response",
        statusCode: response.status,
        requestPath: path,
        requestId: response.headers.get("X-Request-Id") ?? undefined,
        traceId: response.headers.get("X-Trace-Id") ?? undefined,
        cause: error,
      }),
    );
  }
}

function withQuery(
  path: string,
  query: Record<string, string | number | boolean | undefined | null> | ProductEventQuery | RuntimeLogQuery | ControlPlaneScopeQuery = {},
): string {
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

function productControlPlaneOperationPath(operation: string): string {
  for (const objectType of productControlPlane.object_types) {
    const matched = objectType.operations.find(
      (candidate) => candidate.operation === operation,
    );
    if (matched) {
      return matched.path;
    }
  }
  throw new RuntimeError(
    fallbackRuntimeErrorResponse({
      code: "OPS.CONTRACT.invalid_response",
      cause: `generated product control-plane operation is missing: ${operation}`,
    }),
  );
}

export async function fetchRuntimeClusters(): Promise<RuntimeClusterItem[]> {
  const payload = await fetchJSON<{ items: RuntimeClusterItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/control-plane/platform/topology/clusters',
  );
  return payload.items;
}

export async function fetchRuntimeServices(): Promise<RuntimeServiceItem[]> {
  const payload = await fetchJSON<{ items: RuntimeServiceItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/control-plane/platform/topology/services',
  );
  return payload.items;
}

export async function fetchRuntimeInstances(): Promise<RuntimeInstanceItem[]> {
  const payload = await fetchJSON<{ items: RuntimeInstanceItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/control-plane/platform/topology/instances',
  );
  return payload.items;
}

export async function fetchReleases(): Promise<ReleaseItem[]> {
  const payload = await fetchJSON<{ items: ReleaseItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/control-plane/platform/releases',
  );
  return payload.items;
}

export async function fetchReports(limit = 50): Promise<ReportItem[]> {
  const payload = await fetchJSON<{ items: ReportItem[] }>(
    envBaseUrl('VITE_CONTENT_SERVICE_BASE_URL'),
    withQuery(productControlPlaneOperationPath('ListReports'), { limit }),
  );
  return payload.items;
}

// 举报处置动作直连 content-service 真实举报聚合（report_queue 对象），
// path 来自 generated control-plane operation；命令幂等由 Idempotency-Key 承载。
export async function beginReportReview(reportId: string): Promise<ReportItem> {
  const path = productControlPlaneOperationPath('BeginReportReview')
    .replace('{reportId}', encodeURIComponent(reportId));
  return mutateJSON<ReportItem>(envBaseUrl('VITE_CONTENT_SERVICE_BASE_URL'), 'POST', path, {}, {
    'Idempotency-Key': `portal-begin-review-${reportId}`,
  });
}

export type ReportResolution = 'warn' | 'delete_content' | 'suspend_user' | 'ban';

export async function resolveReport(reportId: string, resolution: ReportResolution): Promise<ReportItem> {
  const path = productControlPlaneOperationPath('ResolveReport')
    .replace('{reportId}', encodeURIComponent(reportId));
  return mutateJSON<ReportItem>(envBaseUrl('VITE_CONTENT_SERVICE_BASE_URL'), 'PATCH', path, { resolution }, {
    'Idempotency-Key': `portal-resolve-${reportId}-${resolution}`,
  });
}

export async function dismissReport(reportId: string): Promise<ReportItem> {
  const path = productControlPlaneOperationPath('DismissReport')
    .replace('{reportId}', encodeURIComponent(reportId));
  return mutateJSON<ReportItem>(
    envBaseUrl('VITE_CONTENT_SERVICE_BASE_URL'),
    'POST',
    path,
    {},
    { 'Idempotency-Key': `portal-dismiss-report-${reportId}` },
  );
}

export async function fetchHomepageCandidates(
  query: {
    text?: string;
    homepageType?: string;
    city?: string;
    cursor?: string;
    limit?: number;
  } = {},
): Promise<CursorSlice<HomepageCandidateItem>> {
  return fetchJSON<CursorSlice<HomepageCandidateItem>>(
    envBaseUrl('VITE_ENTITY_SERVICE_BASE_URL'),
    withQuery(productControlPlaneOperationPath('ListHomepageCandidates'), {
      query: query.text,
      homepageType: query.homepageType,
      city: query.city,
      cursor: query.cursor,
      limit: query.limit ?? 50,
    }),
  );
}

export async function intakeHomepageCandidate(
  payload: IntakeHomepageCandidatePayload,
): Promise<HomepageCandidateItem> {
  return mutateJSON<HomepageCandidateItem>(
    envBaseUrl('VITE_ENTITY_SERVICE_BASE_URL'),
    'POST',
    productControlPlaneOperationPath('IntakeHomepageCandidate'),
    payload,
    {
      'Idempotency-Key':
        `portal-homepage-intake-${payload.canonicalEntityId}`,
    },
  );
}

export async function publishHomepageCandidate(
  homepageId: string,
): Promise<HomepageCandidateItem> {
  const path = productControlPlaneOperationPath('PublishHomepageCandidate')
    .replace('{homepageId}', encodeURIComponent(homepageId));
  return mutateJSON<HomepageCandidateItem>(
    envBaseUrl('VITE_ENTITY_SERVICE_BASE_URL'),
    'POST',
    path,
    {},
    { 'Idempotency-Key': `portal-homepage-publish-${homepageId}` },
  );
}

export async function fetchHomepageClaimRequests(
  query: {
    homepageId?: string;
    status?: HomepageClaimRequestItem['status'];
    cursor?: string;
    limit?: number;
  } = {},
): Promise<CursorSlice<HomepageClaimRequestItem>> {
  return fetchJSON<CursorSlice<HomepageClaimRequestItem>>(
    envBaseUrl('VITE_ENTITY_SERVICE_BASE_URL'),
    withQuery(productControlPlaneOperationPath('ListHomepageClaimRequests'), {
      homepageId: query.homepageId,
      status: query.status ?? 'pending_review',
      cursor: query.cursor,
      limit: query.limit ?? 50,
    }),
  );
}

export async function reviewHomepageClaimRequest(
  item: HomepageClaimRequestItem,
  status: 'approved' | 'rejected',
  reviewNote: string,
): Promise<HomepageClaimRequestItem> {
  const path = productControlPlaneOperationPath('ReviewHomepageClaimRequest')
    .replace('{homepageId}', encodeURIComponent(item.homepageId))
    .replace('{claimRequestId}', encodeURIComponent(item.claimRequestId));
  return mutateJSON<HomepageClaimRequestItem>(
    envBaseUrl('VITE_ENTITY_SERVICE_BASE_URL'),
    'POST',
    path,
    { status, reviewNote },
    {
      'Idempotency-Key':
        `portal-homepage-claim-${item.claimRequestId}-${item.version}-${status}`,
    },
  );
}

export async function fetchHomepageStatusReports(
  query: {
    homepageId?: string;
    status?: HomepageStatusReportItem['status'];
    cursor?: string;
    limit?: number;
  } = {},
): Promise<CursorSlice<HomepageStatusReportItem>> {
  return fetchJSON<CursorSlice<HomepageStatusReportItem>>(
    envBaseUrl('VITE_ENTITY_SERVICE_BASE_URL'),
    withQuery(productControlPlaneOperationPath('ListHomepageStatusReports'), {
      homepageId: query.homepageId,
      status: query.status ?? 'pending_review',
      cursor: query.cursor,
      limit: query.limit ?? 50,
    }),
  );
}

export async function reviewHomepageStatusReport(
  item: HomepageStatusReportItem,
  status: 'confirmed_offline' | 'dismissed',
  reviewNote: string,
): Promise<HomepageStatusReportItem> {
  const path = productControlPlaneOperationPath('ReviewHomepageStatusReport')
    .replace('{homepageId}', encodeURIComponent(item.homepageId))
    .replace('{reportId}', encodeURIComponent(item.reportId));
  return mutateJSON<HomepageStatusReportItem>(
    envBaseUrl('VITE_ENTITY_SERVICE_BASE_URL'),
    'POST',
    path,
    { status, reviewNote },
    {
      'Idempotency-Key':
        `portal-homepage-report-${item.reportId}-${item.version}-${status}`,
    },
  );
}

export async function fetchCurrentPostModerationCase(
  postId: string,
): Promise<PostModerationCaseItem> {
  const path = productControlPlaneOperationPath('GetCurrentPostModerationCase')
    .replace('{postId}', encodeURIComponent(postId));
  return fetchJSON<PostModerationCaseItem>(
    envBaseUrl('VITE_CONTENT_SERVICE_BASE_URL'),
    path,
  );
}

export async function reviewPostModerationCase(
  item: PostModerationCaseItem,
): Promise<PostModerationCaseItem> {
  const path = productControlPlaneOperationPath('ReviewPostModerationCase')
    .replace('{postId}', encodeURIComponent(item.postId));
  return mutateJSON<PostModerationCaseItem>(
    envBaseUrl('VITE_CONTENT_SERVICE_BASE_URL'),
    'POST',
    path,
    { caseId: item.id },
    { 'Idempotency-Key': `portal-review-moderation-${item.id}-${item.version}` },
  );
}

export async function decidePostModerationCase(
  item: PostModerationCaseItem,
  decision: 'approved' | 'rejected',
  decisionReason: string,
): Promise<PostModerationCaseItem> {
  const path = productControlPlaneOperationPath('DecidePostModeration')
    .replace('{postId}', encodeURIComponent(item.postId));
  return mutateJSON<PostModerationCaseItem>(
    envBaseUrl('VITE_CONTENT_SERVICE_BASE_URL'),
    'POST',
    path,
    { caseId: item.id, decision, decisionReason },
    {
      'Idempotency-Key':
        `portal-decide-moderation-${item.id}-${item.version}-${decision}`,
    },
  );
}

export async function fetchServiceCatalog(): Promise<ServiceCatalogItem[]> {
  const payload = await fetchJSON<{ items: ServiceCatalogItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/control-plane/platform/catalog/services',
  );
  return payload.items;
}

export async function fetchOnboardingDomains(): Promise<OnboardingDomainItem[]> {
  const payload = await fetchJSON<{ items: OnboardingDomainItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/control-plane/platform/onboarding/domains',
  );
  return payload.items;
}

export async function fetchPlaneBindings(): Promise<PlaneBindingItem[]> {
  const payload = await fetchJSON<{ items: PlaneBindingItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/control-plane/platform/topology/planes',
  );
  return payload.items;
}

export async function fetchPlatformAudits(): Promise<PlatformAuditItem[]> {
  const payload = await fetchJSON<{ items: PlatformAuditItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/control-plane/platform/audits',
  );
  return payload.items;
}

export async function fetchPlatformApprovals(): Promise<PlatformApprovalItem[]> {
  const payload = await fetchJSON<{ items: PlatformApprovalItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/control-plane/platform/approvals',
  );
  return payload.items;
}

export async function fetchPlatformProjectionSummary(): Promise<PlatformProjectionSummary> {
  return fetchJSON<PlatformProjectionSummary>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/control-plane/platform/projections/summary',
  );
}

export async function fetchActiveAlerts(status?: string): Promise<ActiveAlertItem[]> {
  const payload = await fetchJSON<{ items: ActiveAlertItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    withQuery('/control-plane/platform/alerts/active', { status }),
  );
  return payload.items;
}

export async function ackAlert(fingerprint: string): Promise<ActiveAlertItem> {
  return postJSON<ActiveAlertItem>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    `/control-plane/platform/alerts/${encodeURIComponent(fingerprint)}:ack`,
    {},
  );
}

export async function fetchPlatformConfigKeys(): Promise<ConfigKeyItem[]> {
  const payload = await fetchJSON<{ items: ConfigKeyItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/control-plane/platform/configs',
  );
  return payload.items;
}

export type GrayRoutingStage = 'gray-initial' | 'carry-on' | 'full';

export interface GrayRoutingStageDimensions {
  appVersions: string[];
  userIds: string[];
  provinces: string[];
  carriers: string[];
}

export interface GrayRoutingPolicyResponse {
  policy: {
    enabled: boolean;
    grayUpstream: string;
    grayUpstreamTlsInsecureSkipVerify: boolean;
    stageDimensions: Record<GrayRoutingStage, GrayRoutingStageDimensions>;
  };
  sourcePath: string;
  rawYaml: string;
}

export async function fetchGrayRoutingPolicy(): Promise<GrayRoutingPolicyResponse> {
  return fetchJSON<GrayRoutingPolicyResponse>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/control-plane/platform/rollout/routing-policy',
  );
}

export async function fetchConfigDomains(): Promise<ConfigDomainItem[]> {
  const payload = await fetchJSON<{ items: ConfigDomainItem[] }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/control-plane/platform/configs/domains',
  );
  return payload.items;
}

export async function fetchConfigSnapshot(env: string, service: string): Promise<ConfigSnapshotView> {
  return fetchJSON<ConfigSnapshotView>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    withQuery('/control-plane/platform/configs/snapshot', { env, service }),
  );
}

export async function fetchPlatformConfigInstanceReports(): Promise<{
  items: ConfigInstanceReportItem[];
  summary: ConfigInstanceReportSummary;
}> {
  return fetchJSON<{ items: ConfigInstanceReportItem[]; summary: ConfigInstanceReportSummary }>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    '/control-plane/platform/configs/instances',
  );
}

export async function fetchEffectiveConfig(query: ControlPlaneScopeQuery = {}): Promise<EffectiveConfigResponse> {
  return fetchJSON<EffectiveConfigResponse>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    withQuery('/control-plane/platform/configs/resolve', query),
  );
}

export async function fetchPlatformTriageSummary(query: ControlPlaneScopeQuery = {}): Promise<PlatformTriageSummaryResponse> {
  return fetchJSON<PlatformTriageSummaryResponse>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    withQuery('/control-plane/platform/triage/summary', query),
  );
}

export async function fetchPremiumPoolEntries(activeOnly = false): Promise<PremiumPoolEntryItem[]> {
  const payload = await fetchJSON<{ items: PremiumPoolEntryItem[] }>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    withQuery(productControlPlaneOperationPath('ListPremiumPoolEntries'), {
      activeOnly: activeOnly ? 'true' : undefined,
    }),
  );
  return payload.items;
}

export async function upsertPremiumPoolEntry(payload: {
  contentId: string;
  scope?: string;
  qualityScore: number;
  qualityAdmission: string;
  supplySource?: string;
  sourceTaskId?: string;
  auditId: string;
  rollbackToken?: string;
  expiresAt: string;
}): Promise<PremiumPoolEntryItem> {
  return postJSON<PremiumPoolEntryItem>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    productControlPlaneOperationPath('UpsertPremiumPoolEntry'),
    payload,
  );
}

export async function rollbackPremiumPoolEntry(contentId: string): Promise<PremiumPoolEntryItem> {
  const path = productControlPlaneOperationPath('RollbackPremiumPoolEntry')
    .replace('{contentId}', encodeURIComponent(contentId));
  return postJSON<PremiumPoolEntryItem>(envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'), path, {});
}

// takedown 为双签高危动作：单 principal 调用会返回 pending approval 状态，
// 第二个不同 principal 复核后才真正弹出条目。
export async function takedownPremiumPoolEntry(contentId: string): Promise<PremiumPoolMutationResponse> {
  const path = productControlPlaneOperationPath('TakedownPremiumPoolEntry')
    .replace('{contentId}', encodeURIComponent(contentId));
  return mutateJSON<PremiumPoolMutationResponse>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    'POST',
    path,
    {},
    { 'Idempotency-Key': `portal-premium-pool-takedown-${contentId}` },
  );
}

export async function fetchProductWorkflows(): Promise<WorkflowItem[]> {
  const payload = await fetchJSON<{ items: WorkflowItem[] }>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    '/control-plane/product/workflows',
  );
  return payload.items;
}

export async function fetchProductAudits(): Promise<PlatformAuditItem[]> {
  const payload = await fetchJSON<{ items: PlatformAuditItem[] }>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    '/control-plane/product/audits',
  );
  return payload.items;
}

export async function fetchProductApprovals(): Promise<ProductApprovalItem[]> {
  const payload = await fetchJSON<{ items: ProductApprovalItem[] }>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    '/control-plane/product/approvals',
  );
  return payload.items;
}

export async function fetchProductProjectionSummary(): Promise<ProductProjectionSummary> {
  return fetchJSON<ProductProjectionSummary>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    '/control-plane/product/projections/summary',
  );
}

export async function fetchProductEventSummary(query: ProductEventQuery = {}): Promise<ProductEventSummary> {
  return fetchJSON<ProductEventSummary>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    withQuery('/ops/events/summary', query),
  );
}

export async function fetchProductEventDrilldown(query: ProductEventQuery = {}): Promise<ProductEventDrilldown> {
  return fetchJSON<ProductEventDrilldown>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    withQuery('/ops/events/drilldown', query),
  );
}

export async function fetchRuntimeLogSummary(query: RuntimeLogQuery = {}): Promise<RuntimeLogSummary> {
  return fetchJSON<RuntimeLogSummary>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    withQuery('/ops/runtime-logs/summary', query),
  );
}

export async function fetchRuntimeLogDrilldown(query: RuntimeLogQuery = {}): Promise<RuntimeLogDrilldown> {
  return fetchJSON<RuntimeLogDrilldown>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    withQuery('/ops/runtime-logs/drilldown', query),
  );
}

export async function fetchRecommendationBehaviorMetrics(): Promise<RecommendationBehaviorMetrics> {
  return fetchJSON<RecommendationBehaviorMetrics>(
    envBaseUrl('VITE_CONTENT_SERVICE_BASE_URL'),
    '/metrics/rec/behavior-attribution',
  );
}

export async function fetchProductL1L4Metrics(query: ControlPlaneScopeQuery = {}): Promise<ProductL1L4MetricsResponse> {
  return fetchJSON<ProductL1L4MetricsResponse>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    withQuery('/control-plane/product/metrics/l1l4', query),
  );
}

export interface ServiceRouteREDItem {
  service: string;
  route: string;
  method?: string;
  qps: number;
  avgMs: number;
  p99Ms: number;
  successRatePercent: number;
}

export interface ServiceRouteREDResponse {
  items: ServiceRouteREDItem[];
  window: string;
  source: string;
}

export async function fetchServiceRouteRED(service: string): Promise<ServiceRouteREDResponse> {
  return fetchJSON<ServiceRouteREDResponse>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    withQuery('/control-plane/product/metrics/red-routes', { service }),
  );
}

export interface GrowthDailyItem {
  date: string;
  dau: number;
  pv: number;
  sessionCount: number;
  newActors: number;
  updatedAt?: string;
}

export interface GrowthOverviewResponse {
  days: GrowthDailyItem[];
  todayPv: number;
  todayDau: number;
  wau: number;
  mau: number;
  d1RetentionPercent: number;
  d7RetentionPercent: number;
  source: string;
  generatedAt: string;
}

export async function fetchGrowthOverview(days = 30): Promise<GrowthOverviewResponse> {
  return fetchJSON<GrowthOverviewResponse>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    withQuery('/control-plane/product/growth/overview', { days }),
  );
}

export interface PageExperienceStat {
  pageName: string;
  opens: number;
  avgReadyMs: number;
  readySamples: number;
  avgStayMs: number;
  staySamples: number;
  runtimeErrors: number;
}

export interface RtcMediaQoeHourlyPoint {
  bucketStart: string;
  partial: boolean;
  hasSamples: boolean;
  effectiveSampleCount: number;
  mediaConnectedCount: number;
  mediaConnectedRate: number | null;
  connectP95Ms: number | null;
  connectionLostCount: number;
  connectionLostRate: number | null;
  reconnectCount: number;
  generatedThrough: string | null;
}

export interface RtcMediaQoeSummary {
  hasSamples: boolean;
  windowHours: number;
  actualFrom: string;
  actualTo: string;
  effectiveSampleCount: number;
  mediaConnectedCount: number;
  mediaConnectedRate: number | null;
  connectP95Ms: number | null;
  connectionLostCount: number;
  connectionLostRate: number | null;
  reconnectCount: number;
  series: RtcMediaQoeHourlyPoint[];
  sourceKind: string;
  freshness: string;
  generatedThrough: string | null;
  lagSeconds: number | null;
}

export async function fetchPageExperience(query: { from?: string; to?: string } = {}): Promise<{
  items: PageExperienceStat[];
  source: string;
}> {
  return fetchJSON<{ items: PageExperienceStat[]; source: string }>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    withQuery('/control-plane/product/experience/pages', query),
  );
}

export async function fetchRtcMediaQoeSummary(): Promise<RtcMediaQoeSummary> {
  return fetchJSON<RtcMediaQoeSummary>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    productControlPlaneOperationPath('GetRtcMediaQoeSummary'),
  );
}

export async function fetchProductTriageSummary(query: ProductEventQuery = {}): Promise<ProductTriageSummaryResponse> {
  return fetchJSON<ProductTriageSummaryResponse>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    withQuery('/control-plane/product/triage/summary', query),
  );
}
