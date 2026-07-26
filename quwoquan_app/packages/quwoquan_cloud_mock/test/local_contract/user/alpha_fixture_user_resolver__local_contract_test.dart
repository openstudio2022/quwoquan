// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#req-004
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock_identity.dart';
import 'package:test/test.dart';

void main() {
  group('AlphaFixtureUserResolver', () {
    test('resolves the current identity from the immutable bundle', () {
      final ownerId = AlphaFixtureUserResolver.currentUserVariantUserId;
      final subAccountId =
          AlphaFixtureUserResolver.currentUserVariantSubAccountId;

      expect(ownerId, isNotEmpty);
      expect(subAccountId, isNotEmpty);
      expect(AlphaFixtureUserResolver.resolveUserId(subAccountId), ownerId);
      expect(
        AlphaFixtureUserResolver.profileWireFor(subAccountId),
        containsPair('ownerUserId', ownerId),
      );
    });

    test('does not fabricate a profile for an unknown identity', () {
      const unknownUserId = 'alpha_unknown_user';

      expect(
        AlphaFixtureUserResolver.resolveSubAccountId(unknownUserId),
        unknownUserId,
      );
      expect(AlphaFixtureUserResolver.profileWireFor(unknownUserId), isNull);
    });
  });
}
