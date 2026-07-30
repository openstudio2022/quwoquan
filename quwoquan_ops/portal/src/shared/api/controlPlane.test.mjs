import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ackAlert,
  beginReportReview,
  decidePostModerationCase,
  dismissReport,
  fetchActiveAlerts,
  fetchEffectiveConfig,
  fetchGrayRoutingPolicy,
  fetchHomepageCandidates,
  fetchHomepageClaimRequests,
  fetchHomepageStatusReports,
  fetchPlatformConfigInstanceReports,
  fetchPlatformProjectionSummary,
  fetchPremiumPoolEntries,
  fetchReleases,
  fetchPlatformAudits,
  fetchPlatformApprovals,
  fetchPlatformTriageSummary,
  fetchProductEventDrilldown,
  fetchProductEventSummary,
  fetchProductL1L4Metrics,
  fetchRtcMediaQoeSummary,
  fetchProductTriageSummary,
  fetchProductProjectionSummary,
  fetchRuntimeLogDrilldown,
  fetchRuntimeLogSummary,
  fetchRecommendationBehaviorMetrics,
  fetchReports,
  fetchCurrentPostModerationCase,
  reviewPostModerationCase,
  resolveReport,
  takedownPremiumPoolEntry,
  fetchServiceCatalog,
  intakeHomepageCandidate,
  publishHomepageCandidate,
  reviewHomepageClaimRequest,
  reviewHomepageStatusReport,
} from '../../../.test-dist/shared/api/controlPlane.js';

const originalFetch = globalThis.fetch;
const originalPlatformBaseUrl = process.env.VITE_PLATFORM_OPS_BASE_URL;
const originalProductBaseUrl = process.env.VITE_PRODUCT_OPS_BASE_URL;
const originalContentServiceBaseUrl = process.env.VITE_CONTENT_SERVICE_BASE_URL;
const originalEntityServiceBaseUrl = process.env.VITE_ENTITY_SERVICE_BASE_URL;

function stubFetch(payload) {
  const calls = [];
  globalThis.fetch = async (input) => {
    calls.push(String(input));
    return {
      ok: true,
      json: async () => payload,
    };
  };
  return calls;
}

function stubFetchSequence(responses) {
  const calls = [];
  globalThis.fetch = async (input, init) => {
    calls.push({ url: String(input), init });
    const next = responses[Math.min(calls.length - 1, responses.length - 1)];
    return {
      ok: next.ok ?? true,
      status: next.status ?? 200,
      headers: new Headers(next.headers ?? {}),
      json: async () => next.payload,
      text: async () => JSON.stringify(next.payload ?? {}),
    };
  };
  return calls;
}

function restoreEnvAndFetch() {
  globalThis.fetch = originalFetch;
  process.env.VITE_PLATFORM_OPS_BASE_URL = originalPlatformBaseUrl;
  process.env.VITE_PRODUCT_OPS_BASE_URL = originalProductBaseUrl;
  process.env.VITE_CONTENT_SERVICE_BASE_URL = originalContentServiceBaseUrl;
  process.env.VITE_ENTITY_SERVICE_BASE_URL = originalEntityServiceBaseUrl;
}

test('requests platform service catalog from configured base url', async () => {
  process.env.VITE_PLATFORM_OPS_BASE_URL = 'http://platform.test';
  const calls = stubFetch({
    items: [{ id: 'content-service', service: 'content-service', plane: 'user-plane', owner: 'content-team', health: 'success', summary: 'ok' }],
  });

  const items = await fetchServiceCatalog();

  assert.equal(calls[0], 'http://platform.test/control-plane/platform/catalog/services');
  assert.equal(items[0].service, 'content-service');
  restoreEnvAndFetch();
});

