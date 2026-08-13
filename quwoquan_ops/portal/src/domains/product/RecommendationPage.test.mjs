import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const pagePath = new URL('./RecommendationPage.tsx', import.meta.url);

test('recommendation page reads premium pool and behavior metrics through typed clients', async () => {
  const source = await readFile(pagePath, 'utf8');
  for (const operation of [
    'fetchPremiumPoolEntries',
    'fetchRecommendationBehaviorMetrics',
    'rollbackPremiumPoolEntry',
  ]) {
    assert.match(source, new RegExp(`\\b${operation}\\b`));
  }
  assert.doesNotMatch(source, /\bfetch\s*\(/);
  assert.doesNotMatch(source, /['"`]\/control-plane/);
});

test('behavior attribution card states its single-replica in-process scope honestly', async () => {
  const source = await readFile(pagePath, 'utf8');
  // 行为卡读 content-service 进程内计数：口径必须明示，禁止伪装成集群聚合。
  assert.match(source, /进程内/);
  assert.match(source, /单副本口径/);
});
