// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
//
// DEC-033 四路投影媒体交付绑定薄改（persona 头像路）：
// `personaProfileViewDataFromWire` 必须保留契约 `PersonaProfileView` 的
// avatarAssetId 与 avatarAccessMode，缺席时为 null，不以 personaId 冒充。

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/persona_management_view_data_mapper.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

PersonaProfileView _profileView({
  String? avatarAssetId,
  MediaDeliveryAccessMode? avatarAccessMode,
}) {
  return PersonaProfileView(
    personaId: 'persona-1',
    subjectType: ProfileOwnerKind.persona,
    userHandle: 'handle-1',
    displayName: '展示名',
    nicknameCustomized: true,
    avatarUrl: 'media/avatar/s/fixture/persona-1/v1/avatar.png',
    avatarAssetId: avatarAssetId,
    avatarAccessMode: avatarAccessMode,
    followerCount: 1,
    followingCount: 2,
    postCount: 3,
    circleCount: 4,
    likeCount: 5,
    profileVisibility: ProfileVisibility.public,
    isolationLevel: IsolationLevel.open,
    inheritsFromOwner: false,
    updatedAt: DateTime.utc(2026, 8, 1),
  );
}

void main() {
  group('personaProfileViewDataFromWire — 头像交付绑定保留', () {
    test('signed_grant 绑定在场时 avatarAssetId 与 avatarAccessMode 完整透传', () {
      final dto = personaProfileViewDataFromWire(
        _profileView(
          avatarAssetId: 'asset-avatar-1',
          avatarAccessMode: MediaDeliveryAccessMode.signedGrant,
        ),
      );

      expect(dto.avatarAssetId, 'asset-avatar-1');
      expect(dto.avatarAccessMode, MediaDeliveryAccessMode.signedGrant);
      // 不以 personaId 冒充媒体资产标识。
      expect(dto.avatarAssetId, isNot(dto.personaId));
    });

    test('存量 public 投影未携带绑定字段时缺席为 null，不以 personaId 冒充', () {
      final dto = personaProfileViewDataFromWire(_profileView());

      expect(dto.avatarAssetId, isNull);
      expect(dto.avatarAccessMode, isNull);
    });

    test('mergeStats 保留头像交付绑定字段', () {
      final dto = personaProfileViewDataFromWire(
        _profileView(
          avatarAssetId: 'asset-avatar-1',
          avatarAccessMode: MediaDeliveryAccessMode.public,
        ),
      );

      final merged = dto.mergeStats(
        const UserProfileStatsViewData(
          followingCount: 10,
          circleCount: 11,
          followerCount: 12,
          likeCount: 13,
          postCount: 14,
        ),
      );

      expect(merged.avatarAssetId, 'asset-avatar-1');
      expect(merged.avatarAccessMode, MediaDeliveryAccessMode.public);
      expect(merged.followerCount, 12);
    });
  });
}
