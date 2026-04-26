import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/appearance_settings_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/active_persona_context_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/call_settings_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_management_summary_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_lifecycle_guard_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_management_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/privacy_settings_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_management_quota_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_interaction_activity_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_social_relation_row_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_subject_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_user_like_row_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/relationship_capability_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/recent_search_entry_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/relationship_normalized_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/social_relation_search_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/social_relationship_capability_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_profile_stats_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/appearance_settings_repository.dart';
import 'package:quwoquan_app/cloud/services/user/call_settings_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/models/search_models.dart';

void main() {
  group('ProfileSubjectWireDto', () {
    test('userId 仅填充 profileSubjectId，不再冒充 ownerUserId', () {
      final dto = ProfileSubjectWireDto.fromMap(<String, dynamic>{
        'userId': 'u_owner',
        'nickname': 'nick',
        'followerCount': 1,
        'followingCount': 2,
        'postCount': 3,
        'circleCount': 4,
        'likeCount': 5,
      });
      expect(dto.profileSubjectId, 'u_owner');
      expect(dto.ownerUserId, isEmpty);
      expect(dto.displayName, 'nick');
    });

    test('backgroundImage 别名映射到 backgroundUrl', () {
      final dto = ProfileSubjectWireDto.fromMap(<String, dynamic>{
        'userId': 'u1',
        'backgroundImage': 'https://bg.example/x.jpg',
      });
      expect(dto.backgroundUrl, 'https://bg.example/x.jpg');
    });

    test('toMap round-trip 稳定', () {
      final dto = ProfileSubjectWireDto.fromMap(<String, dynamic>{
        'profileSubjectId': 'ps1',
        'ownerUserId': 'o1',
        'subAccountId': '',
        'userHandle': 'handle_1',
        'nickname': 'n',
        'displayName': 'd',
        'username': 'u',
        'subjectType': 'user',
        'avatarUrl': '',
        'backgroundUrl': '',
        'bio': '',
        'followerCount': 0,
        'followingCount': 0,
        'postCount': 0,
        'circleCount': 0,
        'likeCount': 0,
        'profileVisibility': 'public',
        'inheritsFromOwner': false,
      });
      final restored = ProfileSubjectWireDto.fromMap(dto.toMap());
      expect(restored.profileSubjectId, dto.profileSubjectId);
      expect(restored.userHandle, 'handle_1');
      expect(restored.followerCount, dto.followerCount);
    });
  });

  group('ProfileSubjectViewData — Wire 映射', () {
    test('展示名在 wire 空串时回退到 subjectId', () {
      final view = ProfileSubjectViewData.fromProfileSubjectWire(
        ProfileSubjectWireDto.fromMap(<String, dynamic>{
          'userId': 'only_id',
          'nickname': '',
          'displayName': '',
          'username': '',
          'subjectType': '',
          'subAccountId': '',
        }),
      );
      expect(view.displayName, 'only_id');
      expect(view.username, 'only_id');
      expect(view.userHandle, 'only_id');
      expect(view.subjectType, 'user');
    });
  });

  group('ProfileSocialRelationRowWireDto', () {
    test('userId 与 displayName 别名', () {
      final dto = ProfileSocialRelationRowWireDto.fromMap(<String, dynamic>{
        'userId': 'rel_1',
        'nickname': '朋友',
        'avatarUrl': 'https://a.test/1.jpg',
        'isFollowing': true,
      });
      expect(dto.profileSubjectId, 'rel_1');
      expect(dto.displayName, '朋友');
      expect(dto.isFollowing, isTrue);
    });
  });

  group('ProfileUserLikeRowWireDto', () {
    test('基本字段解析', () {
      final dto = ProfileUserLikeRowWireDto.fromMap(<String, dynamic>{
        'postId': 'p9',
        'title': '标题',
        'coverUrl': 'https://c.test/x.jpg',
        'likerNickname': '赞过',
        'likerAvatarUrl': 'https://a.test/y.jpg',
        'likedAt': '2026-01-01T00:00:00Z',
      });
      expect(dto.postId, 'p9');
      expect(dto.likedAt, isNotNull);
    });
  });

  group('ProfileInteractionActivityWireDto', () {
    test('activityId / actor 别名与 target 别名', () {
      final dto = ProfileInteractionActivityWireDto.fromMap(<String, dynamic>{
        'id': 'act_1',
        'userId': 'actor_sub',
        'nickname': '小明',
        'avatarUrl': 'https://av.test/z.jpg',
        'activityType': 'like',
        'targetUserId': 'tgt_sub',
        'postId': 'post_99',
        'targetContentType': 'post',
        'targetTitle': '摘要',
        'createdAt': '2026-02-02T12:00:00Z',
      });
      expect(dto.activityId, 'act_1');
      expect(dto.actorProfileSubjectId, 'actor_sub');
      expect(dto.actorDisplayName, '小明');
      expect(dto.actorAvatarUrl, 'https://av.test/z.jpg');
      expect(dto.targetProfileSubjectId, 'tgt_sub');
      expect(dto.targetContentId, 'post_99');
      expect(dto.targetContentSummary, '摘要');
    });
  });

  group('ProfileInteractionActivityViewData — Wire 映射', () {
    test('缺 activityId 时生成合成 id', () {
      final view =
          ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
            ProfileInteractionActivityWireDto.fromMap(<String, dynamic>{
              'userId': 'u_x',
              'activityType': 'comment',
              'nickname': '某人',
            }),
          );
      expect(view.activityId, 'comment:u_x');
    });
  });

  group('PersonaManagementItemWireDto', () {
    test('personaId / id 别名与扩展字段', () {
      final dto = PersonaManagementItemWireDto.fromMap(<String, dynamic>{
        'personaId': 'per_1',
        'profileSubjectId': 'subj_1',
        'nickname': '分身名',
        'userHandle': 'persona_handle',
        'phone': '13800000000',
        'email': 'persona@example.com',
        'inheritsFromOwner': false,
        'overriddenProfileFields': <String>['email'],
      });
      expect(dto.subAccountId, 'per_1');
      expect(dto.profileSubjectId, 'subj_1');
      expect(dto.displayName, '分身名');
      expect(dto.userHandle, 'persona_handle');
      expect(dto.phone, '13800000000');
      expect(dto.email, 'persona@example.com');
      expect(dto.inheritsProfileFromOwner, isFalse);
      expect(dto.overriddenProfileFields, <String>['email']);
    });
  });

  group('PersonaManagementQuotaWireDto', () {
    test('maxPersonas / usedPersonas 别名', () {
      final dto = PersonaManagementQuotaWireDto.fromMap(<String, dynamic>{
        'maxPersonas': 10,
        'usedPersonas': 3,
      });
      expect(dto.maxSubAccounts, 10);
      expect(dto.usedSubAccounts, 3);
    });
  });

  group('PersonaManagementItemViewData — Wire 映射', () {
    test('无 subAccountId 时 subjectType 归一为 user', () {
      final view = PersonaManagementItemViewData.fromPersonaManagementItemWire(
        PersonaManagementItemWireDto.fromMap(<String, dynamic>{
          'profileSubjectId': 'owner_row',
          'displayName': '主号',
        }),
      );
      expect(view.subAccountId, '');
      expect(view.subjectType, 'user');
    });
  });

  group('PersonaManagementQuotaViewData — Wire 映射', () {
    test('maxSubAccounts<=0 时抬升到 5', () {
      final view =
          PersonaManagementQuotaViewData.fromPersonaManagementQuotaWire(
            PersonaManagementQuotaWireDto.fromMap(<String, dynamic>{
              'maxSubAccounts': 0,
              'usedSubAccounts': 0,
            }),
          );
      expect(view.maxSubAccounts, 5);
    });
  });

  group('ActivePersonaContextWireDto', () {
    test('persona envelope 字段可稳定解码', () {
      final dto = ActivePersonaContextWireDto.fromMap(<String, dynamic>{
        'personaId': 'persona_main',
        'profileSubjectId': 'subject_main',
        'subAccountId': 'persona_main',
        'ownerUserId': 'user_main',
        'contextVersion': 3,
        'personaSnapshotVersion': 2,
        'sourceSurfaceId': 'notification_center',
        'explicitOverride': true,
      });
      expect(dto.personaId, 'persona_main');
      expect(dto.profileSubjectId, 'subject_main');
      expect(dto.ownerUserId, 'user_main');
      expect(dto.personaContextVersion, '3');
      expect(dto.personaSnapshotVersion, 2);
      expect(dto.sourceSurfaceId, 'notification_center');
      expect(dto.explicitOverride, isTrue);
    });

    test('view data 暴露 canonical personaId 与 typed envelope', () {
      final view = ActivePersonaContextViewData.fromActivePersonaContextWire(
        ActivePersonaContextWireDto.fromMap(<String, dynamic>{
          'personaId': 'persona_photo',
          'profileSubjectId': 'subject_photo',
          'subAccountId': 'persona_photo',
          'ownerUserId': 'user_owner',
          'contextVersion': 5,
        }),
      );
      expect(view.personaId, 'persona_photo');
      expect(view.contextVersion, '5');
      expect(
        view.toTypedEnvelope(sourceSurfaceId: 'create_editor'),
        containsPair('personaId', 'persona_photo'),
      );
      expect(
        view.toTypedEnvelope(sourceSurfaceId: 'create_editor'),
        containsPair('sourceSurfaceId', 'create_editor'),
      );
    });
  });

  group('SocialRelationshipCapabilityWireDto', () {
    test('relationshipState 别名', () {
      final dto = SocialRelationshipCapabilityWireDto.fromMap(<String, dynamic>{
        'relationshipState': 'mutual',
        'canFollow': true,
      });
      expect(dto.relationState, 'mutual');
      expect(dto.canFollow, isTrue);
    });
  });

  group('SocialRelationSearchItemWireDto', () {
    test('显式空 subAccountId 不截断 userId（skip_empty_string_aliases）', () {
      final dto = SocialRelationSearchItemWireDto.fromMap(<String, dynamic>{
        'profileSubjectId': '',
        'userId': 'search_u1',
        'nickname': 'n',
      });
      expect(dto.profileSubjectId, 'search_u1');
    });
  });

  group('RecentSearchEntryWireDto', () {
    test('scope / updatedAt', () {
      final dto = RecentSearchEntryWireDto.fromMap(<String, dynamic>{
        'entryId': 'e1',
        'query': '摄影',
        'scope': 'content',
        'updatedAt': '2026-03-01T08:00:00Z',
      });
      expect(dto.scope, 'content');
      expect(dto.updatedAt, isNotNull);
    });
  });

  group('RecentSearchEntryView — Wire 映射', () {
    test('缺 entryId 时由 buildEntryId 生成', () {
      final view = RecentSearchEntryView.fromRecentSearchEntryWire(
        RecentSearchEntryWireDto.fromMap(<String, dynamic>{
          'query': 'hello',
          'scope': 'all',
        }),
      );
      expect(view.query, 'hello');
      expect(view.entryId, isNotEmpty);
    });
  });

  group('RelationshipNormalizedWireDto', () {
    test('布尔与状态', () {
      final dto = RelationshipNormalizedWireDto.fromMap(<String, dynamic>{
        'relationState': 'following',
        'isFollowing': true,
        'isFollowedBy': false,
        'isMutual': false,
      });
      final v = RelationshipViewData.fromRelationshipNormalizedWire(dto);
      expect(v.relationState, 'following');
      expect(v.isFollowing, isTrue);
    });
  });

  group('UserProfileStatsWireDto', () {
    test('计数解析', () {
      final dto = UserProfileStatsWireDto.fromMap(<String, dynamic>{
        'followerCount': 10,
        'followingCount': 20,
        'postCount': 3,
        'circleCount': 4,
        'likeCount': 5,
      });
      final v = UserProfileStatsViewData.fromUserProfileStatsWire(dto);
      expect(v.followerCount, 10);
      expect(v.followingCount, 20);
    });
  });

  group('PersonaLifecycleGuardWireDto', () {
    test('message 多别名', () {
      final dto = PersonaLifecycleGuardWireDto.fromMap(<String, dynamic>{
        'subAccountId': 's1',
        'userMessage': '提示',
        'canDelete': false,
      });
      final v = PersonaLifecycleGuardViewData.fromPersonaLifecycleGuardWire(
        dto,
      );
      expect(v.message, '提示');
    });
  });

  group('ActivePersonaContextWireDto', () {
    test('skip_empty 后 userId 回填 profileSubjectId', () {
      final dto = ActivePersonaContextWireDto.fromMap(<String, dynamic>{
        'profileSubjectId': '',
        'subAccountId': '',
        'userId': 'ctx_u',
        'nickname': '展示',
      });
      expect(dto.profileSubjectId, 'ctx_u');
    });
  });

  group('PersonaManagementSummaryWireDto', () {
    test('subAccounts 优先于空 items', () {
      final dto = PersonaManagementSummaryWireDto.fromMap(<String, dynamic>{
        'items': <Map<String, dynamic>>[],
        'subAccounts': <Map<String, dynamic>>[
          <String, dynamic>{
            'subAccountId': 's1',
            'profileSubjectId': 'p1',
            'displayName': 'A',
          },
        ],
        'quota': <String, dynamic>{'maxSubAccounts': 5, 'usedSubAccounts': 1},
      });
      expect(dto.items.length, 1);
      final view =
          PersonaManagementSummaryViewData.fromPersonaManagementSummaryWire(
            dto,
          );
      expect(view.items.length, 1);
      expect(view.quota.usedSubAccounts, 1);
    });
  });

  group('RelationshipCapabilityWireDto', () {
    test('映射到 RelationshipCapabilityDto', () {
      final dto = RelationshipCapabilityWireDto.fromMap(<String, dynamic>{
        'viewerProfileSubjectId': 'v1',
        'targetProfileSubjectId': 't1',
        'relationState': 'following',
        'canFollow': false,
        'canUnfollow': true,
        'canMessage': true,
        'canFollowBack': false,
        'isBlocked': false,
        'isBlockedBy': false,
      });
      final cap = RelationshipCapabilityDto.fromRelationshipCapabilityWire(dto);
      expect(cap.viewerSubAccountId, 'v1');
      expect(cap.relationState, 'following');
    });
  });

  group('AppearanceSettingsWireDto', () {
    test('Wire → Snapshot', () {
      final w = AppearanceSettingsWireDto.fromMap(<String, dynamic>{
        'themeMode': 'dark',
        'fontSizePreset': 'lg',
        'source': 'sub_override',
        'ownerDefaultThemeMode': 'system',
        'ownerDefaultFontSizePreset': 'md',
        'hasSubAccountOverride': true,
        'version': 3,
        'updatedAt': '2026-01-02T00:00:00Z',
      });
      final s = AppearanceSettingsSnapshot.fromAppearanceSettingsWire(w);
      expect(s.themeMode.wireValue, 'dark');
      expect(s.version, 3);
    });
  });

  group('CallSettingsWireDto', () {
    test('Wire → CallSettingsDto', () {
      final w = CallSettingsWireDto.fromMap(<String, dynamic>{
        'defaultIncomingCallRingtoneId': 'official.blue-wave',
        'allowCallerRingtoneOverride': false,
        'enableCallVibration': true,
        'enableGroupCallRing': false,
      });
      final d = CallSettingsDto.fromCallSettingsWire(w);
      expect(d.defaultIncomingCallRingtoneId, 'official.blue-wave');
      expect(d.allowCallerRingtoneOverride, isFalse);
    });
  });

  group('PrivacySettingsWireDto', () {
    test('blockedKeywords', () {
      final w = PrivacySettingsWireDto.fromMap(<String, dynamic>{
        'blockedKeywords': <String>['a', 'b'],
      });
      expect(w.blockedKeywords, ['a', 'b']);
    });
  });
}
