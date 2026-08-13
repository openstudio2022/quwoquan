import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const pagePath = new URL('./AuditPage.tsx', import.meta.url);

test('audit page reads platform and product audit trails through typed clients', async () => {
  const source = await readFile(pagePath, 'utf8');
  for (const operation of ['fetchPlatformAudits', 'fetchProductAudits']) {
    assert.match(source, new RegExp(`\\b${operation}\\b`));
  }
  assert.doesNotMatch(source, /\bfetch\s*\(/);
  assert.doesNotMatch(source, /['"`]\/control-plane/);
});
