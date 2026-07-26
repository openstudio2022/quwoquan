// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#req-004
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock_identity.dart';

void main() {
  test('shared user without persona refs falls back to its user id', () {
    const userId = 'fixture_user_photo';

    expect(AlphaFixtureUserResolver.resolveSubAccountId(userId), userId);
    expect(
      AlphaFixtureUserResolver.profileWireFor(userId),
      containsPair('subAccountId', userId),
    );
  });

  test(
    'alpha identity is available without a repository working directory',
    () async {
      final originalDirectory = Directory.current;
      final isolatedDirectory = await Directory.systemTemp.createTemp(
        'qwq_alpha_fixture_identity_',
      );
      addTearDown(() async {
        Directory.current = originalDirectory;
        await isolatedDirectory.delete(recursive: true);
      });
      Directory.current = isolatedDirectory;

      expect(AlphaFixtureUserResolver.currentUserVariantUserId, isNotEmpty);
      expect(
        AlphaFixtureUserResolver.profileWireFor(
          AlphaFixtureUserResolver.currentUserVariantSubAccountId,
        ),
        isNotNull,
      );
    },
  );
}
