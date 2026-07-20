import assert from 'node:assert/strict';
import test from 'node:test';

import { buildMenuGroups } from '../../../.test-dist/shared/layout/PortalLayout.js';

function flatten(groups) {
  return groups.flatMap(({ root, children }) => [
    root,
    ...children.flatMap(({ child, grandchildren }) => [
      child,
      ...grandchildren,
    ]),
  ]);
}

test('portal menu is filtered by generated permission scope', () => {
  const granted = new Set(['ops.platform.config.read']);
  const items = flatten(buildMenuGroups((permission) => granted.has(permission)));

  assert.ok(items.length > 0, 'config permission should expose at least one menu item');
  assert.ok(
    items.every((item) => item.permission_scope === 'ops.platform.config.read'),
    'no menu outside the verified token scope may be rendered',
  );
});

test('portal menu is empty without any permission', () => {
  assert.deepEqual(buildMenuGroups(() => false), []);
});
