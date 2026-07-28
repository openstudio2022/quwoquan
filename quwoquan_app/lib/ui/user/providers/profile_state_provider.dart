import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_created_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/greeting_reply_result_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/user/greeting_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart'
    show SubAccountProfileViewData;
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/app_request_wait_controller.dart';
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
    this.isIdentityLoading = false,
    this.isIdentitySlow = false,
    this.identityFailure,
    this.isWorksLoading = false,
    this.isWorksSlow = false,
    this.worksFailure,
    this.isFollowing = false,
    this.capability,
    this.optimisticFollowOverride,
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
  final bool isIdentityLoading;
  final bool isIdentitySlow;
  final RuntimeFailureBase? identityFailure;
  final bool isWorksLoading;
  final bool isWorksSlow;
  final RuntimeFailureBase? worksFailure;
  final bool isFollowing;

  /// 关系能力位投影（null = 未载入）
  final RelationshipCapabilityDto? capability;
  final bool? optimisticFollowOverride;

  bool get isLoading => isIdentityLoading || isWorksLoading;

  /// 兼容只读取一个错误的旧消费方；新页面必须分别消费身份与作品状态。
  RuntimeFailureBase? get failure => identityFailure ?? worksFailure;

  /// 结构化首屏错误文案（null = 无错误）。
  String? get errorMessage =>
      failure == null ? null : runtimeFailureDisplayMessage(failure!).trim();

  /// 首屏聚合是否失败（用于错误态分支：重试 / 降级提示）。
  bool get hasLoadError => identityFailure != null || worksFailure != null;

  bool get hasCacheFallback => hasLoadError && profile != null;

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
    bool? isIdentityLoading,
    bool? isIdentitySlow,
    RuntimeFailureBase? identityFailure,
    bool? isWorksLoading,
    bool? isWorksSlow,
    RuntimeFailureBase? worksFailure,
    bool? isFollowing,
    RelationshipCapabilityDto? capability,
    bool? optimisticFollowOverride,
    bool clearCapability = false,
    bool clearOptimisticFollowOverride = false,
    bool clearIdentityFailure = false,
    bool clearWorksFailure = false,
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
      isIdentityLoading: isIdentityLoading ?? this.isIdentityLoading,
      isIdentitySlow: isIdentitySlow ?? this.isIdentitySlow,
      identityFailure: clearIdentityFailure
          ? null
          : (identityFailure ?? this.identityFailure),
      isWorksLoading: isWorksLoading ?? this.isWorksLoading,
      isWorksSlow: isWorksSlow ?? this.isWorksSlow,
      worksFailure: clearWorksFailure
          ? null
          : (worksFailure ?? this.worksFailure),
      isFollowing: isFollowing ?? this.isFollowing,
      capability: clearCapability ? null : (capability ?? this.capability),
      optimisticFollowOverride: clearOptimisticFollowOverride
          ? null
          : (optimisticFollowOverride ?? this.optimisticFollowOverride),
    );
  }
}

class ProfileNotifier extends Notifier<ProfileState> {
  ProfileNotifier(this._userId);

  final String _userId;
  AppRequestWaitController _identityWaitController = AppRequestWaitController();
  AppRequestWaitController _worksWaitController = AppRequestWaitController();
  Completer<void>? _identityGenerationDone;
  Completer<void>? _worksGenerationDone;