test('requests report queue through generated control-plane metadata', async () => {
  process.env.VITE_CONTENT_SERVICE_BASE_URL = 'http://content.test';
  const calls = stubFetch({
    items: [{
      id: 'rpt-1',
      version: 1,
      targetType: 'post',
      targetId: 'post-1',
      reason: 'spam',
      status: 'pending',
      createdAt: '2026-07-13T00:00:00Z',
      updatedAt: '2026-07-13T00:00:00Z',
    }],
    total: 1,
  });

  const items = await fetchReports();

  assert.equal(calls[0], 'http://content.test/content/reports?limit=50');
  assert.equal(items[0].id, 'rpt-1');
  assert.equal(items[0].version, 1);
  restoreEnvAndFetch();
});

test('report review and resolve use generated paths with idempotency keys', async () => {
  process.env.VITE_CONTENT_SERVICE_BASE_URL = 'http://content.test';
  const calls = stubFetchSequence([
    { payload: { id: 'rpt-1', version: 2, targetType: 'post', targetId: 'post-1', reason: 'spam', status: 'reviewing', createdAt: '', updatedAt: '' } },
    { payload: { id: 'rpt-1', version: 3, targetType: 'post', targetId: 'post-1', reason: 'spam', status: 'resolved', createdAt: '', updatedAt: '' } },
  ]);

  const reviewing = await beginReportReview('rpt-1');
  const resolved = await resolveReport('rpt-1', 'warn');

  assert.equal(calls[0].url, 'http://content.test/content/reports/rpt-1/review');
  assert.equal(calls[0].init?.method, 'POST');
  assert.equal(calls[0].init?.headers['Idempotency-Key'], 'portal-begin-review-rpt-1');
  assert.equal(reviewing.status, 'reviewing');

  assert.equal(calls[1].url, 'http://content.test/content/reports/rpt-1');
  assert.equal(calls[1].init?.method, 'PATCH');
  assert.match(String(calls[1].init?.body), /"resolution":"warn"/);
  assert.equal(resolved.status, 'resolved');
  restoreEnvAndFetch();
});

test('report dismissal and moderation case workflow use generated paths', async () => {
  process.env.VITE_CONTENT_SERVICE_BASE_URL = 'http://content.test';
  const caseItem = {
    id: 'case-1',
    version: 1,
    postId: 'post-1',
    postVersion: 3,
    contentDigest: 'digest',
    status: 'pending',
    createdAt: '',
    updatedAt: '',
  };
  const calls = stubFetchSequence([
    { payload: caseItem },
    { payload: { ...caseItem, version: 2, status: 'reviewed' } },
    { payload: { ...caseItem, version: 3, status: 'rejected' } },
    { payload: { id: 'rpt-1', status: 'dismissed' } },
  ]);

  const loaded = await fetchCurrentPostModerationCase('post-1');
  const reviewed = await reviewPostModerationCase(loaded);
  const decided = await decidePostModerationCase(
    reviewed,
    'rejected',
    '确认存在违规内容',
  );
  const dismissed = await dismissReport('rpt-1');

  assert.equal(
    calls[0].url,
    'http://content.test/internal/content/posts/post-1/moderation-case',
  );
  assert.equal(
    calls[1].url,
    'http://content.test/internal/content/posts/post-1:review-moderation',
  );
  assert.match(String(calls[1].init?.body), /"caseId":"case-1"/);
  assert.equal(
    calls[2].url,
    'http://content.test/internal/content/posts/post-1:moderate',
  );
  assert.match(String(calls[2].init?.body), /"decisionReason":"确认存在违规内容"/);
  assert.equal(
    calls[3].url,
    'http://content.test/content/reports/rpt-1:dismiss',
  );
  assert.equal(decided.status, 'rejected');
  assert.equal(dismissed.status, 'dismissed');
  restoreEnvAndFetch();
});

