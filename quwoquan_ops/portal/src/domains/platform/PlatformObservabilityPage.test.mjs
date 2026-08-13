import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const pagePath = new URL('./PlatformObservabilityPage.tsx', import.meta.url);
const catalogPath = new URL('./PlatformServiceCatalogPage.tsx', import.meta.url);

test('platform observability page reads alerts and runtime logs through typed clients', async () => {
  const source = await readFile(pagePath, 'utf8');

  for (const operation of [
    'fetchActiveAlerts',
    'fetchPlatformAudits',
    'fetchPlatformTriageSummary',
    'fetchPlatformProjectionSummary',
    'fetchRuntimeLogDrilldown',
    'fetchRuntimeLogSummary',
  ]) {
    assert.match(source, new RegExp(`\\b${operation}\\b`));
  }
  assert.doesNotMatch(source, /\bfetch\s*\(/);
  assert.doesNotMatch(source, /['"`]\/control-plane/);
});

test('service catalog labels static topology honestly instead of faking health', async () => {
  const source = await readFile(catalogPath, 'utf8');

  // 目录来自静态拓扑扫描：不得把无探测的条目渲染成健康结论。
  assert.match(source, /static_topology/);
  assert.match(source, /静态拓扑（无实时健康）/);
  assert.doesNotMatch(source, /badge--\$\{item\.health\}/);
});
