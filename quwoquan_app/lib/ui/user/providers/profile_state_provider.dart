import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_created_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/greeting_reply_result_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/user/greeting_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart'
    show SubAccountProfileViewData, UserHomepageBundleViewData;
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

class ProfileState {
  const ProfileState({
    required this.userId,
    this.profile,
    this.activeSubTab = CreationSubTab.all,
    this.activeWorkFormat = CreationWorkFormat.all,
    this.activeVisibility = CreationVisibility.all,
    this.interactionSubTab = InteractionSubTab.likes,
    this.interactionDirection = InteractionDirection.received,
    this.creations = const [],
    this.circles = const [],
    this.isLoading = false,
    this.isFollowing = false,
    this.capability,
    this.optimisticFollowOverride,
    this.failure,
  });

  final String userId;
  final SubAccountProfileViewData? profile;
  final CreationSubTab activeSubTab;
  final CreationWorkFormat activeWorkFormat;
  final CreationVisibility activeVisibility;
  final InteractionSubTab interactionSubTab;
  final InteractionDirection interactionDirection;

  final List<PostBaseDto> creations;
  final List<CircleDto> circles;
  final bool isLoading;
  final bool isFollowing;

  /// 关系能力位投影（null = 未载入）
  final RelationshipCapabilityDto? capability;
  final bool? optimisticFollowOverride;

  /// 首屏聚合失败的结构化错误（null = 无错误）。
  final RuntimeFailureBase? failure;

  /// 结构化首屏错误文案（null = 无错误）。
  String? get errorMessage =>
      failure == null ? null : runtimeFailureDisplayMessage(failure!).trim();

  /// 首屏聚合是否失败（用于错误态分支：重试 / 降级提示）。
  bool get hasLoadError => failure != null;

  bool get hasCacheFallback => failure != null && profile != null;

  RelationshipCapabilityDto? get displayCapability {
    final base = capability;
    final override = optimisticFollowOverride;
    if (base == null || override == null) {
      return base;
    }
    return _copyCapabilityWithFollowState(base, override);
  }

  ProfileState copyWith({
    SubAccountProfileViewData? profile,
    CreationSubTab? activeSubTab,
    CreationWorkFormat? activeWorkFormat,
    CreationVisibility? activeVisibility,
    InteractionSubTab? interactionSubTab,
    InteractionDirection? interactionDirection,
    List<PostBaseDto>? creations,
    List<CircleDto>? circles,
    bool? isLoading,
    bool? isFollowing,
    RelationshipCapabilityDto? capability,
    bool? optimisticFollowOverride,
    RuntimeFailureBase? failure,
    bool clearCapability = false,
    bool clearOptimisticFollowOverride = false,
    bool clearError = false,
  }) {
    return ProfileState(
      userId: userId,
      profile: profile ?? this.profile,
      activeSubTab: activeSubTab ?? this.activeSubTab,
      activeWorkFormat: activeWorkFormat ?? this.activeWorkFormat,
      activeVisibility: activeVisibility ?? this.activeVisibility,
      interactionSubTab: interactionSubTab ?? this.interactionSubTab,
      interactionDirection: interactionDirection ?? this.interactionDirection,
      creations: creations ?? this.creations,
      circles: circles ?? this.circles,
      isLoading: isLoading ?? this.isLoading,
      isFollowing: isFollowing ?? this.isFollowing,
      capability: clearCapability ? null : (capability ?? this.capability),
      optimisticFollowOverride: clearOptimisticFollowOverride
          ? null
          : (optimisticFollowOverride ?? this.optimisticFollowOverride),
      failure: clearError ? null : (failure ?? this.failure),
    );
  }
}

class ProfileNotifier extends Notifier<ProfileState> {
  ProfileNotifier(this._userId);

  final String _userId;

  @override
  ProfileState build() {
    ref.listen<UserRelationshipState>(userRelationshipStateProvider, (
      previous,
      next,
    ) {
      _syncFollowStateFromShared(next);
    });
    Future.microtask(loadProfile);
    return ProfileState(userId: _userId);
  }

