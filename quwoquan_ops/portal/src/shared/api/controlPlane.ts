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
  releaseState: string;
  configVersion?: string;
  updatedAt?: string;
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

export interface PlaneBindingItem {
  id: string;
  env: string;
  workload: string;
  plane: string;
  deploymentRef: string;
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
  releaseManifestDigest?: string;
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
  revision: number;
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
  callType?: string;
  participantCount?: number;
  connectTimeMs?: number;
  mediaConnected?: boolean;
  reconnectCount?: number;
  disconnectReason?: string;
  networkQuality?: string;
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
  /** 日志文本检索（Elasticsearch match_phrase；memory 仅限对象级 local_contract）。 */
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

export type HumanAuthorityCardType = 'intake' | 'choice' | 'authorization' | 'exception' | 'post_check';
export type HumanAuthorityRound = 1 | 2;
export type HumanAuthorityAction =
  | 'request_evidence'
  | 'transfer'
  | 'pause'
  | 'submit_round_1'
  | 'submit_round_2'
  | 'authorize'
  | 'post_check';

export interface HumanAuthorityOption {
  optionId: string;
  neutralLabel: string;
  userOutcome: string;
  businessOutcome: string;
  cost: string;
  timeToEffect: string;
  risk: string;
  reversibility: string;
  scopeChange: string;
  unknowns: string[];
  nextStep: string;
}

export interface HumanAuthorityCardProjection {
  schemaVersion: number;
  cardType: HumanAuthorityCardType;
  currentRole: string;
  roleResponsibility: string;
  question: string;
  whatHappened: string;
  userOrBusinessImpact: string;
  knownFacts: string[];
  unknowns: string[];
  hardConstraints: string[];
  options: HumanAuthorityOption[];
  selectedOptionId: string | null;
  agentRecommendation: string | null;
  actions: HumanAuthorityAction[];
  consequences: string[];
  safestDefault: string;
  auditDetails?: Record<string, unknown>;
}

export interface HumanAuthorityRoleTask {
  taskId: string;
  decisionUnitId: string;
  role: string;
  stage: string;
  decisionKind: string;
  state: string;
  dueAt?: string;
  sodPolicy: 'role-record-only' | 'independent-principal-required';
  sodMessage?: string;
  card: HumanAuthorityCardProjection;
}

export interface HumanAuthorityDecisionUnit {
  decisionUnitId: string;
  stage: string;
  decisionKind: string;
  scope: string;
  state: string;
  evidenceExpiresAt: string;
  currentTask?: HumanAuthorityRoleTask;
  readback?: HumanAuthorityReadback;
}

export interface HumanAuthorityReadback {
  decisionUnitId: string;
  status: string;
  recordedAt?: string;
  selectedOptionId?: string;
  replayed?: boolean;
  message: string;
}

export interface HumanAuthorityRoleSubmissionInput {
  round: HumanAuthorityRound;
  facts: string[];
  impacts: string[];
  unknowns: string[];
  selectedOptionId?: string;
  note?: string;
}

export interface HumanAuthorityActionInput {
  action: 'request_evidence' | 'transfer' | 'pause' | 'authorize' | 'post_check';
  note: string;
  targetRole?: string;
  selectedOptionId?: string;
}

export interface HumanAuthoritySubmissionResult {
  task: HumanAuthorityRoleTask;
  readback: HumanAuthorityReadback;
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

export type GrayRoutingStage = 'canary' | '5' | '20' | '50' | '100';

export interface RolloutSelector {
  mode: 'all' | 'include' | 'supported';
  values: string[];
}

export interface GrayRoutingStageDimensions {
  basisPoints: number;
  appVersions: RolloutSelector;
  platforms: RolloutSelector;
  regions: RolloutSelector;
  carriers: RolloutSelector;
}

export interface GrayRoutingPolicyResponse {
  policy: {
    enabled: boolean;
    campaignId: string;
    candidateDigest: string;
    allocationKeyId: string;
    subjectKind: 'device_actor';
    stage: GrayRoutingStage;
    status: 'active' | 'paused' | 'rolled_back' | 'complete';
    candidateUpstream: string;
    assignmentTtlDaysAfterCampaign: number;
    internalCanary: { accountIds: string[]; deviceActorIds: string[] };
    stages: Record<GrayRoutingStage, GrayRoutingStageDimensions>;
  };
  source: { path: string; sha256: string };
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
  return mutateJSON<PremiumPoolEntryItem>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    'POST',
    productControlPlaneOperationPath('UpsertPremiumPoolEntry'),
    payload,
    {
      'Idempotency-Key': premiumPoolMutationKey('upsert', payload.contentId),
    },
  );
}

export async function rollbackPremiumPoolEntry(contentId: string): Promise<PremiumPoolEntryItem> {
  const path = productControlPlaneOperationPath('RollbackPremiumPoolEntry')
    .replace('{contentId}', encodeURIComponent(contentId));
  return mutateJSON<PremiumPoolEntryItem>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    'POST',
    path,
    {},
    { 'Idempotency-Key': premiumPoolMutationKey('rollback', contentId) },
  );
}

