import assert from 'node:assert/strict';
import test from 'node:test';

import {
  fetchOnboardingDomains,
  fetchProductEventDrilldown,
  fetchProductEventSummary,
  fetchProductProjectionSummary,
  fetchServiceCatalog,
} from '../../../.test-dist/shared/api/controlPlane.js';

const originalFetch = globalThis.fetch;
const originalPlatformBaseUrl = process.env.VITE_PLATFORM_OPS_BASE_URL;
const originalProductBaseUrl = process.env.VITE_PRODUCT_OPS_BASE_URL;

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

function restoreEnvAndFetch() {
  globalThis.fetch = originalFetch;
  process.env.VITE_PLATFORM_OPS_BASE_URL = originalPlatformBaseUrl;
  process.env.VITE_PRODUCT_OPS_BASE_URL = originalProductBaseUrl;
}

test('requests platform service catalog from configured base url', async () => {
  process.env.VITE_PLATFORM_OPS_BASE_URL = 'http://platform.test';
  const calls = stubFetch({
    items: [{ id: 'content-service', service: 'content-service', plane: 'user-plane', owner: 'content-team', health: 'success', summary: 'ok' }],
  });

  const items = await fetchServiceCatalog();

  assert.equal(calls[0], 'http://platform.test/v1/control-plane/platform/catalog/services');
  assert.equal(items[0].service, 'content-service');
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
          plane_binding_source: 'deploy/shared/process_domain_plane_mapping.yaml',
          legacy_binding_source: 'deploy/shared/process_domain_mapping.yaml',
        },
        replication: { source_template: 'content', next_copy_targets: ['chat'], copy_notes: ['seed'] },
        blocking_gaps: [],
      },
    ],
  });

  const items = await fetchOnboardingDomains();

  assert.equal(calls[0], 'http://platform.test/v1/control-plane/platform/onboarding/domains');
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

  assert.equal(calls[0], 'http://product.test/v1/control-plane/product/projections/summary');
  assert.equal(summary.pendingDualReview, 2);
  restoreEnvAndFetch();
});

test('requests product event summary from configured base url', async () => {
  process.env.VITE_PRODUCT_OPS_BASE_URL = 'http://product.test';
  const calls = stubFetch({
    totalCount: 12,
    dimensions: { pageName: { home: 8 } },
  });

  const summary = await fetchProductEventSummary({ source: 'page_access' });

  assert.equal(calls[0], 'http://product.test/v1/ops/events/summary?source=page_access');
  assert.equal(summary.totalCount, 12);
  restoreEnvAndFetch();
});

test('requests product event drilldown from configured base url', async () => {
  process.env.VITE_PRODUCT_OPS_BASE_URL = 'http://product.test';
  const calls = stubFetch({
    totalCount: 1,
    items: [{ eventId: 'evt-1', eventType: 'experience', eventName: 'page_open', occurredAt: '2026-04-01T00:00:00Z' }],
  });

  const drilldown = await fetchProductEventDrilldown({ eventType: 'experience', limit: 5 });

  assert.equal(calls[0], 'http://product.test/v1/ops/events/drilldown?eventType=experience&limit=5');
  assert.equal(drilldown.items[0].eventId, 'evt-1');
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