test('entity homepage governance queues use generated operation paths', async () => {
  process.env.VITE_ENTITY_SERVICE_BASE_URL = 'http://entity.test';
  const calls = stubFetchSequence([
    { payload: { items: [{ homepageId: 'hp-1', canonicalEntityId: 'place-1', title: '西湖', homepageType: 'place', status: 'candidate' }] } },
    { payload: { items: [{ claimRequestId: 'claim-1', version: 1, homepageId: 'hp-1', requesterPersonaId: 'persona-1', claimTier: 'basic', status: 'pending_review', createdAt: '', updatedAt: '' }] } },
    { payload: { items: [{ reportId: 'report-1', version: 1, homepageId: 'hp-1', reporterPersonaId: 'persona-2', reason: 'offline', evidenceUrls: [], status: 'pending_review', createdAt: '', updatedAt: '' }] } },
  ]);

  const [candidates, claims, reports] = await Promise.all([
    fetchHomepageCandidates({ limit: 20 }),
    fetchHomepageClaimRequests({ status: 'pending_review', limit: 20 }),
    fetchHomepageStatusReports({ status: 'pending_review', limit: 20 }),
  ]);

  assert.equal(calls[0].url, 'http://entity.test/homepages/candidates?limit=20');
  assert.equal(calls[1].url, 'http://entity.test/homepage-claim-requests?status=pending_review&limit=20');
  assert.equal(calls[2].url, 'http://entity.test/homepage-status-reports?status=pending_review&limit=20');
  assert.equal(candidates.items[0].homepageId, 'hp-1');
  assert.equal(claims.items[0].claimRequestId, 'claim-1');
  assert.equal(reports.items[0].reportId, 'report-1');
  restoreEnvAndFetch();
});

test('entity homepage governance mutations are typed and idempotent', async () => {
  process.env.VITE_ENTITY_SERVICE_BASE_URL = 'http://entity.test';
  const claim = {
    claimRequestId: 'claim-1',
    version: 1,
    homepageId: 'hp-1',
    requesterPersonaId: 'persona-1',
    claimTier: 'basic',
    status: 'pending_review',
    createdAt: '',
    updatedAt: '',
  };
  const report = {
    reportId: 'report-1',
    version: 1,
    homepageId: 'hp-1',
    reporterPersonaId: 'persona-2',
    reason: 'offline',
    evidenceUrls: [],
    status: 'pending_review',
    createdAt: '',
    updatedAt: '',
  };
  const calls = stubFetchSequence([
    { payload: { homepageId: 'hp-1', canonicalEntityId: 'place-1', title: '西湖', homepageType: 'place', status: 'candidate' } },
    { payload: { homepageId: 'hp-1', canonicalEntityId: 'place-1', title: '西湖', homepageType: 'place', status: 'published' } },
    { payload: { ...claim, version: 2, status: 'approved' } },
    { payload: { ...report, version: 2, status: 'confirmed_offline' } },
  ]);

  await intakeHomepageCandidate({
    title: '西湖',
    homepageType: 'place',
    canonicalEntityId: 'place-1',
  });
  await publishHomepageCandidate('hp-1');
  await reviewHomepageClaimRequest(claim, 'approved', '资质通过');
  await reviewHomepageStatusReport(report, 'confirmed_offline', '现场证据有效');

  assert.equal(calls[0].url, 'http://entity.test/homepages/candidates');
  assert.equal(calls[0].init?.headers['Idempotency-Key'], 'portal-homepage-intake-place-1');
  assert.equal(calls[1].url, 'http://entity.test/homepages/candidates/hp-1:publish');
  assert.equal(calls[1].init?.headers['Idempotency-Key'], 'portal-homepage-publish-hp-1');
  assert.equal(calls[2].url, 'http://entity.test/homepages/hp-1/claim-requests/claim-1:review');
  assert.match(String(calls[2].init?.body), /"reviewNote":"资质通过"/);
  assert.equal(calls[3].url, 'http://entity.test/homepages/hp-1/status-reports/report-1:review');
  assert.match(String(calls[3].init?.body), /"status":"confirmed_offline"/);
  restoreEnvAndFetch();
});

