import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/legacy.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/mock/user_profile_mock_data.dart';
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
  final List<ProfileCircleViewData> circles;
  final List<UserLifeItem> lifeItems;
  final List<UserWorkItem> works;
  final bool isLoading;
  final bool isFollowing;

  /// 关系能力位投影（null = 未载入）
  final RelationshipCapabilityDto? capability;

  ProfileState copyWith({
    ProfileSubjectViewData? profile,
    CreationSubTab? activeSubTab,
    CreationWorkFormat? activeWorkFormat,
    CreationVisibility? activeVisibility,
    InteractionSubTab? interactionSubTab,
    InteractionDirection? interactionDirection,
    LifestyleSubTab? lifestyleSubTab,
    List<PostBaseDto>? creations,
    List<ProfileCircleViewData>? circles,
    List<UserLifeItem>? lifeItems,
    List<UserWorkItem>? works,
    bool? isLoading,
    bool? isFollowing,
    RelationshipCapabilityDto? capability,
    bool clearCapability = false,
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
    );
  }
}

class ProfileNotifier extends ChangeNotifier {
  ProfileNotifier(this._ref, this._userId) {
    // Avoid notifying listeners during provider creation/build.
    Future<void>.microtask(loadProfile);
  }

  final Ref _ref;
  final String _userId;
  ProfileState _state = const ProfileState(userId: '');

  ProfileState get state => _state;

  Future<void> loadProfile() async {
    _state = ProfileState(userId: _userId).copyWith(isLoading: true);
    notifyListeners();
    try {
      final repo = _ref.read(userProfileRepositoryProvider);
      final profile = await repo.getProfileSubject(_userId);
      final posts = await repo.listUserPosts(_userId);
      final works = await repo.listUserWorks(_userId);
      final lifeItems = await repo.listUserLifeItems(_userId);
      final circles = await repo.listProfileCircles(_userId);
      final profileSubjectId = profile.profileSubjectId.isNotEmpty
          ? profile.profileSubjectId
          : _userId;
      final seededFollowing = _ref
          .read(userRelationshipStateProvider)
          .isFollowing(profileSubjectId);
      _state = _state.copyWith(
        profile: profile,
        creations: posts,
        works: works,
        lifeItems: lifeItems,
        circles: circles,
        isLoading: false,
        isFollowing: seededFollowing,
      );
    } catch (_) {
      _state = _state.copyWith(isLoading: false);
    }
    notifyListeners();
    // 异步加载关系能力位（不阻塞主内容展示）
    _loadRelationshipCapability();
  }

  Future<void> _loadRelationshipCapability() async {
    try {
      final targetUserId = _state.profile?.profileSubjectId.isNotEmpty == true
          ? _state.profile!.profileSubjectId
          : _userId;
      final seededFollowing = _ref
          .read(userRelationshipStateProvider)
          .isFollowing(targetUserId);
      final capRepo = _ref.read(relationshipCapabilityRepositoryProvider);
      var cap = await capRepo.getCapability(targetUserId);
      if (_ref.read(appDataSourceModeProvider) != AppDataSourceMode.remote &&
          seededFollowing &&
          !(cap.isFollowing || cap.isMutual)) {
        cap = _copyCapabilityWithFollowState(cap, true);
      }
      final latestTargetId = _state.profile?.profileSubjectId.isNotEmpty == true
          ? _state.profile!.profileSubjectId
          : _userId;
      if (latestTargetId != targetUserId) {
        return;
      }
      _ref
          .read(userRelationshipStateProvider.notifier)
          .setFollowing(targetUserId, cap.isFollowing || cap.isMutual);
      _state = _state.copyWith(
        capability: cap,
        isFollowing: cap.isFollowing || cap.isMutual,
      );
      notifyListeners();
    } catch (_) {
      // 加载失败时回退到旧版 isFollowing 显示
    }
  }

  void setSubTab(CreationSubTab tab) {
    _state = _state.copyWith(
      activeSubTab: tab,
      activeWorkFormat: CreationWorkFormat.all,
    );
    notifyListeners();
  }

  void setWorkFormat(CreationWorkFormat format) {
    _state = _state.copyWith(activeWorkFormat: format);
    notifyListeners();
  }

  void setVisibility(CreationVisibility v) {
    _state = _state.copyWith(activeVisibility: v);
    notifyListeners();
  }

  void setInteractionSubTab(InteractionSubTab tab) {
    _state = _state.copyWith(interactionSubTab: tab);
    notifyListeners();
  }

  void setInteractionDirection(InteractionDirection d) {
    _state = _state.copyWith(interactionDirection: d);
    notifyListeners();
  }

  void setLifestyleSubTab(LifestyleSubTab tab) {
    _state = _state.copyWith(lifestyleSubTab: tab);
    notifyListeners();
  }

  Future<void> toggleFollow() async {
    final profileSubjectId = _state.profile?.profileSubjectId.isNotEmpty == true
        ? _state.profile!.profileSubjectId
        : _userId;
    final wasFollowing = _state.isFollowing;
    final nextFollowing = !wasFollowing;
    _ref
        .read(userRelationshipStateProvider.notifier)
        .setFollowing(profileSubjectId, nextFollowing);
    _ref
        .read(clientStateSyncOutboxProvider.notifier)
        .enqueueFollow(
          profileSubjectId: profileSubjectId,
          shouldFollow: nextFollowing,
        );
    _state = _state.copyWith(
      isFollowing: nextFollowing,
      capability: _state.capability == null
          ? null
          : _copyCapabilityWithFollowState(_state.capability!, nextFollowing),
    );
    notifyListeners();
  }
}

RelationshipCapabilityDto _copyCapabilityWithFollowState(
  RelationshipCapabilityDto capability,
  bool isFollowing,
) {
  final relationState = isFollowing ? 'following' : 'not_following';
  return RelationshipCapabilityDto(
    viewerSubAccountId: capability.viewerSubAccountId,
    targetSubAccountId: capability.targetSubAccountId,
    relationState: relationState,
    canFollow: !isFollowing,
    canUnfollow: isFollowing,
    canMessage: capability.canMessage,
    canFollowBack: capability.canFollowBack && !isFollowing,
    canGreet: capability.canGreet,
    canOpenConversation: capability.canOpenConversation,
    canAddSameInterest: capability.canAddSameInterest,
    canSetCloseFriend: capability.canSetCloseFriend,
    canStartVoiceCall: capability.canStartVoiceCall,
    canStartVideoCall: capability.canStartVideoCall,
    isBlocked: capability.isBlocked,
    isBlockedBy: capability.isBlockedBy,
  );
}

final profileNotifierProvider =
    ChangeNotifierProvider.family<ProfileNotifier, String>(
      (ref, userId) => ProfileNotifier(ref, userId),
    );
