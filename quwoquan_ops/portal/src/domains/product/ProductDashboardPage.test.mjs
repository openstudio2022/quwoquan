import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const pagePath = new URL('./ProductDashboardPage.tsx', import.meta.url);

test('product dashboard reads every card from typed control-plane clients', async () => {
  const source = await readFile(pagePath, 'utf8');
  for (const operation of [
    'fetchPageExperience',
    'fetchPremiumPoolEntries',
    'fetchProductEventSummary',
    'fetchProductL1L4Metrics',
    'fetchProductProjectionSummary',
    'fetchRtcMediaQoeSummary',
    'fetchProductTriageSummary',
    'fetchProductWorkflows',
    'fetchReports',
  ]) {
    assert.match(source, new RegExp(`\\b${operation}\\b`));
  }
  assert.doesNotMatch(source, /\bfetch\s*\(/);
  assert.doesNotMatch(source, /['"`]\/control-plane/);
  // 页面不得合成假数字：不存在 Math.random 或硬编码演示数组。
  assert.doesNotMatch(source, /Math\.random/);
});