test('premium pool listing and dual-sign takedown use generated operation paths', async () => {
  process.env.VITE_PRODUCT_OPS_BASE_URL = 'http://product.test';
  const calls = stubFetchSequence([
    { payload: { items: [{ id: 'post-1', contentId: 'post-1', scope: 'global', status: 'active', qualityScore: 0.92, qualityAdmission: 'approved', auditId: 'audit-1', rollbackToken: 'rbk-1', featuredAt: '', expiresAt: '', takedownEjected: false, updatedAt: '' }] } },
    { payload: { entry: { id: 'post-1' }, approvalCount: 1, approvalState: 'pending_second_principal', pending: true, payloadDigest: 'digest', approverActors: ['ops-1'] } },
  ]);

  const entries = await fetchPremiumPoolEntries();
  const pendingResponse = await takedownPremiumPoolEntry('post-1');

  assert.equal(calls[0].url, 'http://product.test/control-plane/product/recommendation/premium-pool');
  assert.equal(entries[0].contentId, 'post-1');
  assert.equal(calls[1].url, 'http://product.test/control-plane/product/recommendation/premium-pool/post-1:takedown');
  assert.equal(calls[1].init?.method, 'POST');
  assert.equal('pending' in pendingResponse && pendingResponse.pending, true);
  restoreEnvAndFetch();
});

test('active alerts listing and ack hit platform alert loop endpoints', async () => {
  process.env.VITE_PLATFORM_OPS_BASE_URL = 'http://platform.test';
  const calls = stubFetchSequence([
    { payload: { items: [{ id: 'fp-1', fingerprint: 'fp-1', alertName: 'HTTPErrorRateHigh', severity: 'critical', labels: {}, annotations: {}, status: 'firing', updatedAt: '' }] } },
    { payload: { id: 'fp-1', fingerprint: 'fp-1', alertName: 'HTTPErrorRateHigh', severity: 'critical', labels: {}, annotations: {}, status: 'acknowledged', ackedBy: 'oncall-1', updatedAt: '' } },
  ]);

  const alerts = await fetchActiveAlerts();
  const acked = await ackAlert('fp-1');

  assert.equal(calls[0].url, 'http://platform.test/control-plane/platform/alerts/active');
  assert.equal(alerts[0].status, 'firing');
  assert.equal(calls[1].url, 'http://platform.test/control-plane/platform/alerts/fp-1:ack');
  assert.equal(calls[1].init?.method, 'POST');
  assert.equal(acked.status, 'acknowledged');
  restoreEnvAndFetch();
});

test('requests stage-scoped gray routing policy from platform control plane', async () => {
  process.env.VITE_PLATFORM_OPS_BASE_URL = 'http://platform.test';
  const calls = stubFetch({
    policy: {
      enabled: true,
      grayUpstream: 'http://gray.internal:29000',
      grayUpstreamTlsInsecureSkipVerify: false,
      stageDimensions: {
        'gray-initial': {
          appVersions: [],
          userIds: ['ops-release-canary'],
          provinces: [],
          carriers: [],
        },
        'carry-on': {
          appVersions: ['1.1.0'],
          userIds: ['ops-release-canary'],
          provinces: [],
          carriers: [],
        },
        full: {
          appVersions: [],
          userIds: [],
          provinces: [],
          carriers: [],
        },
      },
    },
    sourcePath: '/runtime/config-root/gray-routing/policy.yaml',
    rawYaml: 'policy: {}',
  });

  const response = await fetchGrayRoutingPolicy();

  assert.equal(calls[0], 'http://platform.test/control-plane/platform/rollout/routing-policy');
  assert.deepEqual(response.policy.stageDimensions['gray-initial'].userIds, ['ops-release-canary']);
  assert.deepEqual(response.policy.stageDimensions.full.appVersions, []);
  restoreEnvAndFetch();
});

test('requests product projection summary from configured base url', async () => {
  process.env.VITE_PRODUCT_OPS_BASE_URL = 'http://product.test';
  const calls = stubFetch({
    workflowCount: 5,
    approvalCount: 4,
    auditCount: 6,
    pendingDualReview: 2,
    activeObjectTypes: ['moderation_case', 'experiment'],
  });

  const summary = await fetchProductProjectionSummary();

  assert.equal(calls[0], 'http://product.test/control-plane/product/projections/summary');
  assert.equal(summary.pendingDualReview, 2);
  restoreEnvAndFetch();
});