  void _syncFollowStateFromShared(UserRelationshipState relationshipState) {
    final targetSubAccountId = state.profile?.subAccountId.isNotEmpty == true
        ? state.profile!.subAccountId
        : _userId;
    if (!relationshipState.hasRelationshipStateFor(targetSubAccountId)) {
      return;
    }
    final sharedFollowing = relationshipState.isFollowing(targetSubAccountId);
    final capability = state.capability;
    final shouldOverride =
        capability != null && capability.viewerFollowsTarget != sharedFollowing;
    if (state.isFollowing == sharedFollowing &&
        ((!shouldOverride && state.optimisticFollowOverride == null) ||
            state.optimisticFollowOverride == sharedFollowing)) {
      return;
    }
    state = state.copyWith(
      isFollowing: sharedFollowing,
      optimisticFollowOverride: shouldOverride ? sharedFollowing : null,
      clearOptimisticFollowOverride: !shouldOverride,
    );
  }

  bool? _pendingFollowIntent(String subAccountId) {
    for (final entry
        in ref.read(clientStateSyncOutboxProvider).entries.reversed) {
      if (entry.objectType == 'profile' &&
          entry.intentType == 'follow' &&
          entry.objectId == subAccountId) {
        return entry.desiredBoolValue;
      }
    }
    return null;
  }

  Future<void> loadProfile() async {
    state = state.copyWith(isLoading: true, clearError: true);
    _recordProfileState(
      phase: 'onlineLoading',
      source: 'online',
      hasCache: state.profile != null,
      itemCount: state.creations.length,
    );
    try {
      final profileQuery = ref.read(
        profileQueryProvider(AppUiSurfaces.userProfile),
      );
      final contentRepo = ref.read(userProfileContentAuthorPostsReaderProvider);
      // 锁定决策 #1：homepage-bundle 一次聚合身份域真相（profile/stats/关系能力/
      // viewerContext），与作品/帖子内容并发补充，消除首屏串行阻塞。
      // 作品 Tab 由 content 域 ListUserPosts 单轨承载（user_work 投影已删除）。
      final results = await Future.wait(<Future<Object>>[
        profileQuery.getUserHomepageBundle(_userId),
        contentRepo.listUserPosts(userId: _userId),
      ]);
      final bundle = results[0] as UserHomepageBundleViewData;
      final postsPage = results[1] as CursorPage<PostBaseDto>;
      final posts = postsPage.items;
      final profile = bundle.profileWithStats;
      if (!ref.mounted) {
        return;
      }
      ref
          .read(postInteractionStateProvider.notifier)
          .applyConfirmedPosts(posts);
      final subAccountId = profile.subAccountId.isNotEmpty
          ? profile.subAccountId
          : _userId;
      // bundle 自带首屏关系能力快照（user 域聚合 follow/block 同源），作为 capability
      // seed，免去首屏额外 getCapability 串行请求。
      final bundleCapability = bundle.relationshipCapability;
      final reconcileCap = ref
          .read(relationshipCapabilityRepositoryProvider)
          .reconcilesCapabilityWithSharedRelationshipState;
      final sharedFollowing = ref
          .read(userRelationshipStateProvider)
          .isFollowing(subAccountId);
      final pendingFollowIntent = _pendingFollowIntent(subAccountId);
      final RelationshipCapabilityDto? seededCapability = bundleCapability;
      bool? optimisticFollowOverride;
      if (bundleCapability != null && reconcileCap) {
        final desiredFollowing = pendingFollowIntent ?? sharedFollowing;
        if (desiredFollowing != bundleCapability.viewerFollowsTarget) {
          optimisticFollowOverride = desiredFollowing;
        }
      }
      final seededFollowing =
          optimisticFollowOverride ??
          pendingFollowIntent ??
          seededCapability?.viewerFollowsTarget ??
          sharedFollowing;
      final fallbackError = postsPage.cacheFallbackError;
      final fallbackFailure = fallbackError == null
          ? null
          : CloudErrorMapper.runtimeFailureFromException(fallbackError);
      state = state.copyWith(
        profile: profile,
        creations: posts,
        isLoading: false,
        isFollowing: seededFollowing,
        capability: seededCapability,
        optimisticFollowOverride: optimisticFollowOverride,
        failure: fallbackFailure,
        clearError: fallbackError == null,
      );
      _recordProfileState(
        phase: fallbackError == null ? 'onlineSuccess' : 'cacheFallback',
        source: fallbackError == null ? 'online' : 'cache',
        error: fallbackError,
        copyKey: fallbackError == null ? null : 'profileCacheFallback',
        hasCache: fallbackError != null,
        cacheAgeMs: postsPage.cacheAgeMs,
        itemCount: posts.length,
      );
      ref
          .read(userRelationshipStateProvider.notifier)
          .setFollowing(subAccountId, seededFollowing);
    } catch (e) {
      final failure = CloudErrorMapper.runtimeFailureFromException(e);
      state = state.copyWith(isLoading: false, failure: failure);
      _recordProfileState(
        phase: state.profile == null ? 'blockingFailure' : 'cacheFallback',
        source: state.profile == null ? 'online' : 'retained',
        error: failure,
        copyKey: state.profile == null
            ? 'homepageLoadFailedTitle'
            : 'profileCacheFallback',
        hasCache: state.profile != null,
        itemCount: state.creations.length,
      );
    }
    // bundle 未提供关系能力（本人态 / 异常降级）时，异步精确校准（不阻塞首屏）。
    if (state.capability == null && !state.hasLoadError) {
      _loadRelationshipCapability();
    }
  }