  @override
  ProfileState build() {
    if (_identityWaitController.isDisposed) {
      _identityWaitController = AppRequestWaitController();
    }
    if (_worksWaitController.isDisposed) {
      _worksWaitController = AppRequestWaitController();
    }
    ref.onDispose(() {
      _finishIdentityGeneration(_identityGenerationDone);
      _finishWorksGeneration(_worksGenerationDone);
      _identityWaitController.dispose();
      _worksWaitController.dispose();
    });
    ref.listen<UserRelationshipState>(userRelationshipStateProvider, (
      previous,
      next,
    ) {
      _syncFollowStateFromShared(next);
    });
    Future.microtask(() {
      if (!ref.mounted ||
          _identityWaitController.isDisposed ||
          _worksWaitController.isDisposed) {
        return;
      }
      unawaited(loadProfile());
    });
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
    if (!ref.mounted ||
        _identityWaitController.isDisposed ||
        _worksWaitController.isDisposed) {
      return;
    }
    state = state.copyWith(
      isIdentityLoading: true,
      isIdentitySlow: false,
      isWorksLoading: true,
      isWorksSlow: false,
      clearIdentityFailure: true,
      clearWorksFailure: true,
    );
    _recordProfileState(
      phase: 'onlineLoading',
      source: 'online',
      hasCache: state.profile != null,
      itemCount: state.creations.length,
    );
    final identityDone = _nextIdentityGeneration();
    final identityGeneration = _identityWaitController.start(
      mode: AppRequestWaitMode.foreground,
      onSlow: (generation) {
        if (!ref.mounted || generation != _identityWaitController.generation) {
          return;
        }
        state = state.copyWith(isIdentitySlow: true);
      },
      onTimeout: (generation) {
        _finishIdentityGeneration(identityDone);
        if (!ref.mounted || generation != _identityWaitController.generation) {
          return;
        }
        state = state.copyWith(
          isIdentityLoading: false,
          isIdentitySlow: false,
          identityFailure: _profileTimeoutFailure('identity'),
        );
      },
    );
    final worksDone = _nextWorksGeneration();
    final worksGeneration = _worksWaitController.start(
      mode: AppRequestWaitMode.foreground,
      onSlow: (generation) {
        if (!ref.mounted || generation != _worksWaitController.generation) {
          return;
        }
        state = state.copyWith(isWorksSlow: true);
      },
      onTimeout: (generation) {
        _finishWorksGeneration(worksDone);
        if (!ref.mounted || generation != _worksWaitController.generation) {
          return;
        }
        state = state.copyWith(
          isWorksLoading: false,
          isWorksSlow: false,
          worksFailure: _profileTimeoutFailure('works'),
        );
      },
    );
    unawaited(
      _loadIdentity(
        identityGeneration,
      ).whenComplete(() => _finishIdentityGeneration(identityDone)),
    );
    unawaited(
      _loadWorks(
        worksGeneration,
      ).whenComplete(() => _finishWorksGeneration(worksDone)),
    );
    await Future.wait<void>(<Future<void>>[
      identityDone.future,
      worksDone.future,
    ]);
    if (!ref.mounted) return;
    // bundle 未提供关系能力（本人态 / 异常降级）时，异步精确校准（不阻塞首屏）。
    if (state.capability == null && state.identityFailure == null) {
      unawaited(_loadRelationshipCapability());
    }
  }

  Future<void> reloadIdentity() async {
    state = state.copyWith(
      isIdentityLoading: true,
      isIdentitySlow: false,
      clearIdentityFailure: true,
    );
    final done = _nextIdentityGeneration();
    final generation = _identityWaitController.start(
      mode: AppRequestWaitMode.foreground,
      onSlow: (current) {
        if (ref.mounted && current == _identityWaitController.generation) {
          state = state.copyWith(isIdentitySlow: true);
        }
      },
      onTimeout: (current) {
        _finishIdentityGeneration(done);
        if (!ref.mounted || current != _identityWaitController.generation) {
          return;
        }
        state = state.copyWith(
          isIdentityLoading: false,
          isIdentitySlow: false,
          identityFailure: _profileTimeoutFailure('identity'),
        );
      },
    );
    unawaited(
      _loadIdentity(
        generation,
      ).whenComplete(() => _finishIdentityGeneration(done)),
    );
    await done.future;
  }

  Future<void> reloadWorks() async {
    state = state.copyWith(
      isWorksLoading: true,
      isWorksSlow: false,
      clearWorksFailure: true,
    );
    final done = _nextWorksGeneration();
    final generation = _worksWaitController.start(
      mode: AppRequestWaitMode.foreground,
      onSlow: (current) {
        if (ref.mounted && current == _worksWaitController.generation) {
          state = state.copyWith(isWorksSlow: true);
        }
      },
      onTimeout: (current) {
        _finishWorksGeneration(done);
        if (!ref.mounted || current != _worksWaitController.generation) {
          return;
        }
        state = state.copyWith(
          isWorksLoading: false,
          isWorksSlow: false,
          worksFailure: _profileTimeoutFailure('works'),
        );
      },
    );
    unawaited(
      _loadWorks(generation).whenComplete(() => _finishWorksGeneration(done)),
    );
    await done.future;
  }

  Completer<void> _nextIdentityGeneration() {
    _finishIdentityGeneration(_identityGenerationDone);
    final next = Completer<void>();
    _identityGenerationDone = next;
    return next;
  }

  Completer<void> _nextWorksGeneration() {
    _finishWorksGeneration(_worksGenerationDone);
    final next = Completer<void>();
    _worksGenerationDone = next;
    return next;
  }

  void _finishIdentityGeneration(Completer<void>? generation) {
    if (generation == null) return;
    if (!generation.isCompleted) generation.complete();
    if (identical(_identityGenerationDone, generation)) {
      _identityGenerationDone = null;
    }
  }

  void _finishWorksGeneration(Completer<void>? generation) {
    if (generation == null) return;
    if (!generation.isCompleted) generation.complete();
    if (identical(_worksGenerationDone, generation)) {
      _worksGenerationDone = null;
    }
  }

