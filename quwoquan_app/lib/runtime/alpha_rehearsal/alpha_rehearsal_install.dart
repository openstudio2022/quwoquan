import 'package:quwoquan_app/runtime/alpha_rehearsal/executor/rehearsal_cloud_operation_executor.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/content_handlers.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/handler_registry.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/synthetic_login_ports.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_space_binding.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/config/rehearsal_storage_namespace.dart';
import 'package:quwoquan_app/runtime/config/rehearsal_storage_observer.dart';
import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/application/public/synthetic_challenge_port.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/application/public/synthetic_session_port.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_identity.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_app/runtime/auth/rehearsal_auth_port.dart';
import 'package:quwoquan_app/runtime/config/generated/offline_content_bundle_identity.g.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/di/login_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/adapters/discovery_feed_query_bundled.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_projection_mapper.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/user_homepage_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/persona_management_view_data_mapper.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/profile_query_bundled.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

AlphaRehearsalStore? installedAlphaRehearsalStore;

/// 启动 owner 持有该值，显式注入共享 application ports；不提供全局永久 hook。
final class AlphaRehearsalComposition {
  AlphaRehearsalComposition._(
    this.space,
    this.store,
    this.synthetic,
    this.executor,
    this.storageObserver,
  );
  final VerifiedRehearsalSpace space;
  final AlphaRehearsalStore store;
  final AlphaSyntheticLoginPorts? synthetic;
  final AlphaRehearsalCloudOperationExecutor executor;
  SyntheticChallengePort? get challengePort => synthetic;
  SyntheticSessionPort? get sessionPort => synthetic;
  RehearsalStorageNamespace? get storageNamespace =>
      synthetic?.binding.storageNamespace;
  final RehearsalStorageObserver? storageObserver;
  void dispose() {
    executor.dispose();
    synthetic?.dispose();
    final persistence = store.persistence;
    if (persistence is FileRehearsalPersistence) {
      persistence.observation?.invalidate();
    }
  }
}

/// 只构造当前空间；不会读存储或改变 provider/global 装配。
AlphaRehearsalComposition createAlphaRehearsalComposition({
  required VerifiedRehearsalSpace space,
  required VerifiedRehearsalSpace? Function() currentSpace,
  required FileStorageGateway Function() gatewayFactory,
  AlphaRehearsalStore? store,
  RehearsalStorageObserver? storageObserver,
}) {
  void requireCurrent() {
    VerifiedRehearsalSpace? current;
    try {
      current = currentSpace();
    } catch (_) {
      throw contentCapabilityUnavailable('rehearsal_space_binding');
    }
    if (!identical(current, space) ||
        space.snapshotDigest != offlineContentManifestDigest) {
      throw contentCapabilityUnavailable('rehearsal_space_binding');
    }
  }

  requireCurrent();
  final binding = RehearsalSpaceBinding.verified(space);
  if (store != null) {
    binding.verifyStorage(
      snapshot: store.snapshotDigest,
      instance: store.instanceId,
    );
  }
  if (storageObserver != null) {
    storageObserver.requireCurrent();
    if (!identical(storageObserver.space, space) || store != null) {
      throw contentCapabilityUnavailable('rehearsal_observation_binding');
    }
  }
  final gateway = gatewayFactory();
  requireCurrent();
  final observation = storageObserver?.attach(
    'rehearsal',
    binding.storageNamespace!,
  );
  final resolved =
      store ??
      AlphaRehearsalStore.bound(
        binding: binding,
        gateway: gateway,
        observation: observation,
      );
  final identityOwner = AlphaRehearsalIdentityOwner(resolved);
  final synthetic = space.isIsolated
      ? AlphaSyntheticLoginPorts(
          space: space,
          currentSpace: currentSpace,
          gateway: gateway,
          store: resolved,
          identityOwner: identityOwner,
        )
      : null;
  return AlphaRehearsalComposition._(
    space,
    resolved,
    synthetic,
    AlphaRehearsalCloudOperationExecutor(
      store: resolved,
      identityOwner: identityOwner,
      registry: AlphaRehearsalHandlerRegistry.withPostExists(bundledPostExists),
    ),
    storageObserver,
  );
}

