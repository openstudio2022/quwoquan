import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const pagePath = new URL('./ExperimentOperationsPage.tsx', import.meta.url);
const appPath = new URL('../../app/App.tsx', import.meta.url);

test('experiment operations page mutates only through typed rollout client with weight guard', async () => {
  const source = await readFile(pagePath, 'utf8');

  for (const operation of ['fetchExperiments', 'updateExperimentRollout']) {
    assert.match(source, new RegExp(`\\b${operation}\\b`));
  }
  // 权重总和必须精确 10000，未满足时提交按钮禁用。
  assert.match(source, /TOTAL_BASIS_POINTS = 10000/);
  assert.match(source, /total === TOTAL_BASIS_POINTS/);
  assert.match(source, /disabled=\{!totalValid\}/);
  // rollout 必须带 If-Match 版本前置（经 expectedVersion 传入 typed client）。
  assert.match(source, /expectedVersion: experiment\.experimentRevision/);
  // 状态闭集来自契约枚举，未取得真实目录不合成状态。
  assert.match(source, /'draft', 'scheduled', 'running', 'paused', 'ended'/);
  assert.match(source, /未取得真实目录时不显示合成状态/);
  // 页面不得绕过 typed client 裸 fetch 或硬编码控制面路径。
  assert.doesNotMatch(source, /\bfetch\s*\(/);
  assert.doesNotMatch(source, /['"`]\/control-plane/);
});

test('experiment operations route comes from generated portal metadata', async () => {
  const source = await readFile(appPath, 'utf8');

  assert.match(source, /portalRoutePath\('experiment-operations'\)/);
  assert.doesNotMatch(source, /path=["']\/product\/experiments["']/);
});