export interface ExperimentVariant {
  key: string;
  allocationBasisPoints: number;
}

export interface ExperimentCatalogItem {
  id: string;
  key: string;
  status: string;
  experimentRevision: number;
  variants: ExperimentVariant[];
  variantStats: Record<string, number>;
  assignedSubjects: number;
}

export async function fetchExperiments(): Promise<ExperimentCatalogItem[]> {
  const payload = await fetchJSON<{ items: ExperimentCatalogItem[] }>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    productControlPlaneOperationPath('ListExperiments'),
  );
  return payload.items;
}

// rollout 为版本前置的原子重分配：expectedVersion 经 If-Match 承载，
// 权重总和必须精确为 10000 且至少一个变体为正（服务端强校验）。
export async function updateExperimentRollout(payload: {
  experimentId: string;
  expectedVersion: number;
  status: string;
  variants: ExperimentVariant[];
}): Promise<ExperimentCatalogItem> {
  const path = productControlPlaneOperationPath('UpdateExperimentRollout')
    .replace('{experimentId}', encodeURIComponent(payload.experimentId));
  return mutateJSON<ExperimentCatalogItem>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    'POST',
    path,
    { status: payload.status, variants: payload.variants },
    {
      'If-Match': String(payload.expectedVersion),
      'Idempotency-Key':
        `portal-experiment-rollout-${payload.experimentId}-${payload.expectedVersion}`,
    },
  );
}

export interface AccountEnforcementCaseView {
  caseId: string;
  caseKind: string;
  status: string;
  version: number;
  approvalCount: number;
  decisionId?: string;
  deliveryStatus?: string;
  updatedAt: string;
}

export async function fetchAccountEnforcementCase(
  caseId: string,
): Promise<AccountEnforcementCaseView> {
  const path = productControlPlaneOperationPath('GetAccountEnforcementCase')
    .replace('{caseId}', encodeURIComponent(caseId));
  return fetchJSON<AccountEnforcementCaseView>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    path,
  );
}

// review 为双签高危处置：不同 principal 各自 approve 后才生成处置决定，
// 幂等键绑定 case 与 verdict，重复提交回放而不重复计票。
export async function reviewAccountEnforcementCase(
  caseId: string,
  verdict: 'approve' | 'reject',
): Promise<AccountEnforcementCaseView> {
  const path = productControlPlaneOperationPath('ReviewAccountEnforcementCase')
    .replace('{caseId}', encodeURIComponent(caseId));
  return mutateJSON<AccountEnforcementCaseView>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    'POST',
    path,
    { verdict },
    { 'Idempotency-Key': `portal-enforcement-review-${caseId}-${verdict}` },
  );
}

