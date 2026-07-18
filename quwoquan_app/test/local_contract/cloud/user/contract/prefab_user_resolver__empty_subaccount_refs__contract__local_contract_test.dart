import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/prefab_user_resolver.dart';

void main() {
  test('shared user without persona refs falls back to its user id', () {
    const userId = 'fixture_user_photo';

    expect(PrefabUserResolver.resolveSubAccountId(userId), userId);
    expect(
      PrefabUserResolver.profileWireFor(userId),
      containsPair('subAccountId', userId),
    );
  });
}
