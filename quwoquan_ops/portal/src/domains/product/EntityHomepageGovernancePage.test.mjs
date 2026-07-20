import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const pagePath = new URL('./EntityHomepageGovernancePage.tsx', import.meta.url);
const appPath = new URL('../../app/App.tsx', import.meta.url);

test('entity homepage governance page closes all three governance queues', async () => {
  const source = await readFile(pagePath, 'utf8');

  for (const operation of [
    'fetchHomepageCandidates',
    'intakeHomepageCandidate',
    'publishHomepageCandidate',
    'fetchHomepageClaimRequests',
    'reviewHomepageClaimRequest',
    'fetchHomepageStatusReports',
    'reviewHomepageStatusReport',
  ]) {
    assert.match(source, new RegExp(`\\b${operation}\\b`));
  }
  assert.match(source, /必须填写审核意见/);
  assert.doesNotMatch(source, /\bfetch\s*\(/);
  assert.doesNotMatch(source, /['"`]\/homepages/);
});

test('entity homepage governance route comes from generated portal metadata', async () => {
  const source = await readFile(appPath, 'utf8');

  assert.match(source, /portalRoutePath\('entity-homepage-governance'\)/);
  assert.doesNotMatch(
    source,
    /path=["']\/product\/entity-homepage-governance["']/,
  );
});
