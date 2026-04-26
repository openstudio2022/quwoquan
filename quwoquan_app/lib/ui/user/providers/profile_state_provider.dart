import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart'
    show ProfileSubjectViewData, UserLifeItem, UserWorkItem;
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
    this.interactionSubTab = InteractionSubTab.likes,
    this.interactionDirection = InteractionDirection.received,
    this.lifestyleSubTab = LifestyleSubTab.footprint,
    this.creations = const [],
    this.circles = const [],
    this.lifeItems = const [],
    this.works = const [],
    this.isLoading = false,
    this.isFollowing = false,
    this.capability,
    this.optimisticFollowOverride,
  });

  final String userId;
  final ProfileSubjectViewData? profile;
  final CreationSubTab activeSubTab;
  final CreationWorkFormat activeWorkFormat;
  final CreationVisibility activeVisibility;
  final InteractionSubTab interactionSubTab;
  final InteractionDirection interactionDirection;
  final LifestyleSubTab lifestyleSubTab;
  final List<PostBaseDto> creations;
  final List<CircleDto> circles;
  final List<UserLifeItem> lifeItems;
  final List<UserWorkItem> works;
  final bool isLoading;
  final bool isFollowing;

  /// 关系能力位投影（null = 未载入）
  final RelationshipCapabilityDto? capability;
  final bool? optimisticFollowOverride;

  RelationshipCapabilityDto? get displayCapability {
    final base = capability;
    final override = optimisticFollowOverride;
    if (base == null || override == null) {
      return base;
    }
    return _copyCapabilityWithFollowState(base, override);
  }

  ProfileState copyWith({
    ProfileSubjectViewData? profile,
    CreationSubTab? activeSubTab,
    CreationWorkFormat? activeWorkFormat,
    CreationVisibility? activeVisibility,
    InteractionSubTab? interactionSubTab,
    InteractionDirection? interactionDirection,
    LifestyleSubTab? lifestyleSubTab,
    List<PostBaseDto>? creations,
    List<CircleDto>? circles,
    List<UserLifeItem>? lifeItems,
    List<UserWorkItem>? works,
    bool? isLoading,
    bool? isFollowing,
    RelationshipCapabilityDto? capability,
    bool? optimisticFollowOverride,
    bool clearCapability = false,
    bool clearOptimisticFollowOverride = false,
  }) {
    return ProfileState(
      userId: userId,
      profile: profile ?? this.profile,
      activeSubTab: activeSubTab ?? this.activeSubTab,
      activeWorkFormat: activeWorkFormat ?? this.activeWorkFormat,
      activeVisibility: activeVisibility ?? this.activeVisibility,
      interactionSubTab: interactionSubTab ?? this.interactionSubTab,
      interactionDirection: interactionDirection ?? this.interactionDirection,
      lifestyleSubTab: lifestyleSubTab ?? this.lifestyleSubTab,
      creations: creations ?? this.creations,
      circles: circles ?? this.circles,
      lifeItems: lifeItems ?? this.lifeItems,
      works: works ?? this.works,
      isLoading: isLoading ?? this.isLoading,
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

  @override
  ProfileState build() {
    Future.microtask(loadProfile);
    return ProfileState(userId: _userId);
  }

  Future<void> loadProfile() async {
    state = ProfileState(userId: _userId).copyWith(isLoading: true);
    try {
      final repo = ref.read(userProfileRepositoryProvider);
      final profile = await repo.getProfileSubject(_userId);
      final posts = await repo.listUserPosts(_userId);
      final works = await repo.listUserWorks(_userId);
      final lifeItems = await repo.listUserLifeItems(_userId);
      final circles = await repo.listProfileCircles(_userId);
      final profileSubjectId = profile.profileSubjectId.isNotEmpty
          ? profile.profileSubjectId
          : _userId;
      final reconcileCap = ref
          .read(relationshipCapabilityRepositoryProvider)
          .reconcilesCapabilityWithSharedRelationshipState;
      RelationshipCapabilityDto? seededCapability;
      bool? optimisticFollowOverride;
      final sharedFollowing = ref
          .read(userRelationshipStateProvider)
          .isFollowing(profileSubjectId);
      if (reconcileCap) {
        try {
          seededCapability = await ref
              .read(relationshipCapabilityRepositoryProvider)
              .getCapability(profileSubjectId);
          if (sharedFollowing != seededCapability.viewerFollowsTarget) {
            optimisticFollowOverride = sharedFollowing;
          }
        } catch (_) {
          seededCapability = null;
        }
      }
      final seededFollowing =
          optimisticFollowOverride ??
          seededCapability?.viewerFollowsTarget ??
          sharedFollowing;
      state = state.copyWith(
        profile: profile,
        creations: posts,
        works: works,
        lifeItems: lifeItems,
        circles: circles,
        isLoading: false,
        isFollowing: seededFollowing,
        capability: seededCapability,
        optimisticFollowOverride: optimisticFollowOverride,
      );
      ref
          .read(userRelationshipStateProvider.notifier)
          .setFollowing(profileSubjectId, seededFollowing);
    } catch (_) {
      state = state.copyWith(isLoading: false);
    }
    // 异步加载关系能力位（不阻塞主内容展示）
    if (state.capability == null) {
      _loadRelationshipCapability();
    }
  }

  Future<void> _loadRelationshipCapability() async {
    try {
      final targetUserId = state.profile?.profileSubjectId.isNotEmpty == true
          ? state.profile!.profileSubjectId
          : _userId;
      final seededFollowing = ref
          .read(userRelationshipStateProvider)
          .isFollowing(targetUserId);
      final capRepo = ref.read(relationshipCapabilityRepositoryProvider);
      var cap = await capRepo.getCapability(targetUserId);
      if (ref
              .read(relationshipCapabilityRepositoryProvider)
              .reconcilesCapabilityWithSharedRelationshipState &&
          seededFollowing &&
          !cap.viewerFollowsTarget) {
        state = state.copyWith(optimisticFollowOverride: true);
      }
      final latestTargetId = state.profile?.profileSubjectId.isNotEmpty == true
          ? state.profile!.profileSubjectId
          : _userId;
      if (latestTargetId != targetUserId) {
        return;
      }
      ref
          .read(userRelationshipStateProvider.notifier)
          .setFollowing(targetUserId, cap.viewerFollowsTarget);
      state = state.copyWith(
        capability: cap,
        isFollowing: cap.viewerFollowsTarget,
        clearOptimisticFollowOverride: true,
      );
    } catch (_) {
      final targetUserId = state.profile?.profileSubjectId.isNotEmpty == true
          ? state.profile!.profileSubjectId
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

  void setLifestyleSubTab(LifestyleSubTab tab) {
    state = state.copyWith(lifestyleSubTab: tab);
  }

  Future<void> toggleFollow() async {
    final profileSubjectId = state.profile?.profileSubjectId.isNotEmpty == true
        ? state.profile!.profileSubjectId
        : _userId;
    final wasFollowing = state.isFollowing;
    final nextFollowing = !wasFollowing;
    ref
        .read(userRelationshipStateProvider.notifier)
        .setFollowing(profileSubjectId, nextFollowing);
    ref
        .read(clientStateSyncOutboxProvider.notifier)
        .enqueueFollow(
          profileSubjectId: profileSubjectId,
          shouldFollow: nextFollowing,
        );
    state = state.copyWith(
      isFollowing: nextFollowing,
      optimisticFollowOverride: state.capability == null ? null : nextFollowing,
    );
  }
}

RelationshipCapabilityDto _copyCapabilityWithFollowState(
  RelationshipCapabilityDto capability,
  bool isFollowing,
) {
  final next = RelationshipCapabilityDto.fromFollowFlags(
    viewerId: capability.viewerSubAccountId,
    targetId: capability.targetSubAccountId,
    isFollowing: isFollowing,
    isFollowedBy: capability.targetFollowsViewer,
    closeFriend: capability.isCloseFriend,
  );
  return RelationshipCapabilityDto(
    viewerSubAccountId: capability.viewerSubAccountId,
    targetSubAccountId: capability.targetSubAccountId,
    relationState: next.relationState,
    relationTier: next.relationTier,
    canFollow: next.canFollow,
    canUnfollow: next.canUnfollow,
    canMessage: next.canMessage,
    canFollowBack: next.canFollowBack,
    canGreet: next.canGreet,
    canOpenConversation: next.canOpenConversation,
    canAddSameInterest: next.canAddSameInterest,
    canSetCloseFriend: next.canSetCloseFriend,
    canStartVoiceCall: next.canStartVoiceCall,
    canStartVideoCall: next.canStartVideoCall,
    isBlocked: capability.isBlocked,
    isBlockedBy: capability.isBlockedBy,
  );
}

final profileNotifierProvider =
    NotifierProvider.family<ProfileNotifier, ProfileState, String>(
      ProfileNotifier.new,
    );