AlphaRehearsalComposition installAlphaRehearsalRuntime({
  AlphaRehearsalStore? store,
  RehearsalStorageObserver? storageObserver,
}) {
  final space = CloudRuntimeConfig.rehearsalSpace;
  if (space == null) {
    throw contentCapabilityUnavailable('rehearsal_space_binding');
  }
  final composition = createAlphaRehearsalComposition(
    space: space,
    currentSpace: () => CloudRuntimeConfig.rehearsalSpace,
    gatewayFactory: createFileStorageGateway,
    store: store,
    storageObserver: storageObserver,
  );
  // isolated 没有标准phone/grant端口；父级必须消费返回的合成typed ports。
  if (space.isIsolated) return composition;
  final resolved = composition.store;
  installedAlphaRehearsalStore = resolved;
  installRehearsalAuth(AlphaRehearsalAuth(resolved));
  configureLoginCapabilityFailure(() => null);
  _installBundledOverlays(resolved);
  return composition;
}

void clearAlphaRehearsalRuntime() {
  installedAlphaRehearsalStore = null;
  clearRehearsalAuth();
  configureLoginCapabilityFailure(null);
  bundledFollowingFeedOverlay = null;
  bundledPrivateProfileLookup = null;
  bundledPersonaListLookup = null;
  bundledHomepageLookup = null;
}

void _installBundledOverlays(AlphaRehearsalStore store) {
  bundledFollowingFeedOverlay =
      ({
        required String category,
        String? channelId,
        String? type,
        String? subCategory,
        required int limit,
        String? cursor,
        String sort = 'recommend',
        String? sessionId,
        String? feedRequestId,
        CloudOperationCancellationSignal? cancellation,
        DateTime? deadlineAt,
      }) async {
        await store.ensureLoaded();
        final actor = store.currentPersonaId ?? '';
        final following = actor.isEmpty
            ? const <String>{}
            : store.followingOf(actor).toSet();
        if (following.isEmpty) {
          return const DiscoveryFeedPage(
            items: <ContentPostViewData>[],
            outcome: ContentFeedOutcome.empty,
            emptyReason: ContentFeedEmptyReason.noEligibleContent,
          );
        }
        final bundle = await OfflineContentBundle.load();
        final posts = bundle
            .rows('posts')
            .map(
              (row) => ContentPostProjection.fromWire(
                row['projection']! as Map<String, Object?>,
              ),
            )
            .where((post) => following.contains(post.authorId))
            .toList(growable: false);
        final page = posts.take(limit).toList(growable: false);
        return DiscoveryFeedPage(
          items: page
              .map(const ContentPostProjectionMapper().toDto)
              .toList(growable: false),
          outcome: page.isEmpty
              ? ContentFeedOutcome.empty
              : ContentFeedOutcome.content,
          emptyReason: page.isEmpty
              ? ContentFeedEmptyReason.noEligibleContent
              : null,
        );
      };

  bundledPrivateProfileLookup = (userId) async {
    await store.ensureLoaded();
    final resolvedId = _rehearsalPersonaId(store, userId);
    if (resolvedId == null) {
      return null;
    }
    return _profileFor(store, resolvedId);
  };

  bundledHomepageLookup = (personaId) async {
    await store.ensureLoaded();
    final resolvedId = _rehearsalPersonaId(store, personaId);
    if (resolvedId == null) {
      return null;
    }
    final profile = await _profileFor(store, resolvedId);
    final stats = UserProfileStatsViewData.fromProfile(profile);
    final viewer = store.currentPersonaId ?? '';
    final self = viewer.isNotEmpty && viewer == resolvedId;
    final following =
        viewer.isNotEmpty && store.followingOf(viewer).contains(resolvedId);
    final followedBy =
        store.follows[store.followKey(resolvedId, viewer)]?['active'] == true;
    final blocked =
        store.blocks[store.followKey(viewer, resolvedId)]?['active'] == true;
    final blockedBy =
        store.blocks[store.followKey(resolvedId, viewer)]?['active'] == true;
    final relation = self
        ? 'self'
        : following && followedBy
        ? 'mutual'
        : following
        ? 'following'
        : followedBy
        ? 'followed_by'
        : 'not_following';
    return UserHomepageBundleViewData(
      profile: profile,
      stats: stats,
      relationshipCapability: RelationshipCapabilityViewData.fromWire(
        RelationshipCapabilityView.fromWire(<String, Object?>{
          'viewerPersonaId': viewer.isEmpty ? 'guest' : viewer,
          'targetPersonaId': resolvedId,
          'relationState': relation,
          'canFollow': !self && !following && !blocked && viewer.isNotEmpty,
          'canUnfollow': following,
          'canFollowBack': followedBy && !following,
          'canGreet': !self && viewer.isNotEmpty && !blocked,
          'canOpenConversation': following || followedBy || self,
          'canCreateDirectConversation': !self && viewer.isNotEmpty && !blocked,
          'canSendMessage': following || followedBy || self,
          'hasPendingGreeting': false,
          'hasFormalConversation': false,
          'canStartVoiceCall': following || followedBy,
          'canStartVideoCall': following || followedBy,
          'isBlocked': blocked,
          'isBlockedBy': blockedBy,
        }),
      ),
      tabCounts: UserHomepageTabCountsViewData.fromStats(stats),
      viewerContext: UserHomepageViewerContextViewData(
        viewerPersonaId: viewer,
        isOwner: self,
        isGuest: viewer.isEmpty,
        relationToTarget: relation,
        canViewFullProfile: true,
      ),
      cacheVersion: store.snapshotDigest,
    );
  };

  bundledPersonaListLookup = () async {
    await store.ensureLoaded();
    return store.identities.values
        .map(
          (identity) => PersonaManagementItemViewData(
            personaId: '${identity['personaId'] ?? ''}',
            displayName: '${identity['displayName'] ?? '演练用户'}',
            userHandle: '${identity['personaId'] ?? ''}',
            avatarUrl: '${identity['avatarUrl'] ?? ''}',
            isolationLevel: 'open',
            profileVisibility: 'public',
            isPrimary: true,
            isActive: identity['ownerId'] == store.currentOwnerId,
            status: 'active',
            retiredAt: null,
            hasPublishedContent: false,
            inheritsProfileFromOwner: true,
            overriddenProfileFields: const <String>[],
            lastProfileSyncAt: null,
            lastProfileSyncSource: '',
            lastActivatedAt: null,
            subjectType: 'account',
          ),
        )
        .toList(growable: false);
  };
}

