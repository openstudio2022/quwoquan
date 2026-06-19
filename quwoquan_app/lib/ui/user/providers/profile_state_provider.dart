import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_created_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/greeting_reply_result_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/user/greeting_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart'
    show SubAccountProfileViewData, UserHomepageBundleViewData, UserWorkItem;
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';

class ProfileState {
  const ProfileState({
    required this.userId,
    this.profile,
    this.activeSubTab = CreationSubTab.all,
    this.activeWorkFormat = CreationWorkFormat.all,
    this.activeVisibility = CreationVisibility.all,
    this.interactionSubTab = InteractionSubTab.all,
    this.interactionDirection = InteractionDirection.received,
    this.creations = const [],
    this.circles = const [],
    this.works = const [],
    this.isLoading = false,
    this.isFollowing = false,
    this.capability,
    this.optimisticFollowOverride,
    this.rawError,
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
  final List<UserWorkItem> works;
  final bool isLoading;
  final bool isFollowing;

  /// 关系能力位投影（null = 未载入）
  final RelationshipCapabilityDto? capability;
  final bool? optimisticFollowOverride;

  /// 首屏聚合失败的原始错误（null = 无错误）。UI 经 [errorMessage] 消费结构化文案，
  /// 不直接读异常字符串（对齐 runtime error cutover）。
  final Object? rawError;

  /// 结构化首屏错误文案（null = 无错误）。
  String? get errorMessage =>
      rawError == null ? null : runtimeErrorDisplayMessage(rawError!).trim();

  /// 首屏聚合是否失败（用于错误态分支：重试 / 降级提示）。
  bool get hasLoadError => rawError != null;

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
    List<UserWorkItem>? works,
    bool? isLoading,
    bool? isFollowing,
    RelationshipCapabilityDto? capability,
    bool? optimisticFollowOverride,
    Object? rawError,
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
      works: works ?? this.works,
      isLoading: isLoading ?? this.isLoading,
      isFollowing: isFollowing ?? this.isFollowing,
      capability: clearCapability ? null : (capability ?? this.capability),
      optimisticFollowOverride: clearOptimisticFollowOverride
          ? null
          : (optimisticFollowOverride ?? this.optimisticFollowOverride),
      rawError: clearError ? null : (rawError ?? this.rawError),
    );
  }
}

class ProfileNotifier extends Notifier<ProfileState> {
  ProfileNotifier(this._userId);

  final String _userId;

  @override
  ProfileState build() {
    Future.microtask(loadProfile);
    return ProfileState(userId: _userId);
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
    state = ProfileState(userId: _userId).copyWith(isLoading: true);
    try {
      final repo = ref.read(userProfileRepositoryProvider);
      // 锁定决策 #1：homepage-bundle 一次聚合身份域真相（profile/stats/关系能力/
      // viewerContext），与作品/帖子内容并发补充，消除首屏串行阻塞。
      final results = await Future.wait(<Future<Object>>[
        repo.getUserHomepageBundle(_userId),
        repo.listUserPosts(_userId),
        repo.listUserWorks(_userId),
      ]);
      final bundle = results[0] as UserHomepageBundleViewData;
      final posts = results[1] as List<PostBaseDto>;
      final works = results[2] as List<UserWorkItem>;
      final profile = bundle.profileWithStats;
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
      state = state.copyWith(
        profile: profile,
        creations: posts,
        works: works,
        isLoading: false,
        isFollowing: seededFollowing,
        capability: seededCapability,
        optimisticFollowOverride: optimisticFollowOverride,
        clearError: true,
      );
      ref
          .read(userRelationshipStateProvider.notifier)
          .setFollowing(subAccountId, seededFollowing);
    } catch (e) {
      // 结构化错误态：保留原始错误供 UI 经 errorMessage 展示，不静默吞异常。
      state = state.copyWith(isLoading: false, rawError: e);
    }
    // bundle 未提供关系能力（本人态 / 异常降级）时，异步精确校准（不阻塞首屏）。
    if (state.capability == null && !state.hasLoadError) {
      _loadRelationshipCapability();
    }
  }

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
    } catch (_) {
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
    final wasFollowing = state.isFollowing;
    final nextFollowing = !wasFollowing;
    ref
        .read(userRelationshipStateProvider.notifier)
        .setFollowing(subAccountId, nextFollowing);
    ref
        .read(discoveryStateProvider.notifier)
        .setFollowState(subAccountId, nextFollowing);
    ref
        .read(clientStateSyncOutboxProvider.notifier)
        .enqueueFollow(
          subAccountId: subAccountId,
          shouldFollow: nextFollowing,
          flushImmediately: true,
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
        .read(chatRepositoryProvider)
        .createConversation(
          type: 'direct',
          initialMemberIds: <String>[targetUserId],
        );
    _promoteFormalConversation(result.conversationId);
    return result;
  }

  Future<GreetingReplyResultDto> replyGreetingIntoConversation(
    String requestId,
  ) async {
    final result = await ref
        .read(greetingRepositoryProvider)
        .replyGreeting(requestId);
    _promoteFormalConversation(result.conversationId);
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