test('requests RTC media QoE through generated operation metadata', async () => {
  process.env.VITE_PRODUCT_OPS_BASE_URL = 'http://product.test';
  const calls = stubFetch({
    hasSamples: true,
    windowHours: 24,
    actualFrom: '2026-07-19T17:00:00Z',
    actualTo: '2026-07-20T16:30:00Z',
    effectiveSampleCount: 4,
    mediaConnectedCount: 3,
    mediaConnectedRate: 0.75,
    connectP95Ms: 290,
    connectionLostCount: 1,
    connectionLostRate: 1 / 3,
    reconnectCount: 10,
    series: [],
    sourceKind: 'raw_records',
    freshness: 'near_realtime',
    generatedThrough: '2026-07-20T16:29:40Z',
    lagSeconds: 20,
  });

  const summary = await fetchRtcMediaQoeSummary();

  assert.equal(
    calls[0],
    'http://product.test/ops/events/rtc-media-qoe/summary',
  );
  assert.equal(summary.sourceKind, 'raw_records');
  assert.equal(summary.mediaConnectedRate, 0.75);
  assert.equal(summary.connectP95Ms, 290);
  restoreEnvAndFetch();
});

test('requests product event summary from configured base url', async () => {
  process.env.VITE_PRODUCT_OPS_BASE_URL = 'http://product.test';
  const calls = stubFetch({
    totalCount: 12,
    sessionCount: 5,
    dimensions: { pageName: { home: 8 } },
  });

  const summary = await fetchProductEventSummary({ eventType: 'app_anr_outcome', result: 'detected', from: '2026-04-01T00:00:00Z', to: '2026-04-02T00:00:00Z' });

  assert.equal(calls[0], 'http://product.test/ops/events/summary?eventType=app_anr_outcome&result=detected&from=2026-04-01T00%3A00%3A00Z&to=2026-04-02T00%3A00%3A00Z');
  assert.equal(summary.totalCount, 12);
  assert.equal(summary.sessionCount, 5);
  restoreEnvAndFetch();
});

test('requests product event drilldown from configured base url', async () => {
  process.env.VITE_PRODUCT_OPS_BASE_URL = 'http://product.test';
  const calls = stubFetch({
    totalCount: 1,
    items: [{ rowKey: 'row-1', logType: 'event', eventType: 'page_open', sessionId: 's.***.1', pageName: 'home', occurredAt: '2026-04-01T00:00:00Z' }],
  });

  const drilldown = await fetchProductEventDrilldown({ eventType: 'page_open', from: '2026-04-01T00:00:00Z', to: '2026-04-01T00:15:00Z', limit: 5 });

  assert.equal(calls[0], 'http://product.test/ops/events/drilldown?eventType=page_open&from=2026-04-01T00%3A00%3A00Z&to=2026-04-01T00%3A15%3A00Z&limit=5');
  assert.equal(drilldown.items[0].rowKey, 'row-1');
  restoreEnvAndFetch();
});

test('requests canonical runtime diagnostics from product ops', async () => {
  process.env.VITE_PRODUCT_OPS_BASE_URL = 'http://product.test';
  const calls = stubFetchSequence([
    {
      payload: {
        totalCount: 4,
        dimensions: { signal: { 'app.exception.flutter': 4 } },
        source: 'sls_aggregate',
      },
    },
    {
      payload: {
        totalCount: 1,
        items: [{ rowKey: 'runtime-1', signal: 'app.exception.flutter', severity: 'ERROR', message: 'safe' }],
        source: 'sls_raw',
      },
    },
  ]);

  const query = { signal: 'app.exception.flutter', from: '2026-04-01T00:00:00Z', to: '2026-04-01T01:00:00Z' };
  const summary = await fetchRuntimeLogSummary(query);
  const drilldown = await fetchRuntimeLogDrilldown({ ...query, limit: 5 });

  assert.equal(calls[0].url, 'http://product.test/ops/runtime-logs/summary?signal=app.exception.flutter&from=2026-04-01T00%3A00%3A00Z&to=2026-04-01T01%3A00%3A00Z');
  assert.equal(calls[1].url, 'http://product.test/ops/runtime-logs/drilldown?signal=app.exception.flutter&from=2026-04-01T00%3A00%3A00Z&to=2026-04-01T01%3A00%3A00Z&limit=5');
  assert.equal(summary.dimensions.signal['app.exception.flutter'], 4);
  assert.equal(drilldown.items[0].rowKey, 'runtime-1');
  restoreEnvAndFetch();
});