String? _rehearsalPersonaId(AlphaRehearsalStore store, String userId) {
  final normalized = userId.trim();
  if (normalized.isEmpty) {
    return null;
  }
  final me = store.currentPersonaId ?? '';
  final owner = store.currentOwnerId ?? '';
  if (normalized == 'me' || normalized == me || normalized == owner) {
    return me.isEmpty ? null : me;
  }
  for (final identity in store.identities.values) {
    if (identity['personaId'] == normalized ||
        identity['ownerId'] == normalized) {
      return '${identity['personaId']}';
    }
  }
  return null;
}

Future<PersonaProfileViewData> _profileFor(
  AlphaRehearsalStore store,
  String personaId,
) async {
  final bundle = await OfflineContentBundle.load();
  final rows = bundle.rows('creators').where((row) {
    final projection = row['projection']! as Map<String, Object?>;
    return projection['personaId'] == personaId;
  });
  if (rows.length == 1) {
    return personaProfileViewDataFromWire(
      PersonaProfileView.fromWire(
        rows.single['projection']! as Map<String, Object?>,
      ),
    );
  }
  final identity = store.identities.values
      .cast<Map<String, Object?>?>()
      .firstWhere((row) => row?['personaId'] == personaId, orElse: () => null);
  return PersonaProfileViewData(
    personaId: personaId,
    ownerUserId: '${identity?['ownerId'] ?? personaId}',
    subjectType: 'account',
    userHandle: personaId,
    displayName: '${identity?['displayName'] ?? '演练用户'}',
    nicknameCustomized: true,
    avatarUrl: '${identity?['avatarUrl'] ?? ''}',
    backgroundUrl: '',
    bio: '本地演练账号，不连接真实后端。',
    followerCount: store.follows.values
        .where(
          (row) => row['targetPersonaId'] == personaId && row['active'] == true,
        )
        .length,
    followingCount: store.followingOf(personaId).length,
    postCount: 0,
    circleCount: 0,
    likeCount: 0,
    isolationLevel: 'open',
    profileVisibility: 'public',
    inheritsFromOwner: true,
    overriddenFields: const <String>[],
    updatedAt: DateTime.now().toUtc(),
  );
}
