import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const pagePath = new URL('./AccountEnforcementPage.tsx', import.meta.url);
const appPath = new URL('../../app/App.tsx', import.meta.url);

test('account enforcement page drives dual-sign review through typed case client', async () => {
  const source = await readFile(pagePath, 'utf8');

  for (const operation of [
    'fetchAccountEnforcementCase',
    'reviewAccountEnforcementCase',
    'retryAccountEnforcementDelivery',
  ]) {
    assert.match(source, new RegExp(`\\b${operation}\\b`));
  }
  // 双签复核动作只在 pending_approval 态可用，其余状态禁用。
  assert.match(source, /disabled=\{caseView\.status !== 'pending_approval'\}/);
  // 双签进度以 approvalCount/2 显式呈现。
  assert.match(source, /approvals=\{caseView\.approvalCount\}\/2/);
  // 未取得真实事实不合成状态；处置真相源不在 Portal。
  assert.match(source, /未取得真实事实时不显示合成状态/);
  assert.match(source, /不落第二处置真相源/);
  // 不得裸 fetch 或硬编码控制面路径。
  assert.doesNotMatch(source, /\bfetch\s*\(/);
  assert.doesNotMatch(source, /['"`]\/control-plane/);
});

test('account enforcement route comes from generated portal metadata', async () => {
  const source = await readFile(appPath, 'utf8');

  assert.match(source, /portalRoutePath\('account-enforcement'\)/);
  assert.doesNotMatch(source, /path=["']\/product\/account-enforcement["']/);
});