test('requests recommendation behavior metrics from content service', async () => {
  process.env.VITE_CONTENT_SERVICE_BASE_URL = 'http://content.test';
  const calls = stubFetch({
    source: 'recommendation_behavior_by_attribution_total',
    freshness: 'process_realtime',
    series: [{ labels: { state: 'click', action: 'click' }, value: 3 }],
  });

  const metrics = await fetchRecommendationBehaviorMetrics();

  assert.equal(calls[0], 'http://content.test/metrics/rec/behavior-attribution');
  assert.equal(metrics.series[0].value, 3);
  restoreEnvAndFetch();
});

test('requests effective config from platform control plane', async () => {
  process.env.VITE_PLATFORM_OPS_BASE_URL = 'http://platform.test';
  const calls = stubFetch({
    scope: { environment: 'beta', cluster: 'beta-control-a', service: 'product-ops-service' },
    resolvedAt: '2026-05-17T00:00:00Z',
    effectiveHash: 'hash-1',
    desiredHash: 'hash-1',
    values: [{ key: 'sys.api-edge.rate_limit.query.limit', value: 50, scopeLevel: 'workload', scopeId: 'api-edge', sourceLayer: 'service:api-edge' }],
    source: 'control-plane',
    driftSummary: { totalInstances: 1, inSyncInstances: 1, outOfSyncInstances: 0 },
  });

  const payload = await fetchEffectiveConfig({ env: 'beta', cluster: 'beta-control-a', service: 'product-ops-service' });

  assert.equal(calls[0], 'http://platform.test/control-plane/platform/configs/resolve?env=beta&cluster=beta-control-a&service=product-ops-service');
  assert.equal(payload.effectiveHash, 'hash-1');
  assert.equal(payload.driftSummary.totalInstances, 1);
  restoreEnvAndFetch();
});

test('requests platform triage summary from configured base url', async () => {
  process.env.VITE_PLATFORM_OPS_BASE_URL = 'http://platform.test';
  const calls = stubFetch({
    scope: { environment: 'beta', cluster: 'beta-control-a', service: 'content-service' },
    projectionSummary: { approvalCount: 2, auditCount: 4, activeAlerts: 1, releaseServices: ['content-service'] },
    configDrift: { totalInstances: 2, inSyncInstances: 1, outOfSyncInstances: 1 },
    serviceDrift: [{ service: 'content-service', totalInstances: 2, inSyncInstances: 1, outOfSyncInstances: 1 }],
    outOfSyncInstances: [{ id: 'content-service-beta-control-a-0', environment: 'beta', cluster: 'beta-control-a', service: 'content-service', instanceId: 'content-service-beta-control-a-0', inSync: false }],
    backlogCandidates: [{ id: 'platform-config-drift-content-service', category: 'config_drift', severity: 'critical', title: '修复配置漂移', nextAction: '打开 /platform/config/drift', drilldownRoute: '/platform/config/drift', repairEntry: '/platform/rollout', alertId: 'config_release_error_rate', auditRoute: '/audit' }],
    runtimeReady: false,
    source: 'control-plane',
  });

  const payload = await fetchPlatformTriageSummary({ env: 'beta', cluster: 'beta-control-a', service: 'content-service' });

  assert.equal(calls[0], 'http://platform.test/control-plane/platform/triage/summary?env=beta&cluster=beta-control-a&service=content-service');
  assert.equal(payload.configDrift.outOfSyncInstances, 1);
  assert.equal(payload.backlogCandidates[0].id, 'platform-config-drift-content-service');
  restoreEnvAndFetch();
});

