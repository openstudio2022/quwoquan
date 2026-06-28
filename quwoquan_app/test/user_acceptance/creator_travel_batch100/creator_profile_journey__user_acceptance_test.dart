import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/prefab_user_resolver.dart';
import 'package:quwoquan_app/core/auth/mock_session_identity.dart';

void main() {
  test('currentUserVariant 槽位与 legacy alias 双读', () {
    expect(
      PrefabUserResolver.resolveUserId('fixture_user_current'),
      PrefabUserResolver.currentUserVariantUserId,
    );
    expect(
      PrefabUserResolver.resolveSubAccountId('fixture_user_current'),
      PrefabUserResolver.currentUserVariantSubAccountId,
    );
    expect(kMockCurrentSubAccountId, PrefabUserResolver.currentUserVariantSubAccountId);
    expect(kMockCurrentOwnerId, PrefabUserResolver.currentUserVariantUserId);
  });

  test('creator currentUserVariant profile wire 分离 owner/subAccount', () {
    final wire = PrefabUserResolver.creatorProfileWireFor(kMockCurrentSubAccountId);
    expect(wire, isNotNull);
    expect(wire!['ownerUserId'], kMockCurrentOwnerId);
    expect(wire['subAccountId'], kMockCurrentSubAccountId);
    expect(wire['displayName'], isNotEmpty);
  });

  test('creator 轨 20 人抽样 subAccountId 可解析', () {
    final sampleHandles = List<String>.generate(
      20,
      (index) => 'agent_sub_account_travel_travel_batch_100_v1_${(index + 1).toString().padLeft(3, '0')}',
    );
    for (final subAccountId in sampleHandles) {
      expect(PrefabUserResolver.resolveSubAccountId(subAccountId), subAccountId);
      expect(PrefabUserResolver.isOwnerLikeSubAccountId(subAccountId), isFalse);
    }
  });
}