  Future<void> _loadIdentity(int generation) async {
    try {
      final bundle = await ref
          .read(profileQueryProvider(AppUiSurfaces.userProfile))
          .getUserHomepageBundle(_userId);
      if (!_identityWaitController.complete(generation) || !ref.mounted) return;
      final profile = bundle.profileWithStats;
      final subAccountId = profile.subAccountId.isNotEmpty
          ? profile.subAccountId
          : _userId;
      final bundleCapability = bundle.relationshipCapability;
      final reconcileCap = ref
          .read(relationshipCapabilityRepositoryProvider)
          .reconcilesCapabilityWithSharedRelationshipState;
      final sharedFollowing = ref
          .read(userRelationshipStateProvider)
          .isFollowing(subAccountId);
      final pendingFollowIntent = _pendingFollowIntent(subAccountId);
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
          bundleCapability?.viewerFollowsTarget ??
          sharedFollowing;
      state = state.copyWith(
        profile: profile,
        isIdentityLoading: false,
        isIdentitySlow: false,
        isFollowing: seededFollowing,
        capability: bundleCapability,
        optimisticFollowOverride: optimisticFollowOverride,
        clearIdentityFailure: true,
      );
      ref
          .read(userRelationshipStateProvider.notifier)
          .setFollowing(subAccountId, seededFollowing);
    } catch (error) {
      if (!_identityWaitController.complete(generation) || !ref.mounted) return;
      final failure = CloudErrorMapper.runtimeFailureFromException(error);
      state = state.copyWith(
        isIdentityLoading: false,
        isIdentitySlow: false,
        identityFailure: failure,
      );
      _recordProfileState(
        phase: state.profile == null ? 'blockingFailure' : 'cacheFallback',
        source: state.profile == null ? 'online' : 'retained',
        error: failure,
        copyKey: 'recovery.reloadLater',
        hasCache: state.profile != null,
        itemCount: state.creations.length,
      );
    }
  }

  Future<void> _loadWorks(int generation) async {
    try {
      final postsPage = await ref
          .read(userProfileContentAuthorPostsReaderProvider)
          .listUserPosts(userId: _userId);
      if (!_worksWaitController.complete(generation) || !ref.mounted) return;
      final posts = postsPage.items;
      ref
          .read(postInteractionStateProvider.notifier)
          .applyConfirmedPosts(posts);
      final fallbackError = postsPage.cacheFallbackError;
      final fallbackFailure = fallbackError == null
          ? null
          : CloudErrorMapper.runtimeFailureFromException(fallbackError);
      state = state.copyWith(
        creations: posts,
        isWorksLoading: false,
        isWorksSlow: false,
        worksFailure: fallbackFailure,
        clearWorksFailure: fallbackError == null,
      );
      _recordProfileState(
        phase: fallbackError == null ? 'onlineSuccess' : 'cacheFallback',
        source: fallbackError == null ? 'online' : 'cache',
        error: fallbackError,
        copyKey: fallbackError == null ? null : 'recovery.reloadLater',
        hasCache: fallbackError != null,
        cacheAgeMs: postsPage.cacheAgeMs,
        itemCount: posts.length,
      );
    } catch (error) {
      if (!_worksWaitController.complete(generation) || !ref.mounted) return;
      final failure = CloudErrorMapper.runtimeFailureFromException(error);
      state = state.copyWith(
        isWorksLoading: false,
        isWorksSlow: false,
        worksFailure: failure,
      );
      _recordProfileState(
        phase: state.creations.isEmpty ? 'sectionFailure' : 'cacheFallback',
        source: state.creations.isEmpty ? 'online' : 'retained',
        error: failure,
        copyKey: 'recovery.reloadLater',
        hasCache: state.creations.isNotEmpty,
        itemCount: state.creations.length,
      );
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

RuntimeFailure _profileTimeoutFailure(String area) {
  return RuntimeFailure(
    code: RuntimeFailureCodes.appTimeoutRequestTimeout,
    semanticReason: 'profile_${area}_deadline_exceeded',
    origin: RuntimeFailureOrigin.localClient,
    kind: RuntimeFailureKind.timeout,
    nature: RuntimeFailureNature.transient,
    location: const RuntimeFailureLocation(
      businessObject: 'user.profile',
      functionModule: 'profile_load',
    ),
    context: RuntimeFailureContext(
      attributes: <RuntimeContextAttribute>[
        RuntimeContextAttribute(key: 'area', value: area),
      ],
    ),
    recovery: const RuntimeRecoveryDirective(action: 'retry'),
  );
}

final profileNotifierProvider =
    NotifierProvider.family<ProfileNotifier, ProfileState, String>(
      ProfileNotifier.new,
    );
