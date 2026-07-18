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
import 'package:quwoquan_app/cloud/runtime/generated/user/sub_account_profile_wire_dto.g.dart';
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
  group('SubAccountProfileWireDto', () {
    test('subAccountId does not impersonate ownerUserId', () {
      final dto = SubAccountProfileWireDto.fromMap(<String, dynamic>{
        'subAccountId': 'u_owner',
        'displayName': 'nick',
        'followerCount': 1,
        'followingCount': 2,
        'postCount': 3,
        'circleCount': 4,
        'likeCount': 5,
      });
      expect(dto.subAccountId, 'u_owner');
      expect(dto.ownerUserId, isEmpty);
      expect(dto.displayName, 'nick');
    });

    test('backgroundUrl uses the canonical wire key', () {
      final dto = SubAccountProfileWireDto.fromMap(<String, dynamic>{
        'subAccountId': 'u1',
        'backgroundUrl': 'https://bg.example/x.jpg',
      });
      expect(dto.backgroundUrl, 'https://bg.example/x.jpg');
    });

    test('avatarVersion 稳定解码', () {
      final dto = SubAccountProfileWireDto.fromMap(<String, dynamic>{
        'userId': 'u1',
        'avatarVersion': 7,
      });
      expect(dto.avatarVersion, 7);
    });

    test('canonical creator 复用公开 profile DTO 且不消费内部 CAS/hash 字段', () {
      final dto = SubAccountProfileWireDto.fromMap(<String, dynamic>{
        'userId': 'sys_travelphoto_0800',
        'subAccountId': 'sys_travelphoto_0800_sub_01',
        'subjectType': 'creator',
        'userHandle': 'set-marker',
        'displayName': '片场坐标',
        'nickname': '片场坐标',
        'avatarUrl': 'https://media.example/media/objects/avatar.png',
        'backgroundUrl': 'https://media.example/media/objects/cover.jpg',
        'bio': '路线写给脚步，照片写给回忆。',
        'identityTags': <String>['creator', 'travel', 'photography'],
        'postCount': 0,
        'avatarObjectKey': 'media/objects/avatar.png',
        'avatarSha256': 'internal-only',
        'packageDigest': 'internal-only',
      });
      expect(dto.subjectType, 'creator');
      expect(dto.subAccountId, 'sys_travelphoto_0800_sub_01');
      expect(dto.userHandle, 'set-marker');
      expect(dto.displayName, '片场坐标');
      expect(dto.avatarUrl, endsWith('/avatar.png'));
      expect(dto.backgroundUrl, endsWith('/cover.jpg'));
      expect(dto.identityTags, containsAll(<String>['creator', 'travel']));
      expect(
        dto.toMap().keys,
        isNot(
          containsAll(<String>[
            'avatarObjectKey',
            'avatarSha256',
            'packageDigest',
          ]),
        ),
      );
    });

    test('toMap round-trip 稳定', () {
      final dto = SubAccountProfileWireDto.fromMap(<String, dynamic>{
        'subAccountId': 'ps1',
        'ownerUserId': 'o1',
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
      final restored = SubAccountProfileWireDto.fromMap(dto.toMap());
      expect(restored.subAccountId, dto.subAccountId);
      expect(restored.userHandle, 'handle_1');
      expect(restored.followerCount, dto.followerCount);
    });
  });

  group('SubAccountProfileViewData — Wire 映射', () {
    test('展示名在 wire 空串时回退到 subjectId', () {
      final view = SubAccountProfileViewData.fromSubAccountProfileWire(
        SubAccountProfileWireDto.fromMap(<String, dynamic>{
          'subAccountId': 'only_id',
          'displayName': '',
          'username': '',
          'subjectType': '',
        }),
      );
      expect(view.displayName, 'only_id');
      expect(view.username, 'only_id');
      expect(view.userHandle, 'only_id');
      expect(view.subjectType, 'user');
    });

    test('avatarVersion 进入头像 URL 以驱动缓存失效', () {
      final view = SubAccountProfileViewData.fromSubAccountProfileWire(
        SubAccountProfileWireDto.fromMap(<String, dynamic>{
          'subAccountId': 'u_avatar',
          'avatarUrl':
              'media/avatar/s/archived-avatar/user/u_avatar/v1/profile.png',
          'avatarVersion': 6,
        }),
      );
      expect(view.avatarVersion, 6);
      expect(view.avatarUrl, contains('?v=6'));
    });
  });

  group('ProfileSocialRelationRowWireDto', () {
    test('canonical subAccountId and displayName', () {
      final dto = ProfileSocialRelationRowWireDto.fromMap(<String, dynamic>{
        'subAccountId': 'rel_1',
        'displayName': '朋友',
        'avatarUrl': 'https://a.test/1.jpg',
        'avatarVersion': 4,
        'relationState': 'following',
      });
      expect(dto.subAccountId, 'rel_1');
      expect(dto.displayName, '朋友');
      expect(dto.avatarVersion, 4);
      expect(dto.relationState, 'following');
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
        'likerAvatarVersion': 6,
        'likedAt': '2026-01-01T00:00:00Z',
      });
      expect(dto.postId, 'p9');
      expect(dto.likerAvatarVersion, 6);
      expect(dto.likedAt, isNotNull);
    });

    test('view data 把 likerAvatarVersion 注入缓存 URL', () {
      final view = ProfileUserLikeRowViewData.fromProfileUserLikeRowWire(
        ProfileUserLikeRowWireDto.fromMap(<String, dynamic>{
          'postId': 'p9',
          'title': '标题',
          'coverUrl': 'https://c.test/x.jpg',
          'likerNickname': '赞过',
          'likerAvatarUrl': 'media/avatar/s/mock/seed/test_liker/v1/avatar.jpg',
          'likerAvatarVersion': 6,
        }),
      );
      expect(view.likerAvatarVersion, 6);
      expect(view.likerAvatarUrl, isNotEmpty);
      expect(view.likerAvatarUrl, contains('v=6'));
    });
  });

  group('ProfileInteractionActivityWireDto', () {
    test('canonical activity actor and target fields', () {
      final dto = ProfileInteractionActivityWireDto.fromMap(<String, dynamic>{
        'activityId': 'act_1',
        'actorSubAccountId': 'actor_sub',
        'actorDisplayName': '小明',
        'actorAvatarUrl': 'https://av.test/z.jpg',
        'actorAvatarVersion': 8,
        'activityType': 'like',
        'targetSubAccountId': 'tgt_sub',
        'targetContentId': 'post_99',
        'targetContentType': 'post',
        'targetContentSummary': '摘要',
        'displayAvatarVersion': 8,
        'createdAt': '2026-02-02T12:00:00Z',
      });
      expect(dto.activityId, 'act_1');
      expect(dto.actorSubAccountId, 'actor_sub');
      expect(dto.actorDisplayName, '小明');
      expect(dto.actorAvatarUrl, 'https://av.test/z.jpg');
      expect(dto.actorAvatarVersion, 8);
      expect(dto.targetSubAccountId, 'tgt_sub');
      expect(dto.targetContentId, 'post_99');
      expect(dto.targetContentSummary, '摘要');
      expect(dto.displayAvatarVersion, 8);
      // 默认无评论标识。
      expect(dto.commentId, '');
      expect(dto.parentCommentId, '');
    });

    test('评论标识 commentId / parentCommentId 解析（深链精确定位）', () {
      final dto = ProfileInteractionActivityWireDto.fromMap(<String, dynamic>{
        'activityId': 'comment_reply_9',
        'activityType': 'comment',
        'commentKind': 'reply',
        'commentId': 'comment_reply_9',
        'parentCommentId': 'comment_top_1',
        'actorSubAccountId': 'u_a',
      });
      expect(dto.commentKind, 'reply');
      expect(dto.commentId, 'comment_reply_9');
      expect(dto.parentCommentId, 'comment_top_1');
    });
  });

  group('ProfileInteractionActivityViewData — Wire 映射', () {
    test('缺 activityId 时生成合成 id', () {
      final view =
          ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
            ProfileInteractionActivityWireDto.fromMap(<String, dynamic>{
              'actorSubAccountId': 'u_x',
              'activityType': 'comment',
              'actorDisplayName': '某人',
            }),
          );
      expect(view.activityId, 'comment:u_x');
    });

    test('评论标识透传到 ViewData 供深链消费', () {
      final view =
          ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
            ProfileInteractionActivityWireDto.fromMap(<String, dynamic>{
              'activityId': 'comment_reply_9',
              'activityType': 'comment',
              'commentKind': 'reply',
              'commentId': 'comment_reply_9',
              'parentCommentId': 'comment_top_1',
              'actorSubAccountId': 'u_a',
            }),
          );
      expect(view.commentId, 'comment_reply_9');
      expect(view.parentCommentId, 'comment_top_1');
    });

    test('头像版本驱动 actor/display 缓存 URL，display 缺省时复用 actor 版本', () {
      final view =
          ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
            ProfileInteractionActivityWireDto.fromMap(<String, dynamic>{
              'activityId': 'activity_1',
              'activityType': 'like',
              'actorSubAccountId': 'u_a',
              'actorDisplayName': '某人',
              'actorAvatarUrl':
                  'media/avatar/s/mock/seed/test_actor/v1/avatar.jpg',
              'actorAvatarVersion': 7,
              'displayName': '某人',
            }),
          );
      expect(view.actorAvatarVersion, 7);
      expect(view.actorAvatarUrl, isNotEmpty);
      expect(view.actorAvatarUrl, contains('v=7'));
      expect(view.displayAvatarVersion, 7);
      expect(view.displayAvatarUrl, isNotEmpty);
      expect(view.displayAvatarUrl, contains('v=7'));
    });
  });

  group('PersonaManagementItemWireDto', () {
    test('canonical persona fields and extensions', () {
      final dto = PersonaManagementItemWireDto.fromMap(<String, dynamic>{
        'subAccountId': 'per_1',
        'displayName': '分身名',
        'userHandle': 'persona_handle',
        'phone': '13800000000',
        'email': 'persona@example.com',
        'avatarUrl': 'https://a.test/persona.jpg',
        'avatarVersion': 5,
        'inheritsProfileFromOwner': false,
        'overriddenProfileFields': <String>['email'],
      });
      expect(dto.subAccountId, 'per_1');
      expect(dto.displayName, '分身名');
      expect(dto.userHandle, 'persona_handle');
      expect(dto.phone, '13800000000');
      expect(dto.email, 'persona@example.com');
      expect(dto.avatarVersion, 5);
      expect(dto.inheritsProfileFromOwner, isFalse);
      expect(dto.overriddenProfileFields, <String>['email']);
    });
  });

  group('PersonaManagementQuotaWireDto', () {
    test('canonical maxSubAccounts and usedSubAccounts', () {
      final dto = PersonaManagementQuotaWireDto.fromMap(<String, dynamic>{
        'maxSubAccounts': 10,
        'usedSubAccounts': 3,
      });
      expect(dto.maxSubAccounts, 10);
      expect(dto.usedSubAccounts, 3);
    });
  });

  group('PersonaManagementItemViewData — Wire 映射', () {
    test('无 subAccountId 时 subjectType 归一为 user', () {
      final view = PersonaManagementItemViewData.fromPersonaManagementItemWire(
        PersonaManagementItemWireDto.fromMap(<String, dynamic>{
          'displayName': '主号',
        }),
      );
      expect(view.subAccountId, '');
      expect(view.subjectType, 'user');
    });

    test('avatarVersion 驱动管理行头像缓存 URL', () {
      final view = PersonaManagementItemViewData.fromPersonaManagementItemWire(
        PersonaManagementItemWireDto.fromMap(<String, dynamic>{
          'subAccountId': 'per_1',
          'displayName': '分身名',
          'avatarUrl': 'media/avatar/s/mock/seed/test_persona/v1/avatar.jpg',
          'avatarVersion': 5,
        }),
      );
      expect(view.avatarVersion, 5);
      expect(view.avatarUrl, isNotEmpty);
      expect(view.avatarUrl, contains('v=5'));
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
        'subAccountId': 'persona_main',
        'ownerUserId': 'user_main',
        'avatarVersion': 9,
        'personaContextVersion': '3',
        'personaSnapshotVersion': 2,
        'sourceSurfaceId': 'notification_center',
        'explicitOverride': true,
      });
      expect(dto.subAccountId, 'persona_main');
      expect(dto.ownerUserId, 'user_main');
      expect(dto.avatarVersion, 9);
      expect(dto.personaContextVersion, '3');
      expect(dto.personaSnapshotVersion, 2);
      expect(dto.sourceSurfaceId, 'notification_center');
      expect(dto.explicitOverride, isTrue);
    });

    test('view data 暴露 canonical subAccountId 与 typed envelope', () {
      final view = ActivePersonaContextViewData.fromActivePersonaContextWire(
        ActivePersonaContextWireDto.fromMap(<String, dynamic>{
          'subAccountId': 'persona_photo',
          'ownerUserId': 'user_owner',
          'avatarUrl':
              'media/avatar/s/archived-avatar/user/persona_photo/v1/profile.png',
          'avatarVersion': 5,
          'personaContextVersion': '5',
        }),
      );
      expect(view.subAccountId, 'persona_photo');
      expect(view.avatarVersion, 5);
      expect(view.avatarUrl, contains('?v=5'));
      expect(view.contextVersion, '5');
      expect(
        view.toTypedEnvelope(sourceSurfaceId: 'create_editor'),
        containsPair('subAccountId', 'persona_photo'),
      );
      expect(
        view.toTypedEnvelope(sourceSurfaceId: 'create_editor'),
        containsPair('sourceSurfaceId', 'create_editor'),
      );
    });
  });

  group('SocialRelationshipCapabilityWireDto', () {
    test('canonical relationState', () {
      final dto = SocialRelationshipCapabilityWireDto.fromMap(<String, dynamic>{
        'relationState': 'mutual',
        'canFollow': true,
      });
      expect(dto.relationState, 'mutual');
      expect(dto.canFollow, isTrue);
    });
  });

  group('SocialRelationSearchItemWireDto', () {
    test('显式空 subAccountId 不消费 retired userId', () {
      final dto = SocialRelationSearchItemWireDto.fromMap(<String, dynamic>{
        'subAccountId': '',
        'userId': 'search_u1',
        'nickname': 'n',
        'avatarVersion': 8,
      });
      expect(dto.subAccountId, isEmpty);
      expect(dto.avatarVersion, 8);
    });

    test('view 使用 avatarVersion 生成稳定头像缓存键', () {
      final view = SocialRelationSearchItemView.fromSocialRelationSearchItemWire(
        SocialRelationSearchItemWireDto.fromMap(<String, dynamic>{
          'subAccountId': 'search_u2',
          'displayName': '搜索用户',
          'avatarUrl':
              'media/avatar/s/archived-avatar/user/search_u2/v1/profile.png',
          'avatarVersion': 3,
          'chatAvailable': true,
        }),
        <String, dynamic>{},
      );
      expect(view.avatarVersion, 3);
      expect(view.avatarUrl, contains('?v=3'));
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
    test('canonical message', () {
      final dto = PersonaLifecycleGuardWireDto.fromMap(<String, dynamic>{
        'subAccountId': 's1',
        'message': '提示',
        'canDelete': false,
      });
      final v = PersonaLifecycleGuardViewData.fromPersonaLifecycleGuardWire(
        dto,
      );
      expect(v.message, '提示');
    });
  });

  group('ActivePersonaContextWireDto', () {
    test('ownerUserId does not backfill an empty subAccountId', () {
      final dto = ActivePersonaContextWireDto.fromMap(<String, dynamic>{
        'subAccountId': '',
        'ownerUserId': 'ctx_u',
        'displayName': '展示',
      });
      expect(dto.subAccountId, '');
      expect(dto.ownerUserId, 'ctx_u');
    });
  });

  group('PersonaManagementSummaryWireDto', () {
    test('canonical items wins and retired subAccounts is ignored', () {
      final dto = PersonaManagementSummaryWireDto.fromMap(<String, dynamic>{
        'items': <Map<String, dynamic>>[
          <String, dynamic>{'subAccountId': 's1', 'displayName': 'A'},
        ],
        'subAccounts': <Map<String, dynamic>>[
          <String, dynamic>{'subAccountId': 'retired', 'displayName': 'B'},
        ],
        'quota': <String, dynamic>{'maxSubAccounts': 5, 'usedSubAccounts': 1},
      });
      expect(dto.items.length, 1);
      expect(dto.items.single['subAccountId'], 's1');
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
        'viewerSubAccountId': 'v1',
        'targetSubAccountId': 't1',
        'relationState': 'following',
        'canFollow': false,
        'canUnfollow': true,
        'canOpenConversation': true,
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

    test('空 ringtone 字符串回退为 null，兼容存量 NULL 行', () {
      final w = CallSettingsWireDto.fromMap(<String, dynamic>{
        'defaultIncomingCallRingtoneId': '',
        'allowCallerRingtoneOverride': true,
      });
      final d = CallSettingsDto.fromCallSettingsWire(w);
      expect(d.defaultIncomingCallRingtoneId, isNull);
      expect(d.allowCallerRingtoneOverride, isTrue);
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
