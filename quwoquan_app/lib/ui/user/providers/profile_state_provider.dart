import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/legacy.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/user/mock/user_profile_mock_data.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';

class ProfileState {
  const ProfileState({
    required this.userId,
    this.activeSubTab = CreationSubTab.all,
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
    this.stats = const {},
  });

  final String userId;
  final CreationSubTab activeSubTab;
  final CreationVisibility activeVisibility;
  final InteractionSubTab interactionSubTab;
  final InteractionDirection interactionDirection;
  final LifestyleSubTab lifestyleSubTab;
  final List<PostBaseDto> creations;
  final List<Map<String, dynamic>> circles;
  final List<UserLifeItem> lifeItems;
  final List<UserWorkItem> works;
  final bool isLoading;
  final bool isFollowing;
  final Map<String, dynamic> stats;

  ProfileState copyWith({
    CreationSubTab? activeSubTab,
    CreationVisibility? activeVisibility,
    InteractionSubTab? interactionSubTab,
    InteractionDirection? interactionDirection,
    LifestyleSubTab? lifestyleSubTab,
    List<PostBaseDto>? creations,
    List<Map<String, dynamic>>? circles,
    List<UserLifeItem>? lifeItems,
    List<UserWorkItem>? works,
    bool? isLoading,
    bool? isFollowing,
    Map<String, dynamic>? stats,
  }) {
    return ProfileState(
      userId: userId,
      activeSubTab: activeSubTab ?? this.activeSubTab,
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
      stats: stats ?? this.stats,
    );
  }
}

class ProfileNotifier extends ChangeNotifier {
  ProfileNotifier(this._ref, this._userId) {
    loadProfile();
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
      final posts = await repo.listUserPosts(_userId);
      final works = await repo.listUserWorks(_userId);
      final lifeItems = await repo.listUserLifeItems(_userId);
      final circles = await repo.listUserCircles(_userId);
      final stats = await repo.getUserStats(_userId);
      _state = _state.copyWith(
        creations: posts,
        works: works,
        lifeItems: lifeItems,
        circles: circles,
        stats: stats,
        isLoading: false,
      );
    } catch (_) {
      _state = _state.copyWith(isLoading: false);
    }
    notifyListeners();
  }

  void setSubTab(CreationSubTab tab) {
    _state = _state.copyWith(activeSubTab: tab);
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
    final wasFollowing = _state.isFollowing;
    _state = _state.copyWith(isFollowing: !wasFollowing);
    notifyListeners();
    try {
      final repo = _ref.read(userProfileRepositoryProvider);
      if (wasFollowing) {
        await repo.unfollowUser(_userId);
      } else {
        await repo.followUser(_userId);
      }
    } catch (_) {
      _state = _state.copyWith(isFollowing: wasFollowing);
      notifyListeners();
    }
  }
}

final profileNotifierProvider =
    ChangeNotifierProvider.family<ProfileNotifier, String>(
  (ref, userId) => ProfileNotifier(ref, userId),
);