  void _recordProfileState({
    required String phase,
    required String source,
    Object? error,
    String? copyKey,
    bool? hasCache,
    int? cacheAgeMs,
    int? itemCount,
  }) {
    ref
        .read(pageLifecycleObservabilityProvider)
        .recordPageState(
          pageName: 'profile',
          route: AppRoutePaths.userProfile(username: _userId),
          surface: 'user_profile',
          phase: phase,
          source: source,
          error: error,
          copyKey: copyKey,
          hasCache: hasCache,
          cacheAgeMs: cacheAgeMs,
          itemCount: itemCount,
        );
  }

  /// 登录态切换后重新读取当前 viewer→target 的 named capability。
  Future<void> refreshRelationshipCapability() => _loadRelationshipCapability();

  Future<void> _loadRelationshipCapability() async {
    try {
      final targetUserId = state.profile?.subAccountId.isNotEmpty == true
          ? state.profile!.subAccountId
          : _userId;
      final seededFollowing = ref
          .read(userRelationshipStateProvider)
          .isFollowing(targetUserId);
      final pendingFollowIntent = _pendingFollowIntent(targetUserId);
      final capRepo = ref.read(relationshipCapabilityRepositoryProvider);
      final cap = await capRepo.getCapability(targetUserId);
      if (!ref.mounted) {
        return;
      }
      final reconcileCap = ref
          .read(relationshipCapabilityRepositoryProvider)
          .reconcilesCapabilityWithSharedRelationshipState;
      final effectiveFollowing =
          pendingFollowIntent ??
          (reconcileCap ? seededFollowing : cap.viewerFollowsTarget);
      if (reconcileCap && effectiveFollowing != cap.viewerFollowsTarget) {
        state = state.copyWith(optimisticFollowOverride: effectiveFollowing);
      }
      final latestTargetId = state.profile?.subAccountId.isNotEmpty == true
          ? state.profile!.subAccountId
          : _userId;
      if (latestTargetId != targetUserId) {
        return;
      }
      ref
          .read(userRelationshipStateProvider.notifier)
          .setFollowing(targetUserId, effectiveFollowing);
      state = state.copyWith(
        capability: cap,
        isFollowing: effectiveFollowing,
        optimisticFollowOverride: effectiveFollowing == cap.viewerFollowsTarget
            ? null
            : effectiveFollowing,
        clearOptimisticFollowOverride:
            effectiveFollowing == cap.viewerFollowsTarget,
      );
    } catch (error) {
      if (!ref.mounted) {
        return;
      }
      final targetUserId = state.profile?.subAccountId.isNotEmpty == true
          ? state.profile!.subAccountId
          : _userId;
      final seededFollowing = ref
          .read(userRelationshipStateProvider)
          .isFollowing(targetUserId);
      state = state.copyWith(
        isFollowing: seededFollowing,
        optimisticFollowOverride: state.capability == null
            ? null
            : seededFollowing,
      );
      _recordProfileState(
        phase: 'capabilityFallback',
        source: 'relationshipState',
        error: error,
        copyKey: 'profileCapabilityFallback',
        hasCache: true,
        itemCount: state.creations.length,
      );
    }
  }

  void setSubTab(CreationSubTab tab) {
    state = state.copyWith(
      activeSubTab: tab,
      activeWorkFormat: CreationWorkFormat.all,
    );
  }

  void setWorkFormat(CreationWorkFormat format) {
    state = state.copyWith(activeWorkFormat: format);
  }

  void setVisibility(CreationVisibility v) {
    state = state.copyWith(activeVisibility: v);
  }

  void setInteractionSubTab(InteractionSubTab tab) {
    state = state.copyWith(interactionSubTab: tab);
  }

  void setInteractionDirection(InteractionDirection d) {
    state = state.copyWith(interactionDirection: d);
  }

