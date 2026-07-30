import 'package:test/test.dart';
import 'package:quwoquan_app/app/models/appearance_settings_models.dart'
    as appearance;
import 'package:quwoquan_app/cloud/runtime/generated/user/active_persona_context_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona/persona_management_summary_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona/persona_lifecycle_guard_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona/persona_management_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona/persona_management_quota_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona/persona_update_request_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_social_relation_row_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_profile_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/recent_search_entry_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/relationship_view_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/social_relation_search_item_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/relationship_capability_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/account/user_account_stats_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('PersonaProfileWireDto', () {
    test('personaId does not impersonate ownerUserId', () {
      final dto = PersonaProfileWireDto.fromMap(<String, dynamic>{
        'personaId': 'u_owner',
        'displayName': 'nick',
        'followerCount': 1,
        'followingCount': 2,
        'postCount': 3,
        'circleCount': 4,
        'likeCount': 5,
      });
      expect(dto.personaId, 'u_owner');
      expect(dto.ownerUserId, isEmpty);
      expect(dto.displayName, 'nick');
    });

    test('backgroundUrl uses the canonical wire key', () {
      final dto = PersonaProfileWireDto.fromMap(<String, dynamic>{
        'personaId': 'u1',
        'backgroundUrl': 'https://bg.example/x.jpg',
      });
      expect(dto.backgroundUrl, 'https://bg.example/x.jpg');
    });

    test('avatarVersion 稳定解码', () {
      final dto = PersonaProfileWireDto.fromMap(<String, dynamic>{
        'userId': 'u1',
        'avatarVersion': 7,
      });
      expect(dto.avatarVersion, 7);
    });

    test('canonical creator 复用公开 profile DTO 且不消费内部 CAS/hash 字段', () {
      final dto = PersonaProfileWireDto.fromMap(<String, dynamic>{
        'userId': 'sys_travelphoto_0800',
        'personaId': 'sys_travelphoto_0800_sub_01',
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
      expect(dto.personaId, 'sys_travelphoto_0800_sub_01');
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
      final dto = PersonaProfileWireDto.fromMap(<String, dynamic>{
        'personaId': 'ps1',
        'ownerUserId': 'o1',
        'userHandle': 'handle_1',
        'nickname': 'n',
        'displayName': 'd',
        'subjectType': 'account',
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
      final restored = PersonaProfileWireDto.fromMap(dto.toMap());
      expect(restored.personaId, dto.personaId);
      expect(restored.userHandle, 'handle_1');
      expect(restored.followerCount, dto.followerCount);
    });
  });

  group('PersonaProfileViewData — Wire 映射', () {
    test('展示名在 wire 空串时回退到 subjectId', () {
      final view = PersonaProfileViewData.fromPersonaProfileWire(
        PersonaProfileWireDto.fromMap(<String, dynamic>{
          'personaId': 'only_id',
          'displayName': '',
          'userHandle': 'only_handle',
          'subjectType': '',
        }),
      );
      expect(view.displayName, 'only_id');
      expect(view.userHandle, 'only_handle');
      expect(view.subjectType, 'persona');
    });

    test('avatarVersion 按运行时 endpoint 可用性驱动 URL', () {
      final view = PersonaProfileViewData.fromPersonaProfileWire(
        PersonaProfileWireDto.fromMap(<String, dynamic>{
          'personaId': 'u_avatar',
          'avatarUrl':
              'media/avatar/s/archived-avatar/user/u_avatar/v6/profile.png',
          'avatarVersion': 6,
        }),
      );
      expect(view.avatarVersion, 6);
      _expectVersionedAvatarOrUnavailable(view.avatarUrl, 6);
    });
  });

  group('ProfileSocialRelationRowWireDto', () {
    test('canonical personaId and displayName', () {
      final dto = ProfileSocialRelationRowWireDto.fromMap(<String, dynamic>{
        'personaId': 'rel_1',
        'displayName': '朋友',
        'avatarUrl': 'https://a.test/1.jpg',
        'avatarVersion': 4,
        'relationState': 'following',
      });
      expect(dto.personaId, 'rel_1');
      expect(dto.displayName, '朋友');
      expect(dto.avatarVersion, 4);
      expect(dto.relationState, 'following');
    });
  });

  group('ProfileInteractionActivityViewData — typed slice 映射', () {
    test('评论标识透传到 ViewData 供深链消费', () {
      final view = ProfileInteractionActivityViewData.fromContentActivity(
        ContentProfileInteractionActivity(
          activityId: 'comment_reply_9',
          activityType: 'comment',
          direction: 'received',
          commentKind: 'reply',
          commentId: 'comment_reply_9',
          parentCommentId: 'comment_top_1',
          actorPersonaId: 'u_a',
          actorDisplayName: '某人',
          targetPersonaId: 'owner',
          targetContentId: 'post_99',
          targetContentType: 'article',
          displayPersonaId: 'u_a',
          displayName: '某人',
          primaryText: '回复了你',
          createdAt: DateTime.utc(2026, 2, 2),
          occurredAt: DateTime.utc(2026, 2, 2),
        ),
      );
      expect(view.commentId, 'comment_reply_9');
      expect(view.parentCommentId, 'comment_top_1');
    });

    test('actor/display 版本同源并按 endpoint 可用性解析', () {
      final view = ProfileInteractionActivityViewData.fromContentActivity(
        ContentProfileInteractionActivity(
          activityId: 'activity_1',
          activityType: 'like',
          direction: 'received',
          actorPersonaId: 'u_a',
          actorDisplayName: '某人',
          actorAvatarUrl: 'media/avatar/s/mock/seed/test_actor/v7/avatar.jpg',
          actorAvatarVersion: 7,
          targetPersonaId: 'owner',
          targetContentId: 'post_99',
          targetContentType: 'image',
          displayPersonaId: 'u_a',
          displayName: '某人',
          primaryText: '点赞了你的记录',
          createdAt: DateTime.utc(2026, 2, 2),
          occurredAt: DateTime.utc(2026, 2, 2),
        ),
      );
      expect(view.actorAvatarVersion, 7);
      _expectVersionedAvatarOrUnavailable(view.actorAvatarUrl, 7);
      expect(view.displayAvatarVersion, 7);
      _expectVersionedAvatarOrUnavailable(view.displayAvatarUrl, 7);
    });
  });

  group('PersonaManagementItemWireDto', () {
    test('canonical persona fields and extensions', () {
      final dto = PersonaManagementItemWireDto.fromMap(<String, dynamic>{
        'personaId': 'per_1',
        'displayName': '分身名',
        'userHandle': 'persona_handle',
        'avatarUrl': 'https://a.test/persona.jpg',
        'avatarVersion': 5,
        'inheritsProfileFromOwner': false,
        'overriddenProfileFields': <String>['displayName'],
      });
      expect(dto.personaId, 'per_1');
      expect(dto.displayName, '分身名');
      expect(dto.userHandle, 'persona_handle');
      expect(dto.avatarVersion, 5);
      expect(dto.inheritsProfileFromOwner, isFalse);
      expect(dto.overriddenProfileFields, <String>['displayName']);
      expect(dto.toMap().containsKey('phone'), isFalse);
      expect(dto.toMap().containsKey('email'), isFalse);
    });
  });

  group('PersonaUpdateRequestDto', () {
    test('credential plaintext is absent from the generated mutation wire', () {
      final dto = PersonaUpdateRequestDto.fromMap(<String, dynamic>{
        'displayName': '分身名',
        'phone': '13800138000',
        'email': 'persona@example.com',
      });

      expect(dto.toMap().containsKey('phone'), isFalse);
      expect(dto.toMap().containsKey('email'), isFalse);
    });
  });

  group('PersonaManagementQuotaWireDto', () {
    test('canonical maxPersonas and usedPersonas', () {
      final dto = PersonaManagementQuotaWireDto.fromMap(<String, dynamic>{
        'maxPersonas': 10,
        'usedPersonas': 3,
      });
      expect(dto.maxPersonas, 10);
      expect(dto.usedPersonas, 3);
    });
  });

  group('PersonaManagementItemViewData — Wire 映射', () {
    test('无 personaId 时 subjectType 归一为 account', () {
      final view = PersonaManagementItemViewData.fromPersonaManagementItemWire(
        PersonaManagementItemWireDto.fromMap(<String, dynamic>{
          'displayName': '主号',
        }),
      );
      expect(view.personaId, '');
      expect(view.subjectType, 'account');
    });

    test('管理行保留 avatarVersion 并按 endpoint 可用性解析', () {
      final view = PersonaManagementItemViewData.fromPersonaManagementItemWire(
        PersonaManagementItemWireDto.fromMap(<String, dynamic>{
          'personaId': 'per_1',
          'displayName': '分身名',
          'avatarUrl': 'media/avatar/s/mock/seed/test_persona/v5/avatar.jpg',
          'avatarVersion': 5,
        }),
      );
      expect(view.avatarVersion, 5);
      _expectVersionedAvatarOrUnavailable(view.avatarUrl, 5);
    });
  });

  group('PersonaManagementQuotaViewData — Wire 映射', () {
    test('maxPersonas<=0 时抬升到 5', () {
      final view =
          PersonaManagementQuotaViewData.fromPersonaManagementQuotaWire(
            PersonaManagementQuotaWireDto.fromMap(<String, dynamic>{
              'maxPersonas': 0,
              'usedPersonas': 0,
            }),
          );
      expect(view.maxPersonas, 5);
    });
  });

  group('ActivePersonaContextWireDto', () {
    test('persona envelope 字段可稳定解码', () {
      final dto = ActivePersonaContextWireDto.fromMap(<String, dynamic>{
        'personaId': 'persona_main',
        'ownerUserId': 'user_main',
        'avatarVersion': 9,
        'contextVersion': 3,
        'personaSnapshotVersion': 2,
        'sourceSurfaceId': 'notification_center',
        'explicitOverride': true,
      });
      expect(dto.personaId, 'persona_main');
      expect(dto.ownerUserId, 'user_main');
      expect(dto.avatarVersion, 9);
      expect(dto.contextVersion, 3);
      expect(dto.personaSnapshotVersion, 2);
      expect(dto.sourceSurfaceId, 'notification_center');
      expect(dto.explicitOverride, isTrue);
    });

    test('view data 暴露 canonical personaId 与 typed envelope', () {
      final view = ActivePersonaContextViewData.fromActivePersonaContextWire(
        ActivePersonaContextWireDto.fromMap(<String, dynamic>{
          'personaId': 'persona_photo',
          'ownerUserId': 'user_owner',
          'avatarUrl':
              'media/avatar/s/archived-avatar/user/persona/persona_photo/v5/profile.png',
          'avatarVersion': 5,
          'contextVersion': 5,
          'personaSnapshotVersion': 7,
        }),
      );
      expect(view.personaId, 'persona_photo');
      expect(view.avatarVersion, 5);
      _expectVersionedAvatarOrUnavailable(view.avatarUrl, 5);
      expect(view.contextVersion, 5);
      expect(view.personaSnapshotVersion, 7);
      expect(
        view.toTypedEnvelope(sourceSurfaceId: 'create_editor'),
        containsPair('personaId', 'persona_photo'),
      );
      expect(
        view.toTypedEnvelope(sourceSurfaceId: 'create_editor'),
        containsPair('contextVersion', 5),
      );
      expect(
        view.toTypedEnvelope(sourceSurfaceId: 'create_editor'),
        containsPair('personaSnapshotVersion', 7),
      );
      expect(
        view.toTypedEnvelope(sourceSurfaceId: 'create_editor'),
        containsPair('sourceSurfaceId', 'create_editor'),
      );
      expect(
        view.toTypedEnvelope(sourceSurfaceId: 'create_editor'),
        isNot(contains('personaContextVersion')),
      );
    });
  });

  group('RelationshipCapabilityWireDto', () {
    test('canonical relationState', () {
      final dto = RelationshipCapabilityWireDto.fromMap(<String, dynamic>{
        'relationState': 'mutual',
        'canFollow': true,
      });
      expect(dto.relationState, 'mutual');
      expect(dto.canFollow, isTrue);
    });

    test('缺失必填能力位直接拒绝，视图层不补算', () {
      final dto = RelationshipCapabilityWireDto.fromMap(<String, dynamic>{});
      expect(dto.relationState, isNull);
      expect(dto.canFollow, isNull);
      expect(dto.canOpenConversation, isNull);
      expect(
        () => RelationshipCapabilityDto.fromRelationshipCapabilityWire(dto),
        throwsFormatException,
      );
    });
  });

  group('SocialRelationSearchItemWireDto', () {
    test('显式空 personaId 不消费 retired userId', () {
      final dto = SocialRelationSearchItemWireDto.fromMap(<String, dynamic>{
        'personaId': '',
        'userId': 'search_u1',
        'nickname': 'n',
        'avatarVersion': 8,
        'relationshipCapability': <String, dynamic>{
          'viewerPersonaId': '',
          'targetPersonaId': '',
        },
      });
      expect(dto.personaId, isEmpty);
      expect(dto.avatarVersion, 8);
    });

    test('view 保留 avatarVersion 并按 endpoint 可用性解析', () {
      final view = SocialRelationSearchItemView.fromSocialRelationSearchItemWire(
        SocialRelationSearchItemWireDto.fromMap(<String, dynamic>{
          'personaId': 'search_u2',
          'displayName': '搜索用户',
          'avatarUrl':
              'media/avatar/s/archived-avatar/user/search_u2/v3/profile.png',
          'avatarVersion': 3,
          'chatAvailable': true,
          'relationshipCapability': <String, dynamic>{
            'relationState': 'mutual',
            'canFollow': false,
            'canUnfollow': true,
            'canFollowBack': false,
            'canGreet': false,
            'canOpenConversation': true,
            'canCreateDirectConversation': true,
            'canSendMessage': true,
            'hasPendingGreeting': false,
            'hasFormalConversation': false,
            'canStartVoiceCall': true,
            'canStartVideoCall': true,
            'isBlocked': false,
            'isBlockedBy': false,
          },
        }),
      );
      expect(view.avatarVersion, 3);
      _expectVersionedAvatarOrUnavailable(view.avatarUrl, 3);
      expect(view.relationshipCapability.relationState, 'mutual');
      expect(view.chatAvailable, isTrue);
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

  group('RelationshipViewWireDto', () {
    test('relationState 与派生布尔', () {
      final dto = RelationshipViewWireDto.fromMap(<String, dynamic>{
        'viewerPersonaId': 'ps_viewer',
        'targetPersonaId': 'ps_target',
        'relationState': 'mutual',
        'isBlocked': false,
        'isBlockedBy': false,
      });
      final v = RelationshipViewData.fromRelationshipViewWire(dto);
      expect(v.relationState, 'mutual');
      expect(v.isFollowing, isTrue);
      expect(v.isFollowedBy, isTrue);
      expect(v.isMutual, isTrue);
      expect(v.isBlocked, isFalse);
    });

    test('block 位保留且派生布尔跟随 relationState', () {
      final dto = RelationshipViewWireDto.fromMap(<String, dynamic>{
        'relationState': 'not_following',
        'isBlocked': true,
        'isBlockedBy': false,
      });
      final v = RelationshipViewData.fromRelationshipViewWire(dto);
      expect(v.isFollowing, isFalse);
      expect(v.isBlocked, isTrue);
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
    test('canonical lifecycle guard fields', () {
      final dto = PersonaLifecycleGuardWireDto.fromMap(<String, dynamic>{
        'personaId': 's1',
        'requestedAction': 'retire',
        'allowed': false,
        'reason': 'blocked_primary_persona',
        'requiresSuccessor': false,
      });
      final v = PersonaLifecycleGuardViewData.fromPersonaLifecycleGuardWire(
        dto,
      );
      expect(v.personaId, 's1');
      expect(v.requestedAction, 'retire');
      expect(v.allowed, isFalse);
      expect(v.reason, 'blocked_primary_persona');
      expect(v.requiresSuccessor, isFalse);
    });
  });

  group('ActivePersonaContextWireDto', () {
    test('ownerUserId does not backfill an empty personaId', () {
      final dto = ActivePersonaContextWireDto.fromMap(<String, dynamic>{
        'personaId': '',
        'ownerUserId': 'ctx_u',
        'displayName': '展示',
      });
      expect(dto.personaId, '');
      expect(dto.ownerUserId, 'ctx_u');
    });
  });

  group('PersonaManagementSummaryWireDto', () {
    test('canonical items wins and retired personas is ignored', () {
      final dto = PersonaManagementSummaryWireDto.fromMap(<String, dynamic>{
        'items': <Map<String, dynamic>>[
          <String, dynamic>{'personaId': 's1', 'displayName': 'A'},
        ],
        'personas': <Map<String, dynamic>>[
          <String, dynamic>{'personaId': 'retired', 'displayName': 'B'},
        ],
        'quota': <String, dynamic>{'maxPersonas': 5, 'usedPersonas': 1},
      });
      expect(dto.items.length, 1);
      expect(dto.items.single['personaId'], 's1');
      final view =
          PersonaManagementSummaryViewData.fromPersonaManagementSummaryWire(
            dto,
          );
      expect(view.items.length, 1);
      expect(view.quota.usedPersonas, 1);
    });
  });

  group('RelationshipCapabilityResult', () {
    test('strict decoder 保留 canonical 能力位', () {
      final capability =
          decodeRelationshipCapabilityResult(const <String, Object?>{
            'viewerPersonaId': 'viewer-persona',
            'targetPersonaId': 't1',
            'relationState': 'following',
            'canFollow': false,
            'canUnfollow': true,
            'canFollowBack': false,
            'canGreet': true,
            'canOpenConversation': false,
            'canCreateDirectConversation': false,
            'canSendMessage': false,
            'hasPendingGreeting': false,
            'hasFormalConversation': false,
            'canStartVoiceCall': false,
            'canStartVideoCall': false,
            'isBlocked': false,
            'isBlockedBy': false,
          });
      expect(capability.viewerPersonaId, 'viewer-persona');
      expect(capability.targetPersonaId, 't1');
      expect(capability.relationState, 'following');
      expect(capability.canGreet, isTrue);
    });
  });

  group('AppearanceSettingsView', () {
    test('typed decoder → runtime snapshot', () {
      final view = decodeAppearanceSettingsView(<String, Object?>{
        'themeMode': 'dark',
        'fontSizePreset': 'lg',
        'source': 'sub_override',
        'ownerDefaultThemeMode': 'system',
        'ownerDefaultFontSizePreset': 'md',
        'hasPersonaOverride': true,
        'version': 3,
        'updatedAt': '2026-01-02T00:00:00Z',
      });
      final snapshot = appearance.AppearanceSettingsSnapshot.fromContract(view);
      expect(snapshot.themeMode.wireValue, 'dark');
      expect(snapshot.source, appearance.AppearanceSettingsSource.subOverride);
      expect(snapshot.version, 3);
    });
  });

  group('CallSettingsView', () {
    test('typed decoder 保留官方铃声与开关', () {
      final view = decodeCallSettingsView(<String, Object?>{
        'userId': 'u1',
        'defaultIncomingCallRingtoneId': 'official.blue-wave',
        'allowCallerRingtoneOverride': false,
        'enableCallVibration': true,
        'enableGroupCallRing': false,
        'version': 2,
        'updatedAt': '2026-01-02T00:00:00Z',
      });
      expect(
        view.defaultIncomingCallRingtoneId?.wireValue,
        'official.blue-wave',
      );
      expect(view.allowCallerRingtoneOverride, isFalse);
    });

    test('canonical null ringtone 解码为 null', () {
      final view = decodeCallSettingsView(<String, Object?>{
        'userId': 'u1',
        'defaultIncomingCallRingtoneId': null,
        'allowCallerRingtoneOverride': true,
        'enableCallVibration': true,
        'enableGroupCallRing': true,
        'version': 1,
        'updatedAt': '2026-01-02T00:00:00Z',
      });
      expect(view.defaultIncomingCallRingtoneId, isNull);
      expect(view.allowCallerRingtoneOverride, isTrue);
    });
  });

  group('PrivacySettingsView', () {
    test('typed decoder 保留 blockedKeywords', () {
      final view = decodePrivacySettingsView(<String, Object?>{
        'userId': 'u1',
        'allowStrangerMsg': true,
        'profileVisibility': 'public',
        'contentLanguage': null,
        'feedPreference': null,
        'assistantEnabled': true,
        'blockedKeywords': <String>['a', 'b'],
        'version': 1,
        'updatedAt': '2026-01-02T00:00:00Z',
      });
      expect(view.blockedKeywords, ['a', 'b']);
    });
  });
}

void _expectVersionedAvatarOrUnavailable(String? url, int version) {
  final resolved = url ?? '';
  final endpoint = CloudRuntimeConfig.mediaAvatarCdnBaseUrl.trim();
  if (endpoint.isEmpty) {
    expect(resolved, isEmpty);
    return;
  }
  expect(resolved, startsWith(endpoint));
  expect(resolved, contains('/v$version/'));
  expect(Uri.parse(resolved).queryParameters.containsKey('v'), isFalse);
}
