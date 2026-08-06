import 'package:quwoquan_app/runtime/shell/settings/appearance_settings_models.dart'
    as appearance;
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/persona_management_view_data_mapper.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/persona_relationship_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/domain/profile_interaction_activity_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/social_relation_search_item_view_mapper.dart';
import 'package:quwoquan_app/service/search_service/search/recent_search_state/adapters/recent_search_entry_mapper.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_query_contract.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;
import 'package:test/test.dart';

void main() {
  group('PersonaProfileView', () {
    test(
      'canonical identity does not expose an owner-user compatibility field',
      () {
        final profile = _profile(personaId: 'u_owner', displayName: 'nick');

        expect(profile.personaId, 'u_owner');
        expect(profile.displayName, 'nick');
        expect(profile.toWire(), isNot(contains('ownerUserId')));
      },
    );

    test('backgroundUrl uses the canonical wire key', () {
      final profile = _profile(
        personaId: 'u1',
        backgroundUrl: 'https://bg.example/x.jpg',
      );

      expect(profile.backgroundUrl, 'https://bg.example/x.jpg');
      expect(profile.toWire()['backgroundUrl'], 'https://bg.example/x.jpg');
    });

    test('public profile decoder rejects internal CAS and package fields', () {
      final payload = _profile(
        personaId: 'sys_travelphoto_0800_sub_01',
        subjectType: contracts.ProfileOwnerKind.creator,
        userHandle: 'set-marker',
        displayName: '片场坐标',
        identityTags: const <String>['creator', 'travel', 'photography'],
      ).toWire()..['avatarSha256'] = 'internal-only';

      expect(
        () => contracts.PersonaProfileView.fromWire(payload),
        throwsFormatException,
      );
    });

    test('toWire and fromWire round-trip stays on one canonical shape', () {
      final profile = _profile(
        personaId: 'ps1',
        subjectType: contracts.ProfileOwnerKind.account,
        userHandle: 'handle_1',
        displayName: 'd',
      );
      final restored = contracts.PersonaProfileView.fromWire(profile.toWire());

      expect(restored.personaId, profile.personaId);
      expect(restored.userHandle, 'handle_1');
      expect(restored.followerCount, profile.followerCount);
    });
  });

  group('PersonaProfileViewData', () {
    test('display name falls back to canonical personaId', () {
      final view = personaProfileViewDataFromWire(
        _profile(
          personaId: 'only_id',
          displayName: '',
          userHandle: 'only_handle',
        ),
      );

      expect(view.displayName, 'only_id');
      expect(view.userHandle, 'only_handle');
      expect(view.subjectType, 'persona');
    });

    test('avatar reference is resolved only through the runtime endpoint', () {
      final view = personaProfileViewDataFromWire(
        _profile(
          personaId: 'u_avatar',
          avatarUrl:
              'media/avatar/s/archived-avatar/user/u_avatar/v1/profile.png',
        ),
      );

      _expectAvatarOrUnavailable(view.avatarUrl);
    });
  });

  group('ProfileSocialRelationRowViewData', () {
    test('canonical following row preserves persona identity and relation', () {
      final view = ProfileSocialRelationRowViewData.fromFollowingWire(
        contracts.FollowingListItemView(
          personaId: 'rel_1',
          userHandle: 'friend',
          displayName: '朋友',
          avatarUrl: 'https://a.test/1.jpg',
          profileVisibility: contracts.ProfileVisibility.public,
          relationState: contracts.RelationshipState.following,
          followedAt: DateTime.utc(2026, 2, 2),
          relationshipCapability: _capability(
            targetPersonaId: 'rel_1',
            relationState: contracts.RelationshipState.following,
          ),
        ),
      );

      expect(view.personaId, 'rel_1');
      expect(view.displayName, '朋友');
      expect(view.relationState, 'following');
    });
  });

  group('ProfileInteractionActivityViewData', () {
    test('comment identity is preserved for deep-link consumption', () {
      final view = ProfileInteractionActivityViewData.fromWire(
        _activity(
          activityId: 'comment_reply_9',
          activityType: contracts.InteractionActivityType.comment,
          commentKind: 'reply',
          commentId: 'comment_reply_9',
          parentCommentId: 'comment_top_1',
        ),
      );

      expect(view.commentId, 'comment_reply_9');
      expect(view.parentCommentId, 'comment_top_1');
    });

    test('actor and display avatar versions remain source-derived', () {
      final view = ProfileInteractionActivityViewData.fromWire(
        _activity(
          activityId: 'activity_1',
          activityType: contracts.InteractionActivityType.like,
          actorAvatarUrl: 'media/avatar/s/mock/seed/test_actor/v7/avatar.jpg',
          actorAvatarVersion: 7,
          displayAvatarVersion: 7,
        ),
      );

      expect(view.actorAvatarVersion, 7);
      _expectVersionedAvatarOrUnavailable(view.actorAvatarUrl, 7);
      expect(view.displayAvatarVersion, 7);
      _expectVersionedAvatarOrUnavailable(view.displayAvatarUrl, 7);
    });
  });

  group('PersonaManagementItemView', () {
    test('canonical public shape excludes credential plaintext', () {
      final item = _personaItem(
        personaId: 'per_1',
        displayName: '分身名',
        userHandle: 'persona_handle',
        inheritsProfileFromOwner: false,
        overriddenProfileFields: const <String>['displayName'],
      );

      expect(item.personaId, 'per_1');
      expect(item.displayName, '分身名');
      expect(item.userHandle, 'persona_handle');
      expect(item.inheritsProfileFromOwner, isFalse);
      expect(item.overriddenProfileFields, <String>['displayName']);
      expect(item.toWire(), isNot(contains('phone')));
      expect(item.toWire(), isNot(contains('email')));
    });

    test('App view consumes the generated owner directly', () {
      final view = personaManagementItemViewDataFromWire(
        _personaItem(personaId: 'per_1', displayName: '分身名'),
      );

      expect(view.personaId, 'per_1');
      expect(view.subjectType, 'persona');
      expect(view.displayName, '分身名');
    });
  });

  group('UpdatePersonaCommand', () {
    test('generated mutation request has no credential fields', () {
      final command = contracts.UpdatePersonaCommand(
        personaId: 'per_1',
        displayName: '分身名',
      );

      expect(command.toWire(), isNot(contains('phone')));
      expect(command.toWire(), isNot(contains('email')));
    });
  });

  group('PersonaManagementQuotaViewData', () {
    test('non-positive canonical quota is safely presented as five', () {
      final view = PersonaManagementQuotaViewData.fromWire(
        const contracts.PersonaManagementQuotaView(
          ownerUserId: 'owner-1',
          totalCount: 0,
          quotaLimit: 0,
          remainingCount: 0,
          activePersonaId: 'persona-1',
          primaryPersonaId: 'persona-1',
        ),
      );

      expect(view.maxPersonas, 5);
      expect(view.usedPersonas, 0);
    });
  });

  group('ActivePersonaContextView', () {
    test('persona envelope fields have one generated owner', () {
      final projection = _activeContext(
        personaId: 'persona_main',
        ownerUserId: 'user_main',
        contextVersion: 3,
        personaSnapshotVersion: 2,
        sourceSurfaceId: 'notification_center',
        explicitOverride: true,
      );

      expect(projection.personaId, 'persona_main');
      expect(projection.ownerUserId, 'user_main');
      expect(projection.contextVersion, 3);
      expect(projection.personaSnapshotVersion, 2);
      expect(projection.sourceSurfaceId, 'notification_center');
      expect(projection.explicitOverride, isTrue);
    });

    test('App view exposes the canonical typed envelope', () {
      final view = activePersonaContextViewDataFromWire(
        _activeContext(
          personaId: 'persona_photo',
          ownerUserId: 'user_owner',
          contextVersion: 5,
          personaSnapshotVersion: 7,
        ),
      );

      expect(view.personaId, 'persona_photo');
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
        isNot(contains('personaContextVersion')),
      );
    });
  });

  group('RelationshipCapabilityView', () {
    test('canonical relation state and capability bits are typed', () {
      final capability = _capability(
        relationState: contracts.RelationshipState.mutual,
        canFollow: true,
      );

      expect(capability.relationState, contracts.RelationshipState.mutual);
      expect(capability.canFollow, isTrue);
    });

    test(
      'missing required capability bits fail closed in the generated decoder',
      () {
        expect(
          () => contracts.RelationshipCapabilityView.fromWire(
            const <String, Object?>{},
          ),
          throwsFormatException,
        );
      },
    );
  });

  group('SocialRelationSearchItemViewData', () {
    test('nested capability is the only relation source', () {
      final view = SocialRelationSearchItemViewMapper.fromWire(
        contracts.SocialRelationSearchItemView(
          personaId: 'search_u2',
          userHandle: 'search-user',
          displayName: '搜索用户',
          avatarUrl:
              'media/avatar/s/archived-avatar/user/search_u2/v1/profile.png',
          chatAvailable: true,
          relationshipCapability: _capability(
            targetPersonaId: 'search_u2',
            relationState: contracts.RelationshipState.mutual,
            canOpenConversation: true,
          ),
        ),
      );

      expect(view.relationshipCapability.relationState, 'mutual');
      expect(view.chatAvailable, isTrue);
      _expectAvatarOrUnavailable(view.avatarUrl);
    });
  });

  group('RecentSearchEntryWire', () {
    test('scope and updatedAt map into one App view', () {
      final wire = contracts.decodeRecentSearchEntryWire(<String, Object?>{
        'entryId': 'e1',
        'query': '摄影',
        'scope': 'content',
        'updatedAt': '2026-03-01T08:00:00Z',
      });
      final view = recentSearchEntryFromWire(wire);

      expect(wire.scope, 'content');
      expect(view.entryId, 'e1');
      expect(view.scope, SearchScope.content);
    });
  });

  group('RelationshipViewData', () {
    test(
      'relation state derives the convenience flags without a second wire',
      () {
        const view = RelationshipViewData(
          relationState: 'mutual',
          isBlocked: false,
          isBlockedBy: false,
        );

        expect(view.isFollowing, isTrue);
        expect(view.isFollowedBy, isTrue);
        expect(view.isMutual, isTrue);
        expect(view.isBlocked, isFalse);
      },
    );
  });

  group('UserProfileStatsWire', () {
    test('generated counts map to App stats', () {
      const wire = contracts.UserProfileStatsWire(
        followerCount: 10,
        followingCount: 20,
        postCount: 3,
        circleCount: 4,
        likeCount: 5,
      );
      final view = UserProfileStatsViewData.fromWire(wire);

      expect(view.followerCount, 10);
      expect(view.followingCount, 20);
    });
  });

  group('PersonaLifecycleGuardViewData', () {
    test('canonical lifecycle guard maps its enum values', () {
      final view = PersonaLifecycleGuardViewData.fromWire(
        const contracts.PersonaLifecycleGuardView(
          personaId: 's1',
          requestedAction: contracts.PersonaLifecycleAction.retire,
          allowed: false,
          reason: contracts.PersonaLifecycleGuardReason.blockedPrimaryPersona,
          requiresSuccessor: false,
        ),
      );

      expect(view.personaId, 's1');
      expect(view.requestedAction, 'retire');
      expect(view.allowed, isFalse);
      expect(view.reason, 'blocked_primary_persona');
    });
  });

  group('PersonaManagementSummaryViewData', () {
    test('summary consumes canonical items, quota, and active context', () {
      final summary = contracts.PersonaManagementSummaryView(
        items: <contracts.PersonaManagementItemView>[
          _personaItem(personaId: 's1', displayName: 'A'),
        ],
        quota: const contracts.PersonaManagementQuotaView(
          ownerUserId: 'owner-1',
          totalCount: 1,
          quotaLimit: 5,
          remainingCount: 4,
          activePersonaId: 's1',
          primaryPersonaId: 's1',
        ),
        activeContext: _activeContext(personaId: 's1', ownerUserId: 'owner-1'),
      );
      final view = personaManagementSummaryViewDataFromWire(summary);

      expect(view.items.length, 1);
      expect(view.items.single.personaId, 's1');
      expect(view.quota.usedPersonas, 1);
    });
  });

  group('RelationshipCapabilityView', () {
    test('strict decoder preserves canonical capability bits', () {
      final capability = contracts.decodeRelationshipCapabilityView(
        _capability(
          viewerPersonaId: 'viewer-persona',
          targetPersonaId: 't1',
          relationState: contracts.RelationshipState.following,
          canGreet: true,
        ).toWire(),
      );

      expect(capability.viewerPersonaId, 'viewer-persona');
      expect(capability.targetPersonaId, 't1');
      expect(capability.relationState.wireName, 'following');
      expect(capability.canGreet, isTrue);
    });
  });

  group('Settings views', () {
    test('appearance decoder maps to the runtime snapshot', () {
      final view = contracts.decodeAppearanceSettingsView(<String, Object?>{
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

    test('call settings preserve official ringtone and switches', () {
      final view = contracts.decodeCallSettingsView(<String, Object?>{
        'userId': 'u1',
        'defaultIncomingCallRingtoneId': 'official.blue-wave',
        'allowCallerRingtoneOverride': false,
        'enableCallVibration': true,
        'enableGroupCallRing': false,
        'version': 2,
        'updatedAt': '2026-01-02T00:00:00Z',
      });

      expect(view.defaultIncomingCallRingtoneId, 'official.blue-wave');
      expect(view.allowCallerRingtoneOverride, isFalse);
    });

    test('privacy settings preserve blocked keywords', () {
      final view = contracts.decodePrivacySettingsView(<String, Object?>{
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

      expect(view.blockedKeywords, <String>['a', 'b']);
    });
  });
}

contracts.PersonaProfileView _profile({
  required String personaId,
  contracts.ProfileOwnerKind subjectType = contracts.ProfileOwnerKind.persona,
  String userHandle = 'handle',
  String displayName = '昵称',
  String? avatarUrl,
  String? backgroundUrl,
  List<String>? identityTags,
}) {
  return contracts.PersonaProfileView(
    personaId: personaId,
    subjectType: subjectType,
    userHandle: userHandle,
    displayName: displayName,
    nicknameCustomized: true,
    avatarUrl: avatarUrl,
    backgroundUrl: backgroundUrl,
    identityTags: identityTags,
    followerCount: 1,
    followingCount: 2,
    postCount: 3,
    circleCount: 4,
    likeCount: 5,
    profileVisibility: contracts.ProfileVisibility.public,
    isolationLevel: contracts.IsolationLevel.open,
    inheritsFromOwner: false,
    updatedAt: DateTime.utc(2026, 2, 2),
  );
}

contracts.PersonaManagementItemView _personaItem({
  required String personaId,
  required String displayName,
  String? userHandle,
  bool inheritsProfileFromOwner = true,
  List<String>? overriddenProfileFields,
}) {
  return contracts.PersonaManagementItemView(
    personaId: personaId,
    displayName: displayName,
    userHandle: userHandle,
    isolationLevel: contracts.IsolationLevel.open,
    isPrimary: personaId == 's1',
    isActive: personaId == 's1',
    status: contracts.PersonaStatus.active,
    inheritsProfileFromOwner: inheritsProfileFromOwner,
    overriddenProfileFields: overriddenProfileFields,
    profileVisibility: contracts.ProfileVisibility.public,
    updatedAt: DateTime.utc(2026, 2, 2),
  );
}

contracts.ActivePersonaContextView _activeContext({
  required String personaId,
  required String ownerUserId,
  int contextVersion = 1,
  int personaSnapshotVersion = 1,
  String? sourceSurfaceId,
  bool explicitOverride = false,
}) {
  return contracts.ActivePersonaContextView(
    ownerUserId: ownerUserId,
    personaId: personaId,
    subjectType: contracts.ProfileOwnerKind.persona,
    displayName: personaId,
    avatarVersion: 0,
    isPrimary: true,
    isolationLevel: contracts.IsolationLevel.open,
    profileVisibility: contracts.ProfileVisibility.public,
    contextVersion: contextVersion,
    personaSnapshotVersion: personaSnapshotVersion,
    sourceSurfaceId: sourceSurfaceId,
    explicitOverride: explicitOverride,
    switchedAt: DateTime.utc(2026, 2, 2),
  );
}

contracts.RelationshipCapabilityView _capability({
  String viewerPersonaId = 'viewer',
  String targetPersonaId = 'target',
  contracts.RelationshipState relationState =
      contracts.RelationshipState.notFollowing,
  bool canFollow = false,
  bool canGreet = false,
  bool canOpenConversation = false,
}) {
  return contracts.RelationshipCapabilityView(
    viewerPersonaId: viewerPersonaId,
    targetPersonaId: targetPersonaId,
    relationState: relationState,
    canFollow: canFollow,
    canUnfollow: false,
    canFollowBack: false,
    canGreet: canGreet,
    canOpenConversation: canOpenConversation,
    canCreateDirectConversation: canOpenConversation,
    canSendMessage: canOpenConversation,
    hasPendingGreeting: false,
    hasFormalConversation: canOpenConversation,
    canStartVoiceCall: false,
    canStartVideoCall: false,
    isBlocked: false,
    isBlockedBy: false,
  );
}

contracts.ProfileInteractionActivityView _activity({
  required String activityId,
  required contracts.InteractionActivityType activityType,
  String commentKind = '',
  String? commentId,
  String? parentCommentId,
  String? actorAvatarUrl,
  int actorAvatarVersion = 0,
  int displayAvatarVersion = 0,
}) {
  return contracts.ProfileInteractionActivityView(
    ownerPersonaId: 'owner',
    activityId: activityId,
    activityType: activityType,
    direction: contracts.InteractionDirection.received,
    sourceType: 'content',
    sourceEventId: 'source-$activityId',
    sourceVersion: 1,
    viewerReactionVersion: 1,
    targetVersion: 1,
    active: true,
    commentKind: commentKind,
    commentId: commentId,
    parentCommentId: parentCommentId,
    viewerReaction: contracts.CommentReactionType.none,
    actorPersonaId: 'u_a',
    actorDisplayName: '某人',
    actorAvatarUrl: actorAvatarUrl,
    actorAvatarVersion: actorAvatarVersion,
    targetPersonaId: 'owner',
    targetContentId: 'post_99',
    targetContentType: contracts.ContentType.article,
    targetKind: 'record',
    targetAvailability: 'active',
    targetReplyCount: 0,
    displayPersonaId: 'u_a',
    displayName: '某人',
    displayAvatarUrl: actorAvatarUrl,
    displayAvatarVersion: displayAvatarVersion,
    primaryText: '互动了你的记录',
    previewMediaKind: 'none',
    previewUnavailable: false,
    filterKeys: const <String>['all'],
    createdAt: DateTime.utc(2026, 2, 2),
    occurredAt: DateTime.utc(2026, 2, 2),
  );
}

void _expectAvatarOrUnavailable(String? url) {
  final resolved = url ?? '';
  final endpoint = CloudRuntimeConfig.mediaAvatarCdnBaseUrl.trim();
  if (endpoint.isEmpty) {
    expect(resolved, isEmpty);
    return;
  }
  expect(resolved, startsWith(endpoint));
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
