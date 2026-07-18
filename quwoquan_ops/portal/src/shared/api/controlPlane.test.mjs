import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applyPlatformRelease,
  fetchEffectiveConfig,
  fetchOnboardingDomains,
  fetchPlatformConfigInstanceReports,
  fetchPlatformProjectionSummary,
  fetchReleases,
  fetchRunbooks,
  fetchGateRules,
  fetchPlatformAudits,
  fetchPlatformApprovals,
  fetchPlatformTriageSummary,
  fetchProductEventDrilldown,
  fetchProductEventSummary,
  fetchProductL1L4Metrics,
  fetchProductTriageSummary,
  fetchProductProjectionSummary,
  fetchRecommendationBehaviorMetrics,
  fetchReports,
  rollbackPlatformRelease,
  fetchServiceCatalog,
} from '../../../.test-dist/shared/api/controlPlane.js';

const originalFetch = globalThis.fetch;
const originalPlatformBaseUrl = process.env.VITE_PLATFORM_OPS_BASE_URL;
const originalProductBaseUrl = process.env.VITE_PRODUCT_OPS_BASE_URL;
const originalContentServiceBaseUrl = process.env.VITE_CONTENT_SERVICE_BASE_URL;

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

  assert.equal(calls[0], 'http://content.test/content/reports?limit=10');
  assert.equal(items[0].id, 'rpt-1');
  assert.equal(items[0].version, 1);
  restoreEnvAndFetch();
});

test('requests onboarding domains from platform control plane', async () => {
  process.env.VITE_PLATFORM_OPS_BASE_URL = 'http://platform.test';
  const calls = stubFetch({
    items: [
      {
        domain: 'content',
        display_name: 'Content',
        template_role: 'template_seed',
        rollout_group: 'wave_0_template',
        acceptance_status: 'minimum_test_ready',
        metadata_paths: ['content/post'],
        service_names: ['content-service'],
        control_planes: {
          platform: { enabled: true, object_types: ['service_catalog_entry'], config_prefixes: ['sys.content.'] },
          product: { enabled: true, object_types: ['moderation_case'], config_prefixes: ['ops.content.'] },
        },
        minimum_package: {
          metadata_files: ['contracts/metadata/content/post/service.yaml'],
          codegen_targets: ['go_runtime', 'python_runtime', 'ops_portal'],
          test_evidence: { t1: ['a'], t2: ['b'], t3: [], t4: [] },
        },
        deployment: {
          plane_binding_domain: 'content',
          plane_binding_source: 'quwoquan_ops/environments/process_domain_plane_mapping.yaml',
          current_binding_source: 'quwoquan_ops/environments/process_domain_mapping.yaml',
        },
        replication: { source_template: 'content', next_copy_targets: ['chat'], copy_notes: ['seed'] },
        blocking_gaps: [],
      },
    ],
  });

  const items = await fetchOnboardingDomains();

  assert.equal(calls[0], 'http://platform.test/control-plane/platform/onboarding/domains');
  assert.equal(items[0].domain, 'content');
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

test('requests product event summary from configured base url', async () => {
  process.env.VITE_PRODUCT_OPS_BASE_URL = 'http://product.test';
  const calls = stubFetch({
    totalCount: 12,
    sessionCount: 5,
    dimensions: { pageName: { home: 8 } },
  });

  const summary = await fetchProductEventSummary({ eventType: 'page_open', from: '2026-04-01T00:00:00Z', to: '2026-04-02T00:00:00Z' });

  assert.equal(calls[0], 'http://product.test/ops/events/summary?eventType=page_open&from=2026-04-01T00%3A00%3A00Z&to=2026-04-02T00%3A00%3A00Z');
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
    values: [{ key: 'sys.gateway.rate_limit.per_user_rps', value: 50, scopeLevel: 'service', scopeId: 'product-ops-service', sourceLayer: 'service:product-ops-service' }],
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
    projectionSummary: { approvalCount: 2, auditCount: 4, runbookCount: 3, releaseServices: ['content-service'] },
    configDrift: { totalInstances: 2, inSyncInstances: 1, outOfSyncInstances: 1 },
    serviceDrift: [{ service: 'content-service', totalInstances: 2, inSyncInstances: 1, outOfSyncInstances: 1 }],
    outOfSyncInstances: [{ id: 'content-service-beta-control-a-0', environment: 'beta', cluster: 'beta-control-a', service: 'content-service', instanceId: 'content-service-beta-control-a-0', inSync: false }],
    backlogCandidates: [{ id: 'platform-config-drift-content-service', category: 'config_drift', severity: 'critical', title: '修复配置漂移', nextAction: '打开 /platform/config/drift', drilldownRoute: '/platform/config/drift', runbookRoute: '/platform/runbook', repairEntry: '/platform/rollout', alertId: 'config_release_error_rate', auditRoute: '/audit' }],
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
    { payload: { items: [{ id: 'config_release_error_rate', rule: 'config_release_error_rate', stage: '25%', status: 'success', summary: 'ok' }] } },
    { payload: { items: [{ id: 'cfg-rollback-drill', title: '配置发布回滚演练', subtitle: 'desc', status: 'success', runbookRoute: '/platform/runbook', auditRoute: '/audit' }] } },
    { payload: { items: [{ auditId: 'a1', objectType: 'config_release', objectId: 'content-service', action: 'config_release_applied', dangerLevel: 'high', actor: 'platform-admin', environment: 'beta', requestId: 'req-1', traceId: 'trace-1', at: '2026-06-08T00:00:00Z' }] } },
    { payload: { items: [{ objectType: 'config_release', objectId: 'content-service', mode: 'dual', actor: 'platform-admin', decision: 'approved', at: '2026-06-08T00:00:00Z' }] } },
    { payload: { approvalCount: 1, auditCount: 1, runbookCount: 1, releaseServices: ['content-service'] } },
    { payload: { items: [{ id: 'content-service-beta-control-a-0', environment: 'beta', cluster: 'beta-control-a', service: 'content-service', instanceId: 'content-service-beta-control-a-0', inSync: false }], summary: { totalInstances: 1, inSyncInstances: 0, outOfSyncInstances: 1 } } },
  ]);

  const [releases, gates, runbooks, audits, approvals, summary, reports] = await Promise.all([
    fetchReleases(),
    fetchGateRules(),
    fetchRunbooks(),
    fetchPlatformAudits(),
    fetchPlatformApprovals(),
    fetchPlatformProjectionSummary(),
    fetchPlatformConfigInstanceReports(),
  ]);

  assert.equal(calls[0].url, 'http://platform.test/control-plane/platform/releases');
  assert.equal(releases[0].stageState, 'ack_pending');
  assert.equal(gates[0].id, 'config_release_error_rate');
  assert.equal(runbooks[0].id, 'cfg-rollback-drill');
  assert.equal(audits[0].action, 'config_release_applied');
  assert.equal(approvals[0].decision, 'approved');
  assert.equal(summary.releaseServices[0], 'content-service');
  assert.equal(reports.summary.outOfSyncInstances, 1);
  restoreEnvAndFetch();
});

