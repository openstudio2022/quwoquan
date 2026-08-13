import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const pagePath = new URL('./ProductL1L4MetricsPage.tsx', import.meta.url);

test('l1-l4 metrics page reads real metric projections through typed clients', async () => {
  const source = await readFile(pagePath, 'utf8');

  for (const operation of ['fetchProductL1L4Metrics', 'fetchServiceRouteRED']) {
    assert.match(source, new RegExp(`\\b${operation}\\b`));
  }
  assert.doesNotMatch(source, /\bfetch\s*\(/);
  assert.doesNotMatch(source, /['"`]\/control-plane/);
});

test('alert block distinguishes unavailable projection from a genuinely quiet state', async () => {
  const source = await readFile(pagePath, 'utf8');

  // 投影不可用时禁止伪装安静（quiet/success 只允许在真实空告警下出现）。
  assert.match(source, /metricsPayload == null \?/);
  assert.match(source, /告警投影不可用/);
  assert.match(source, /badge--warning">unavailable/);
  assert.match(source, /metricsPayload\.alerts\.length === 0 \?/);
  // quiet 分支必须以 payload 存在为前提。
  const unavailableIndex = source.indexOf('告警投影不可用');
  const quietIndex = source.indexOf('暂无实时告警');
  assert.ok(unavailableIndex > 0 && quietIndex > unavailableIndex);
});