  Future<void> toggleFollow() async {
    final subAccountId = state.profile?.subAccountId.isNotEmpty == true
        ? state.profile!.subAccountId
        : _userId;
    final relationshipState = ref.read(userRelationshipStateProvider);
    final wasFollowing = relationshipState.hasRelationshipStateFor(subAccountId)
        ? relationshipState.isFollowing(subAccountId)
        : state.isFollowing;
    final nextFollowing = !wasFollowing;
    await ref
        .read(userRelationshipStateProvider.notifier)
        .setFollowingWithSync(
          subAccountId,
          currentFollowing: wasFollowing,
          shouldFollow: nextFollowing,
          sourceSurface: AppUiSurfaces.userProfile,
          flushImmediately: false,
        );
    // R20/R21 · 关注/取关动作埋点（关系旅程漏斗；来源为他人主页）。
    unawaited(
      ref
          .read(journeyEventTrackerProvider)
          .trackAction(
            journey: 'relationship',
            action: nextFollowing ? 'follow_user' : 'unfollow_user',
            pageName: 'ProfilePage',
            targetType: 'user',
            targetKey: subAccountId,
          ),
    );
    state = state.copyWith(
      isFollowing: nextFollowing,
      optimisticFollowOverride: state.capability == null ? null : nextFollowing,
    );
  }

  Future<GreetingRequestDto> sendGreeting({
    String? requestMessage,
    String source = 'profile',
  }) async {
    final targetUserId = state.profile?.subAccountId.isNotEmpty == true
        ? state.profile!.subAccountId
        : _userId;
    final greeting = await ref
        .read(greetingRepositoryProvider)
        .sendGreeting(
          targetSubAccountId: targetUserId,
          requestMessage: requestMessage,
          source: source,
        );
    if (!ref.mounted) {
      return greeting;
    }
    // R20 · 打招呼发起埋点（破冰漏斗起点；回复侧在 replyGreeting 上报）。
    unawaited(
      ref
          .read(journeyEventTrackerProvider)
          .trackAction(
            journey: 'greeting',
            action: 'send_greeting',
            pageName: 'ProfilePage',
            targetType: 'user',
            targetKey: targetUserId,
          ),
    );
    final capability = state.capability;
    if (capability != null) {
      state = state.copyWith(
        capability: capability.copyWith(
          canGreet: false,
          hasPendingGreeting: true,
        ),
      );
    }
    return greeting;
  }

  Future<ChatConversationCreatedDto> openOrCreateDirectConversation() async {
    final targetUserId = state.profile?.subAccountId.isNotEmpty == true
        ? state.profile!.subAccountId
        : _userId;
    final result = await ref
        .read(chatConversationRepositoryProvider)
        .createConversation(
          type: 'direct',
          initialMemberIds: <String>[targetUserId],
        );
    if (ref.mounted) {
      _promoteFormalConversation(result.conversationId);
    }
    return result;
  }

  Future<GreetingReplyResultDto> replyGreetingIntoConversation(
    String requestId,
  ) async {
    final result = await ref
        .read(greetingRepositoryProvider)
        .replyGreeting(requestId);
    if (ref.mounted) {
      _promoteFormalConversation(result.conversationId);
    }
    return result;
  }

  void markFormalConversationAvailable({String? conversationId}) {
    _promoteFormalConversation(conversationId);
  }

  void _promoteFormalConversation(String? conversationId) {
    final capability = state.capability;
    if (capability == null) {
      return;
    }
    state = state.copyWith(
      capability: capability.copyWith(
        hasFormalConversation: true,
        hasPendingGreeting: false,
        canOpenConversation: true,
        canSendMessage: true,
        canGreet: false,
      ),
    );
  }
}

RelationshipCapabilityDto _copyCapabilityWithFollowState(
  RelationshipCapabilityDto capability,
  bool isFollowing,
) {
  return RelationshipCapabilityDto.fromFollowFlags(
    viewerId: capability.viewerSubAccountId,
    targetId: capability.targetSubAccountId,
    isFollowing: isFollowing,
    isFollowedBy: capability.targetFollowsViewer,
    isBlocked: capability.isBlocked,
    isBlockedBy: capability.isBlockedBy,
    hasFormalConversation: capability.hasFormalConversation,
    hasPendingGreeting: capability.hasPendingGreeting,
  );
}

final profileNotifierProvider =
    NotifierProvider.family<ProfileNotifier, ProfileState, String>(
      ProfileNotifier.new,
    );