export async function retryAccountEnforcementDelivery(
  caseId: string,
): Promise<AccountEnforcementCaseView> {
  const path = productControlPlaneOperationPath('RetryAccountEnforcementDelivery')
    .replace('{caseId}', encodeURIComponent(caseId));
  // retry-delivery 契约要求空 body（服务端 requireEmptyBody 强校验）。
  return mutateJSON<AccountEnforcementCaseView>(
    envBaseUrl('VITE_PRODUCT_OPS_BASE_URL'),
    'POST',
    path,
    undefined,
    { 'Idempotency-Key': `portal-enforcement-retry-${caseId}` },
  );
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
    { 'Idempotency-Key': premiumPoolMutationKey('takedown', contentId) },
  );
}

function premiumPoolMutationKey(action: string, contentId: string): string {
  return `portal-premium-pool-${action}-${contentId}-${globalThis.crypto.randomUUID()}`;
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

export interface GrowthFunnelSegment {
  sourceTrack: string;
  consumedActors: number;
  publishedActors: number;
  returnedActors: number;
  exposedActors: number | null;
  exposedNote?: string;
}

export interface GrowthOverviewResponse {
  days: GrowthDailyItem[];
  todayPv: number;
  todayDau: number;
  wau: number;
  mau: number;
  d1RetentionPercent: number;
  d7RetentionPercent: number;
  funnel: GrowthFunnelSegment;
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


const humanAuthorityBasePath = '/control-plane/platform/human-authority';

function asString(value: unknown, fallback?: string): string {
  return typeof value === 'string' ? value : fallback ?? '';
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function pick(record: Record<string, unknown>, camel: string, snake: string): unknown {
  return record[camel] ?? record[snake];
}

function adaptHumanAuthorityOption(value: unknown): HumanAuthorityOption {
  const option = asRecord(value);
  return {
    optionId: asString(pick(option, 'optionId', 'option_id')),
    neutralLabel: asString(pick(option, 'neutralLabel', 'neutral_label')),
    userOutcome: asString(pick(option, 'userOutcome', 'user_outcome')),
    businessOutcome: asString(pick(option, 'businessOutcome', 'business_outcome')),
    cost: asString(option.cost),
    timeToEffect: asString(pick(option, 'timeToEffect', 'time_to_effect')),
    risk: asString(option.risk),
    reversibility: asString(option.reversibility),
    scopeChange: asString(pick(option, 'scopeChange', 'scope_change')),
    unknowns: asStringArray(option.unknowns),
    nextStep: asString(pick(option, 'nextStep', 'next_step')),
  };
}

function adaptHumanAuthorityCard(value: unknown, unit: Record<string, unknown> = {}): HumanAuthorityCardProjection {
  const card = asRecord(value);
  const cardType = asString(pick(card, 'cardType', 'card_type'), 'intake') as HumanAuthorityCardType;
  return {
    schemaVersion: Number(pick(card, 'schemaVersion', 'schema_version') ?? 1),
    cardType,
    currentRole: asString(pick(card, 'currentRole', 'current_role')),
    roleResponsibility: asString(pick(card, 'roleResponsibility', 'role_responsibility')),
    question: asString(card.question),
    whatHappened: asString(pick(card, 'whatHappened', 'what_happened')),
    userOrBusinessImpact: asString(pick(card, 'userOrBusinessImpact', 'user_or_business_impact')),
    knownFacts: asStringArray(pick(card, 'knownFacts', 'known_facts')),
    unknowns: asStringArray(card.unknowns),
    hardConstraints: asStringArray(pick(card, 'hardConstraints', 'hard_constraints')),
    options: (Array.isArray(card.options) ? card.options : []).map(adaptHumanAuthorityOption),
    selectedOptionId: asString(pick(card, 'selectedOptionId', 'selected_option_id')) || null,
    agentRecommendation: asString(pick(card, 'agentRecommendation', 'agent_recommendation')) || null,
    actions: asStringArray(card.actions) as HumanAuthorityAction[],
    consequences: asStringArray(card.consequences),
    safestDefault: asString(pick(card, 'safestDefault', 'safest_default'), '暂停并等待具名负责人确认。'),
    auditDetails: Object.keys(asRecord(pick(card, 'auditDetails', 'audit_details'))).length
      ? asRecord(pick(card, 'auditDetails', 'audit_details'))
      : Object.keys(unit).length ? unit : undefined,
  };
}

function taskStateFromHostedUnit(unit: Record<string, unknown>): string {
  if (asRecord(unit.decision).decisionId || asRecord(unit.decision).decision_id) return 'recorded';
  const sealed = Array.isArray(pick(unit, 'sealedRounds', 'sealed_rounds'))
    ? pick(unit, 'sealedRounds', 'sealed_rounds') as unknown[]
    : [];
  if (sealed.includes(2)) return 'ready_to_decide';
  if (sealed.includes(1)) return 'awaiting_round_2';
  return 'awaiting_round_1';
}

function adaptHostedHumanAuthorityUnit(value: unknown): HumanAuthorityDecisionUnit {
  const unit = asRecord(value);
  const submissions = Array.isArray(unit.submissions) ? unit.submissions.map(asRecord) : [];
  const decisionUnitId = asString(pick(unit, 'decisionUnitId', 'decision_unit_id'));
  const requiredRoles = asStringArray(pick(unit, 'requiredRoles', 'required_roles'));
  const currentRole = asString(pick(unit, 'accountableRole', 'accountable_role'), requiredRoles[0]);
  const state = taskStateFromHostedUnit(unit);
  const selectedOptionId = asString(pick(asRecord(unit.decision), 'selectedOptionId', 'selected_option_id'));
  const cardType: HumanAuthorityCardType = state === 'recorded'
    ? 'post_check'
    : state === 'ready_to_decide'
      ? 'authorization'
      : state === 'awaiting_round_2'
        ? 'choice'
        : 'intake';
  const fallbackCard = {
    schemaVersion: 1,
    cardType,
    currentRole,
    roleResponsibility: '请完成当前服务器分配给你的交付决定职责。',
    question: cardType === 'choice' ? '请独立评估各方案的影响' : cardType === 'authorization' ? '请确认本次交付决定' : '请确认第一轮事实',
    whatHappened: asString(unit.summary, `交付决定 ${decisionUnitId} 正等待当前职责输入。`),
    userOrBusinessImpact: asString(pick(unit, 'impactSummary', 'impact_summary'), '请以当前服务器证据为准评估用户与业务影响。'),
    knownFacts: submissions.filter((item) => Number(item.round) === 1).map((item) => `已收到 ${asString(item.role)} 的第一轮事实`),
    unknowns: [] as string[],
    hardConstraints: asStringArray(pick(unit, 'hardConstraints', 'hard_constraints')),
    options: Array.isArray(unit.options) ? unit.options : [],
    selectedOptionId: selectedOptionId || null,
    agentRecommendation: null,
    actions: cardType === 'authorization'
      ? ['authorize', 'request_evidence', 'transfer', 'pause']
      : cardType === 'post_check'
        ? ['post_check', 'request_evidence', 'pause']
        : [cardType === 'choice' ? 'submit_round_2' : 'submit_round_1', 'request_evidence', 'transfer', 'pause'],
    consequences: asStringArray(unit.consequences),
    safestDefault: '暂停并等待具名负责人确认，不作隐式批准。',
    auditDetails: unit,
  };
  const card = Object.keys(asRecord(pick(unit, 'card', 'card_projection'))).length
    ? adaptHumanAuthorityCard(pick(unit, 'card', 'card_projection'), unit)
    : adaptHumanAuthorityCard(fallbackCard, unit);
  return {
    decisionUnitId,
    stage: asString(unit.stage),
    decisionKind: asString(pick(unit, 'decisionKind', 'decision_kind')),
    scope: asString(unit.scope),
    state,
    evidenceExpiresAt: asString(pick(unit, 'evidenceExpiresAt', 'evidence_expires_at')),
    currentTask: {
      taskId: decisionUnitId,
      decisionUnitId,
      role: card.currentRole,
      stage: asString(unit.stage),
      decisionKind: asString(pick(unit, 'decisionKind', 'decision_kind')),
      state,
      dueAt: asString(pick(unit, 'evidenceExpiresAt', 'evidence_expires_at')) || undefined,
      sodPolicy: asString(pick(unit, 'sodPolicy', 'sod_policy'), 'role-record-only') as HumanAuthorityRoleTask['sodPolicy'],
      sodMessage: asString(pick(unit, 'sodMessage', 'sod_message')) || undefined,
      card,
    },
    readback: state === 'recorded'
      ? { decisionUnitId, status: state, selectedOptionId: selectedOptionId || undefined, message: '服务器已记录决定。' }
      : undefined,
  };
}

function adaptHumanAuthorityReadback(value: unknown, decisionUnitId: string): HumanAuthorityReadback {
  const readback = asRecord(value);
  const hostedUnit = Object.keys(asRecord(readback.unit)).length ? asRecord(readback.unit) : readback;
  return {
    decisionUnitId: asString(pick(readback, 'decisionUnitId', 'decision_unit_id'), decisionUnitId),
    status: asString(readback.status, taskStateFromHostedUnit(hostedUnit)),
    recordedAt: asString(pick(readback, 'recordedAt', 'recorded_at'), asString(pick(asRecord(hostedUnit.decision), 'recordedAt', 'recorded_at'))) || undefined,
    selectedOptionId: asString(pick(readback, 'selectedOptionId', 'selected_option_id'), asString(pick(asRecord(hostedUnit.decision), 'selectedOptionId', 'selected_option_id'))) || undefined,
    replayed: typeof readback.replayed === 'boolean' ? readback.replayed : undefined,
    message: asString(readback.message, '服务器已返回当前 authority 记录。'),
  };
}

function adaptHumanAuthorityTask(value: unknown): HumanAuthorityRoleTask {
  const task = asRecord(value);
  if (!Object.keys(asRecord(pick(task, 'card', 'card_projection'))).length) {
    const unit = adaptHostedHumanAuthorityUnit(task);
    if (unit.currentTask) return unit.currentTask;
  }
  const card = adaptHumanAuthorityCard(pick(task, 'card', 'card_projection'));
  return {
    taskId: asString(pick(task, 'taskId', 'task_id')),
    decisionUnitId: asString(pick(task, 'decisionUnitId', 'decision_unit_id')),
    role: asString(task.role, card.currentRole),
    stage: asString(task.stage),
    decisionKind: asString(pick(task, 'decisionKind', 'decision_kind')),
    state: asString(task.state),
    dueAt: asString(pick(task, 'dueAt', 'due_at')) || undefined,
    sodPolicy: asString(pick(task, 'sodPolicy', 'sod_policy'), 'role-record-only') as HumanAuthorityRoleTask['sodPolicy'],
    sodMessage: asString(pick(task, 'sodMessage', 'sod_message')) || undefined,
    card,
  };
}

function adaptHumanAuthorityDecisionUnit(value: unknown): HumanAuthorityDecisionUnit {
  const unit = asRecord(value);
  const taskValue = pick(unit, 'currentTask', 'current_task');
  if (!Object.keys(asRecord(taskValue)).length) return adaptHostedHumanAuthorityUnit(unit);
  const task = adaptHumanAuthorityTask(taskValue);
  const decisionUnitId = asString(pick(unit, 'decisionUnitId', 'decision_unit_id'), task.decisionUnitId);
  return {
    decisionUnitId,
    stage: asString(unit.stage, task.stage),
    decisionKind: asString(pick(unit, 'decisionKind', 'decision_kind'), task.decisionKind),
    scope: asString(unit.scope),
    state: asString(unit.state, task.state),
    evidenceExpiresAt: asString(pick(unit, 'evidenceExpiresAt', 'evidence_expires_at')),
    currentTask: task,
    readback: Object.keys(asRecord(unit.readback)).length ? adaptHumanAuthorityReadback(unit.readback, decisionUnitId) : undefined,
  };
}

function humanAuthorityMutationKey(taskId: string, action: string): string {
  return `portal-human-authority-${taskId}-${action}-${globalThis.crypto.randomUUID()}`;
}

export async function fetchHumanAuthorityDecisionUnits(): Promise<HumanAuthorityDecisionUnit[]> {
  const payload = await fetchJSON<unknown>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    `${humanAuthorityBasePath}/decision-units`,
  );
  const record = asRecord(payload);
  const items = Array.isArray(payload) ? payload : Array.isArray(record.items) ? record.items : [];
  return items.map(adaptHumanAuthorityDecisionUnit);
}

export async function fetchHumanAuthorityTask(taskId: string): Promise<HumanAuthorityRoleTask> {
  const payload = await fetchJSON<unknown>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    `${humanAuthorityBasePath}/decision-units/${encodeURIComponent(taskId)}`,
  );
  const record = asRecord(payload);
  return adaptHumanAuthorityTask(record.task ?? record.unit ?? payload);
}

export async function submitHumanAuthorityRound(
  taskId: string,
  input: HumanAuthorityRoleSubmissionInput,
  idempotencyKey = humanAuthorityMutationKey(taskId, `round-${input.round}`),
): Promise<HumanAuthoritySubmissionResult> {
  const submissionPayload = {
    round: input.round,
    facts: input.facts,
    impacts: input.impacts,
    unknowns: input.unknowns,
    selectedOptionId: input.selectedOptionId,
  };
  await mutateJSON<unknown>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    'POST',
    `${humanAuthorityBasePath}/decision-units/${encodeURIComponent(taskId)}/submissions`,
    submissionPayload,
    { 'Idempotency-Key': idempotencyKey },
  );
  const sealed = await mutateJSON<unknown>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    'POST',
    `${humanAuthorityBasePath}/decision-units/${encodeURIComponent(taskId)}/rounds/${input.round}:seal`,
    {},
    { 'Idempotency-Key': `${idempotencyKey}-seal` },
  );
  const task = adaptHumanAuthorityTask(sealed);
  return { task, readback: adaptHumanAuthorityReadback(sealed, task.decisionUnitId) };
}