test('requests core platform rollout supporting resources from configured base url', async () => {
  process.env.VITE_PLATFORM_OPS_BASE_URL = 'http://platform.test';
  const calls = stubFetchSequence([
    { payload: { items: [{ releaseId: 'v2026.02.28.0', service: 'content-service', configPath: '/tmp/config.yaml', grayStages: [5, 25, 50, 100], releaseState: 'rolling_out', stageState: 'ack_pending' }] } },
    { payload: { items: [{ auditId: 'a1', objectType: 'config_release', objectId: 'content-service', action: 'config_release_applied', dangerLevel: 'high', actor: 'platform-admin', environment: 'beta', requestId: 'req-1', traceId: 'trace-1', at: '2026-06-08T00:00:00Z' }] } },
    { payload: { items: [{ objectType: 'config_release', objectId: 'content-service', mode: 'dual', actor: 'platform-admin', decision: 'approved', at: '2026-06-08T00:00:00Z' }] } },
    { payload: { approvalCount: 1, auditCount: 1, activeAlerts: 0, releaseServices: ['content-service'] } },
    { payload: { items: [{ id: 'content-service-beta-control-a-0', environment: 'beta', cluster: 'beta-control-a', service: 'content-service', instanceId: 'content-service-beta-control-a-0', inSync: false }], summary: { totalInstances: 1, inSyncInstances: 0, outOfSyncInstances: 1 } } },
  ]);

  const [releases, audits, approvals, summary, reports] = await Promise.all([
    fetchReleases(),
    fetchPlatformAudits(),
    fetchPlatformApprovals(),
    fetchPlatformProjectionSummary(),
    fetchPlatformConfigInstanceReports(),
  ]);

  assert.equal(calls[0].url, 'http://platform.test/control-plane/platform/releases');
  assert.equal(releases[0].stageState, 'ack_pending');
  assert.equal(audits[0].action, 'config_release_applied');
  assert.equal(approvals[0].decision, 'approved');
  assert.equal(summary.releaseServices[0], 'content-service');
  assert.equal(reports.summary.outOfSyncInstances, 1);
  restoreEnvAndFetch();
});

test('requests l1l4 metrics from product control plane', async () => {
  process.env.VITE_PRODUCT_OPS_BASE_URL = 'http://product.test';
  const calls = stubFetch({
    scope: { env: 'beta' },
    source: 'live-telemetry',
    freshness: '2026-06-08T01:00:00Z',
    window: '24h',
    coverage: { totalMetrics: 4, liveMetrics: 4, unavailableMetrics: 0, eventSignals: 18 },
    alerts: [
      { id: 'L3HttpRequestP95High', state: 'firing', metric: 'http_request_p95_ms', source: 'telemetry', runbookRoute: '/platform/runbook', repairEntry: '/product/l1-l4/environment', alertId: 'HighP95Latency', auditRoute: '/audit', owner: 'app-observability' },
    ],
    items: [{ id: 'L1:beta', level: 'L1', environment: 'beta', label: '五栏主旅程完成率', metric: 'five_tab_journey_completion_rate', value: 82.4, unit: '%', status: 'success', trend: '+2.1%', description: 'ok', source: 'telemetry' }],
  });

  const payload = await fetchProductL1L4Metrics({ env: 'beta' });

  assert.equal(calls[0], 'http://product.test/control-plane/product/metrics/l1l4?env=beta');
  assert.equal(payload.items[0].level, 'L1');
  assert.equal(payload.source, 'live-telemetry');
  assert.equal(payload.alerts[0].state, 'firing');
  assert.equal(payload.alerts[0].runbookRoute, '/platform/runbook');
  assert.equal(payload.alerts[0].repairEntry, '/product/l1-l4/environment');
  assert.equal(payload.alerts[0].auditRoute, '/audit');
  restoreEnvAndFetch();
});

