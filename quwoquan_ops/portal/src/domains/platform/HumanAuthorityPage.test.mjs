import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const pagePath = new URL('./HumanAuthorityPage.tsx', import.meta.url);
const appPath = new URL('../../app/App.tsx', import.meta.url);
const menuPath = new URL('../../../../../quwoquan_service/contracts/metadata/_control_plane/portal_menu.yaml', import.meta.url);
const generatedMenuPath = new URL('../../generated/control-plane/portalMenu.generated.ts', import.meta.url);
const stylesPath = new URL('../../styles.css', import.meta.url);

async function sources() {
  return Promise.all([
    readFile(pagePath, 'utf8'),
    readFile(appPath, 'utf8'),
    readFile(menuPath, 'utf8'),
    readFile(generatedMenuPath, 'utf8'),
    readFile(stylesPath, 'utf8'),
  ]);
}

test('delivery decision menu and route use canonical generated metadata', async () => {
  const [, app, menu, generatedMenu] = await sources();

  assert.match(menu, /menu_id: platform-delivery-decision/);
  assert.match(menu, /label: 交付决策/);
  assert.match(menu, /permission_scope: ops\.platform\.delivery_decision\.read/);
  assert.match(generatedMenu, /"menu_id": "platform-delivery-decision"/);
  assert.match(app, /portalRoutePath\('platform-delivery-decision'\)/);
  assert.doesNotMatch(app, /path=["']\/platform\/delivery-decision["']/);
});

test('page consumes typed authority API and never executes delivery effects', async () => {
  const [page] = await sources();

  for (const operation of [
    'fetchHumanAuthorityDecisionUnits',
    'submitHumanAuthorityRound',
    'applyHumanAuthorityAction',
    'fetchHumanAuthorityReadback',
  ]) {
    assert.match(page, new RegExp(`\\b${operation}\\b`));
  }
  assert.doesNotMatch(page, /\bfetch\s*\(/);
  assert.doesNotMatch(page, /['"`]\/control-plane/);
  assert.doesNotMatch(page, /\b(?:git|stackctl|kubectl)\b/i);
  assert.match(page, /不执行发布、代码或生产动作/);
  assert.match(page, /未从服务器取得职责内待办/);
});

test('permissions, wrong role recovery and SoD remain fail-closed', async () => {
  const [page] = await sources();

  assert.match(page, /ops\.platform\.delivery_decision\.read/);
  assert.match(page, /ops\.platform\.delivery_decision\.write/);
  assert.match(page, /HAD\.PERMISSION_REQUIRED/);
  assert.match(page, /RuntimeErrorBadge/);
  assert.match(page, /转交给正确负责人/);
  assert.match(page, /independent-principal-required/);
  assert.match(page, /职责分离要求/);
  assert.match(page, /页面不允许从登录信息中自报或切换角色/);
  assert.doesNotMatch(page, /claims\.roles|hasRole\(/);
});

test('options are symmetric, stable, unselected and recommendation-free for value decisions', async () => {
  const [page] = await sources();

  assert.match(page, /task\.card\.options\.map/);
  assert.match(page, /checked=\{selectedOptionId === option\.optionId\}/);
  assert.match(page, /const \[selectedOptionId, setSelectedOptionId\] = useState\(''\)/);
  assert.doesNotMatch(page, /defaultChecked/);
  assert.match(page, /没有预选，也不突出任何方案/);
  for (const field of [
    'userOutcome', 'businessOutcome', 'cost', 'timeToEffect', 'risk',
    'reversibility', 'scopeChange', 'unknowns', 'nextStep',
  ]) {
    assert.match(page, new RegExp(`option\\.${field}`));
  }
  for (const decisionKind of [
    'product_scope', 'experience_direction', 'commercial_readiness', 'outcome_acceptance',
  ]) {
    assert.match(page, new RegExp(`'${decisionKind}'`));
  }
});

test('forms keep native keyboard semantics and announce focused errors', async () => {
  const [page, , , , styles] = await sources();

  assert.match(page, /<fieldset className="human-authority-options">/);
  assert.match(page, /<legend>/);
  assert.match(page, /<label className="human-authority-option"/);
  assert.match(page, /type="radio"/);
  assert.match(page, /aria-live="assertive"/);
  assert.match(page, /aria-live="polite"/);
  assert.match(page, /errorFocusRef\.current\?\.focus\(\)/);
  assert.match(styles, /\.human-authority-option:focus-within/);
  assert.match(styles, /@media \(max-width: 768px\)/);
  assert.match(styles, /\.human-authority-options,/);
  assert.match(styles, /grid-template-columns: minmax\(0, 1fr\)/);
});

test('duplicate and network failure never become false success', async () => {
  const [page] = await sources();

  assert.match(page, /idempotencyKeysRef/);
  assert.match(page, /inFlightRef/);
  assert.match(page, /replayed/);
  assert.match(page, /服务器已确认这是重复请求/);
  assert.match(page, /提交未成功/);
  assert.match(page, /pending 或网络失败不会显示成成功/);
  assert.match(page, /刷新回读/);
});

test('internal terms are rendered only inside collapsed audit details', async () => {
  const [page] = await sources();

  assert.match(page, /<details className="human-authority-audit-details">/);
  assert.match(page, /<summary>审计详情<\/summary>/);
  assert.match(page, /JSON\.stringify\(task\.card\.auditDetails/);
  const jsx = page.slice(page.indexOf('  return ('));
  const stringLiterals = Array.from(jsx.matchAll(/(?:"([^"\n]+)"|'([^'\n]+)')/g), (match) => match[1] ?? match[2]);
  assert.doesNotMatch(stringLiterals.join(' '), /\b(?:digest|receipt|fingerprint|owner_manifest|stackctl)\b/i);
});