export async function applyHumanAuthorityAction(
  taskId: string,
  input: HumanAuthorityActionInput,
  idempotencyKey = humanAuthorityMutationKey(taskId, input.action),
): Promise<HumanAuthoritySubmissionResult> {
  if (input.action === 'authorize' || input.action === 'post_check') {
    const payload = await mutateJSON<unknown>(
      envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
      'POST',
      `${humanAuthorityBasePath}/decision-units/${encodeURIComponent(taskId)}:finalize`,
      { selectedOptionId: input.selectedOptionId, note: input.note },
      { 'Idempotency-Key': idempotencyKey },
    );
    const task = adaptHumanAuthorityTask(payload);
    return { task, readback: adaptHumanAuthorityReadback(payload, task.decisionUnitId) };
  }
  throw new RuntimeError(fallbackRuntimeErrorResponse({
    code: 'HAD.ACTION_UNAVAILABLE',
    requestPath: `${humanAuthorityBasePath}/decision-units/${encodeURIComponent(taskId)}`,
    cause: `hosted provider has not exposed ${input.action} command`,
  }));
}

export async function fetchHumanAuthorityReadback(decisionUnitId: string): Promise<HumanAuthorityReadback> {
  const payload = await fetchJSON<unknown>(
    envBaseUrl('VITE_PLATFORM_OPS_BASE_URL'),
    `${humanAuthorityBasePath}/decision-units/${encodeURIComponent(decisionUnitId)}`,
  );
  return adaptHumanAuthorityReadback(payload, decisionUnitId);
}
