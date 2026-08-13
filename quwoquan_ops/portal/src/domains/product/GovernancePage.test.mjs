import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const pagePath = new URL('./GovernancePage.tsx', import.meta.url);

test('governance page drives report and moderation flows through typed clients', async () => {
  const source = await readFile(pagePath, 'utf8');
  for (const operation of ['fetchReports', 'fetchCurrentPostModerationCase']) {
    assert.match(source, new RegExp(`\\b${operation}\\b`));
  }
  assert.doesNotMatch(source, /\bfetch\s*\(/);
  assert.doesNotMatch(source, /['"`]\/control-plane/);
  assert.doesNotMatch(source, /Math\.random/);
});
