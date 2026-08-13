import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const pagePath = new URL('./PortalLoginPage.tsx', import.meta.url);

test('login page delegates the whole flow to the OIDC portal auth hook', async () => {
  const source = await readFile(pagePath, 'utf8');
  assert.match(source, /usePortalAuth\(\)/);
  assert.match(source, /login\(\)/);
  // 登录页不得自造凭据面：无裸 fetch、无 token 拼装、无本地密钥写入。
  assert.doesNotMatch(source, /\bfetch\s*\(/);
  assert.doesNotMatch(source, /localStorage\.setItem/);
  assert.doesNotMatch(source, /client_secret/);
});
