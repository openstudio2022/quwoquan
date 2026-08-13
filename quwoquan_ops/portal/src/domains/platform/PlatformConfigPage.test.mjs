import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const pagePath = new URL('./PlatformConfigPage.tsx', import.meta.url);

test('config page reads IaC-backed configuration through typed clients only', async () => {
  const source = await readFile(pagePath, 'utf8');
  for (const operation of [
    'fetchConfigDomains',
    'fetchConfigSnapshot',
    'fetchEffectiveConfig',
    'fetchPlatformConfigInstanceReports',
    'fetchPlatformConfigKeys',
  ]) {
    assert.match(source, new RegExp(`\\b${operation}\\b`));
  }
  assert.doesNotMatch(source, /\bfetch\s*\(/);
  assert.doesNotMatch(source, /['"`]\/control-plane/);
});
