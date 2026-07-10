import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/prefab_user_resolver.dart';
import 'package:quwoquan_app/core/auth/mock_session_identity.dart';

Map<String, dynamic> _loadFixture(String metadataRelativePath) {
  const roots = <String>[
    '../quwoquan_service/contracts/metadata/',
    'quwoquan_service/contracts/metadata/',
    '../../quwoquan_service/contracts/metadata/',
  ];
  for (final root in roots) {
    final file = File('$root$metadataRelativePath');
    if (file.existsSync()) {
      return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    }
  }
  throw StateError(
    'contract fixture 缺失: $metadataRelativePath, cwd=${Directory.current.path}',
  );
}

void main() {
  test('travel_photo_1k currentUserVariant 槽位使用正式 user/subAccount ID', () {
    expect(
      PrefabUserResolver.resolveUserId('fixture_user_current'),
      PrefabUserResolver.currentUserVariantUserId,
    );
    expect(
      PrefabUserResolver.resolveSubAccountId('fixture_user_current'),
      PrefabUserResolver.currentUserVariantSubAccountId,
    );
    expect(
      kMockCurrentSubAccountId,
      PrefabUserResolver.currentUserVariantSubAccountId,
    );
    expect(kMockCurrentOwnerId, PrefabUserResolver.currentUserVariantUserId);
  });

  test('travel_photo_1k creator profile wire 分离 owner/subAccount', () {
    final fixture = _loadFixture(
      '_shared/test_fixtures/user_pool.creator_pool.travel_photo_1k_v1.json',
    );
    final users = (fixture['users'] as List)
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .where((user) => user['userId'] != 'fixture_user_current')
        .take(20)
        .toList(growable: false);

    expect(users.length, 20);
    for (final user in users) {
      final userId = user['userId'] as String;
      final subAccountId = user['subAccountId'] as String;
      final wire = PrefabUserResolver.creatorProfileWireFor(subAccountId);

      expect(wire, isNotNull);
      expect(wire!['ownerUserId'], userId);
      expect(wire['subAccountId'], subAccountId);
      expect(wire['displayName'], user['displayName']);
      expect(
        PrefabUserResolver.resolveSubAccountId(subAccountId),
        subAccountId,
      );
      expect(PrefabUserResolver.isOwnerLikeSubAccountId(subAccountId), isFalse);
    }
  });
}