test('posts platform release workflow mutations to configured base url', async () => {
  process.env.VITE_PLATFORM_OPS_BASE_URL = 'http://platform.test';
  const calls = stubFetchSequence([
    {
      payload: {
        releaseId: 'v2026.02.28.0',
        service: 'content-service',
        releaseState: 'rolling_out',
        approvalState: 'approved',
        stageState: 'ack_pending',
        workflowRef: 'config_release_workflow_content-service',
        rollbackToken: 'rbk-content-service-v2026.02.28.0',
        ackSummary: { totalInstances: 2, inSyncInstances: 1, outOfSyncInstances: 1 },
      },
    },
    {
      payload: {
        releaseId: 'v2026.02.28.0',
        service: 'content-service',
        releaseState: 'rolled_back',
        stageState: 'rolled_back',
        workflowRef: 'config_release_workflow_content-service',
        rollbackToken: 'rbk-content-service-v2026.02.28.0',
        ackSummary: { totalInstances: 2, inSyncInstances: 2, outOfSyncInstances: 0 },
      },
    },
  ]);

  const applyPayload = await applyPlatformRelease('v2026.02.28.0', {
    service: 'content-service',
    fromImage: '1.0.0',
    toImage: '1.0.1',
    fromConfig: 'v2026.02.27.1',
    toConfig: 'v2026.02.28.0',
    step: 25,
  });
  const rollbackPayload = await rollbackPlatformRelease('v2026.02.28.0', {
    service: 'content-service',
    targetConfigVersion: 'v2026.02.27.1',
    workflowRef: applyPayload.workflowRef,
    rollbackToken: applyPayload.rollbackToken,
  });

  assert.equal(calls[0].url, 'http://platform.test/control-plane/platform/releases/v2026.02.28.0:apply');
  assert.equal(calls[0].init?.method, 'POST');
  assert.match(String(calls[0].init?.body), /"service":"content-service"/);
  assert.equal(applyPayload.stageState, 'ack_pending');

  assert.equal(calls[1].url, 'http://platform.test/control-plane/platform/releases/v2026.02.28.0:rollback');
  assert.equal(calls[1].init?.method, 'POST');
  assert.match(String(calls[1].init?.body), /"rollbackToken":"rbk-content-service-v2026.02.28.0"/);
  assert.equal(rollbackPayload.releaseState, 'rolled_back');
  restoreEnvAndFetch();
});

test('requests l1l4 metrics from product control plane', async () => {
  process.env.VITE_PRODUCT_OPS_BASE_URL = 'http://product.test';
  const calls = stubFetch({
    scope: { env: 'beta' },
    source: 'live-telemetry',
    freshness: '2026-06-08T01:00:00Z',
    window: '24h',
    coverage: { totalMetrics: 4, liveMetrics: 4, fallbackMetrics: 0, eventSignals: 18 },
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
