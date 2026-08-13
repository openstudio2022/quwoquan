import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const pagePath = new URL('./OverviewDashboardPage.tsx', import.meta.url);

test('overview dashboard reads every block from typed control-plane clients', async () => {
  const source = await readFile(pagePath, 'utf8');

  for (const operation of [
    'fetchPlatformAudits',
    'fetchProductWorkflows',
    'fetchReleases',
    'fetchProductProjectionSummary',
    'fetchProductEventSummary',
    'fetchRecommendationBehaviorMetrics',
    'fetchProductEventDrilldown',
    'fetchProductL1L4Metrics',
    'fetchExperiments',
    'fetchGrowthOverview',
  ]) {
    assert.match(source, new RegExp(`\\b${operation}\\b`));
  }
  // 页面不得绕过 typed client 裸 fetch 或硬编码控制面路径。
  assert.doesNotMatch(source, /\bfetch\s*\(/);
  assert.doesNotMatch(source, /['"`]\/control-plane/);
});

test('running experiment KPI counts the real experiment catalog, not workflow objects', async () => {
  const source = await readFile(pagePath, 'utf8');

  assert.match(source, /experiments\.filter\(\(item\) => item\.status === 'running'\)/);
  // 语义错位回归：不得再用 workflow objectType 冒充实验运行数。
  assert.doesNotMatch(
    source,
    /workflows\.filter\(\(item\) => item\.objectType === 'experiment'\)/,
  );
});

test('moderation load renders an honest snapshot instead of a single-point fake trend', async () => {
  const source = await readFile(pagePath, 'utf8');

  // 单点伪时序回归：控制面工作流只有当前快照，禁止造 day:'now' 趋势图。
  assert.doesNotMatch(source, /moderationTrend/);
  assert.doesNotMatch(source, /day: 'now'/);
  assert.match(source, /moderationSnapshot/);
  assert.match(source, /治理负载快照/);
  // 真实时序图只允许消费 Growth 的按日数据。
  assert.match(source, /AreaChart data=\{growth\?\.days \?\? \[\]\}/);
});