test('requests product triage summary from configured base url', async () => {
  process.env.VITE_PRODUCT_OPS_BASE_URL = 'http://product.test';
  const calls = stubFetch({
    projectionSummary: {
      workflowCount: 5,
      approvalCount: 4,
      auditCount: 6,
      pendingDualReview: 2,
      activeObjectTypes: ['moderation_case', 'experiment'],
      l1l4Cards: [{ level: 'L1', label: '产品旅程', metric: 'five_tab_journey_completion_rate' }],
    },
    eventSummary: {
      totalCount: 12,
      sessionCount: 5,
      dimensions: { pageName: { home: 8 }, eventType: { page_open: 8 } },
    },
    visitSummary: { totalVisits: 2, items: [] },
    topEventHotspots: { pageName: [{ value: 'home', count: 8 }] },
    recentEvents: [{ rowKey: 'row-open', logType: 'event', eventType: 'page_open', sessionId: 's.***.1', occurredAt: '2026-06-08T01:00:00Z', pageName: 'home' }],
    backlogCandidates: [{ id: 'product-event-dimension-gap', category: 'telemetry_gap', severity: 'critical', title: '补齐事件维度覆盖', nextAction: '检查 page_access / event 上报链路', drilldownRoute: '/product/dashboard', runbookRoute: '/platform/runbook', repairEntry: '/product/dashboard', alertId: 'OpsEventUploadDrop', auditRoute: '/audit' }],
    runtimeReady: false,
    source: 'control-plane',
  });

  const payload = await fetchProductTriageSummary({ pageName: 'home', appVersion: '1.0.0' });

  assert.equal(calls[0], 'http://product.test/control-plane/product/triage/summary?pageName=home&appVersion=1.0.0');
  assert.equal(payload.eventSummary.totalCount, 12);
  assert.equal(payload.backlogCandidates[0].id, 'product-event-dimension-gap');
  assert.equal(payload.source, 'control-plane');
  restoreEnvAndFetch();
});

test('throws RuntimeError when base url is missing', async () => {
  process.env.VITE_PLATFORM_OPS_BASE_URL = '';

  await assert.rejects(
    () => fetchServiceCatalog(),
    (error) => {
      assert.equal(error.name, 'RuntimeError');
      assert.equal(error.failure.code, 'OPS.CONFIG.base_url_missing');
      return true;
    },
  );
  restoreEnvAndFetch();
});

test('throws structured RuntimeError from non-2xx response', async () => {
  process.env.VITE_PLATFORM_OPS_BASE_URL = 'http://platform.test';
  globalThis.fetch = async () => ({
    ok: false,
    status: 503,
    headers: new Headers({
      'X-Request-Id': 'req-1',
      'X-Trace-Id': 'trace-1',
    }),
    text: async () => '',
  });

  await assert.rejects(
    () => fetchServiceCatalog(),
    (error) => {
      assert.equal(error.name, 'RuntimeError');
      assert.equal(error.failure.code, 'OPS.UNAVAILABLE.control_plane_unavailable');
      assert.equal(error.requestId, 'req-1');
      assert.equal(error.traceId, 'trace-1');
      return true;
    },
  );
  restoreEnvAndFetch();
});

test('wraps fetch failures as RuntimeError', async () => {
  process.env.VITE_PLATFORM_OPS_BASE_URL = 'http://platform.test';
  globalThis.fetch = async () => {
    throw new TypeError('network down');
  };

  await assert.rejects(
    () => fetchServiceCatalog(),
    (error) => {
      assert.equal(error.name, 'RuntimeError');
      assert.equal(error.failure.code, 'OPS.NETWORK.fetch_failed');
      assert.equal(error.failure.context.attributes.at(-1).value, 'network down');
      return true;
    },
  );
  restoreEnvAndFetch();
});

test('wraps successful response JSON failures as RuntimeError', async () => {
  process.env.VITE_PLATFORM_OPS_BASE_URL = 'http://platform.test';
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    headers: new Headers({
      'X-Request-Id': 'req-json',
      'X-Trace-Id': 'trace-json',
    }),
    json: async () => {
      throw new SyntaxError('bad json');
    },
  });

  await assert.rejects(
    () => fetchServiceCatalog(),
    (error) => {
      assert.equal(error.name, 'RuntimeError');
      assert.equal(error.failure.code, 'OPS.CONTRACT.invalid_json_response');
      assert.equal(error.requestId, 'req-json');
      assert.equal(error.traceId, 'trace-json');
      return true;
    },
  );
  restoreEnvAndFetch();
});
