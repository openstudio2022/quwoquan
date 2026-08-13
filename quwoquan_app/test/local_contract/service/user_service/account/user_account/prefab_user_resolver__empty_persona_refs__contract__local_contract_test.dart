// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#req-004
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import '../../../../../support/service/user_service/account/user_account/fixture_user_resolver.dart';

void main() {
  test('shared user without persona refs falls back to its user id', () {
    const userId = 'fixture_user_photo';

    expect(FixtureUserResolver.resolvePersonaId(userId), userId);
    expect(
      FixtureUserResolver.profileWireFor(userId),
      containsPair('personaId', userId),
    );
  });

  test(
    'canonical identity is available without a repository working directory',
    () async {
      final originalDirectory = Directory.current;
      final isolatedDirectory = await Directory.systemTemp.createTemp(
        'qwq_canonical_fixture_identity_',
      );
      addTearDown(() async {
        Directory.current = originalDirectory;
        await isolatedDirectory.delete(recursive: true);
      });
      Directory.current = isolatedDirectory;

      expect(FixtureUserResolver.currentUserVariantUserId, isNotEmpty);
      expect(
        FixtureUserResolver.profileWireFor(
          FixtureUserResolver.currentUserVariantPersonaId,
        ),
        isNotNull,
      );
    },
  );
}
