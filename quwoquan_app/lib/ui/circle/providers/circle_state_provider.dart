import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/circle/models/circle_stats_view_data.dart';
import 'package:quwoquan_app/ui/circle/models/circle_tab.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';

/// 圈子内用户角色
enum CircleRole { owner, admin, member, visitor }

CircleRole _circleRoleFromRaw(dynamic value) {
  return switch ((value ?? '').toString().trim().toLowerCase()) {
    'owner' => CircleRole.owner,
    'admin' => CircleRole.admin,
    'member' => CircleRole.member,
    _ => CircleRole.visitor,
  };
}

class CircleState {
  const CircleState({
    required this.circleId,
    this.circleData,
    this.defaultPublicGroup,
    this.role = CircleRole.visitor,
    this.joinStatus = 'none',
    this.isFollowed = false,
    this.activeTabType = 'works',
    this.activeSubTab = CreationSubTab.all,
    this.activeWorkFormat = CreationWorkFormat.all,
    this.sortMode = CreationSortMode.latest,
    this.viewMode = CreationViewMode.grid,
    this.isLoading = false,
    this.loadError,
    this.circleStats = CircleStatsViewData.empty,
  });

  final String circleId;
  final CircleDto? circleData;
  final CircleGroupDto? defaultPublicGroup;
  final CircleRole role;
  final String joinStatus;
  final bool isFollowed;
  final String activeTabType;
  final CreationSubTab activeSubTab;
  final CreationWorkFormat activeWorkFormat;
  final CreationSortMode sortMode;
  final CreationViewMode viewMode;
  final bool isLoading;
  final Object? loadError;
  final CircleStatsViewData circleStats;

  CircleState copyWith({
    CircleDto? circleData,
    CircleGroupDto? defaultPublicGroup,
    CircleRole? role,
    String? joinStatus,
    bool? isFollowed,
    String? activeTabType,
    CreationSubTab? activeSubTab,
    CreationWorkFormat? activeWorkFormat,
    CreationSortMode? sortMode,
    CreationViewMode? viewMode,
    bool? isLoading,
    Object? loadError,
    bool clearLoadError = false,
    CircleStatsViewData? circleStats,
  }) {
    return CircleState(
      circleId: circleId,
      circleData: circleData ?? this.circleData,
      defaultPublicGroup: defaultPublicGroup ?? this.defaultPublicGroup,
      role: role ?? this.role,
      joinStatus: joinStatus ?? this.joinStatus,
      isFollowed: isFollowed ?? this.isFollowed,
      activeTabType: activeTabType ?? this.activeTabType,
      activeSubTab: activeSubTab ?? this.activeSubTab,
      activeWorkFormat: activeWorkFormat ?? this.activeWorkFormat,
      sortMode: sortMode ?? this.sortMode,
      viewMode: viewMode ?? this.viewMode,
      isLoading: isLoading ?? this.isLoading,
      loadError: clearLoadError ? null : (loadError ?? this.loadError),
      circleStats: circleStats ?? this.circleStats,
    );
  }
}

class CircleStateNotifier extends Notifier<CircleState> {
  CircleStateNotifier(this._circleId);

  final String _circleId;

  @override
  CircleState build() {
    Future.microtask(loadCircle);
    return CircleState(circleId: _circleId).copyWith(isLoading: true);
  }

  Future<void> loadCircle() async {
    state = CircleState(circleId: _circleId).copyWith(isLoading: true);
    try {
      final repo = ref.read(circleRepositoryProvider);
      final detail = await repo.getCircle(_circleId);
      final statsWire = await repo.getCircleStats(_circleId);
      final dto = detail.circle;
      CircleGroupDto? defaultGroup;
      final defaultGroupId = dto.defaultPublicGroupId?.trim() ?? '';
      if (defaultGroupId.isNotEmpty) {
        try {
          defaultGroup = await repo.getCircleGroup(_circleId, defaultGroupId);
        } catch (_) {
          defaultGroup = null;
        }
      }
      state = state.copyWith(
        circleData: dto,
        defaultPublicGroup: defaultGroup,
        role: _circleRoleFromRaw(detail.viewerRole),
        joinStatus: detail.joinStatusIfPresent ?? state.joinStatus,
        isFollowed: detail.isFollowedIfPresent ?? state.isFollowed,
        circleStats: CircleStatsViewData.fromStatsWire(
          statsWire,
          circleFallback: dto,
        ),
        isLoading: false,
        clearLoadError: true,
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, loadError: e);
    }
  }

  void setActiveTab(String type) {
    state = state.copyWith(activeTabType: type);
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

  void setSortMode(CreationSortMode mode) {
    state = state.copyWith(sortMode: mode);
  }

  void setViewMode(CreationViewMode mode) {
    state = state.copyWith(viewMode: mode);
  }

  Future<void> joinCircle() async {
    final previousStatus = state.joinStatus;
    final previousFollowed = state.isFollowed;
    final nextJoinStatus = state.circleData?.joinPolicy == 'approval'
        ? 'pending'
        : 'joined';
    state = state.copyWith(joinStatus: nextJoinStatus, isFollowed: true);
    try {
      final activeContext = await ref.read(activePersonaContextProvider.future);
      final repo = ref.read(circleRepositoryProvider);
      await repo.joinCircle(
        _circleId,
        ownerUserId: activeContext.ownerUserId,
        subAccountId: activeContext.subAccountId,
        subAccountContextVersion: activeContext.contextVersion,
      );
    } catch (_) {
      state = state.copyWith(
        joinStatus: previousStatus,
        isFollowed: previousFollowed,
      );
    }
  }

  Future<void> leaveCircle() async {
    final previousStatus = state.joinStatus;
    final previousFollowed = state.isFollowed;
    state = state.copyWith(joinStatus: 'none', isFollowed: false);
    try {
      final activeContext = await ref.read(activePersonaContextProvider.future);
      final repo = ref.read(circleRepositoryProvider);
      await repo.leaveCircle(
        _circleId,
        ownerUserId: activeContext.ownerUserId,
        subAccountId: activeContext.subAccountId,
        subAccountContextVersion: activeContext.contextVersion,
      );
    } catch (_) {
      state = state.copyWith(
        joinStatus: previousStatus,
        isFollowed: previousFollowed,
      );
    }
  }

  Future<void> toggleFollow() async {
    final wasFollowed = state.isFollowed;
    state = state.copyWith(isFollowed: !wasFollowed);
    try {
      final activeContext = await ref.read(activePersonaContextProvider.future);
      final repo = ref.read(circleRepositoryProvider);
      if (wasFollowed) {
        await repo.leaveCircle(
          _circleId,
          ownerUserId: activeContext.ownerUserId,
          subAccountId: activeContext.subAccountId,
          subAccountContextVersion: activeContext.contextVersion,
        );
      } else {
        await repo.joinCircle(
          _circleId,
          ownerUserId: activeContext.ownerUserId,
          subAccountId: activeContext.subAccountId,
          subAccountContextVersion: activeContext.contextVersion,
        );
      }
    } catch (_) {
      state = state.copyWith(isFollowed: wasFollowed);
    }
  }

  Future<bool> updateCircleDetails(CircleUpdateWireDto wire) async {
    try {
      final repo = ref.read(circleRepositoryProvider);
      final patch = wire.toMap();
      final updated = await repo.updateCircle(_circleId, wire);
      final merged = <String, dynamic>{
        ...?state.circleData?.toMap(),
        ...updated.toMap(),
        ...patch,
      };
      state = state.copyWith(
        circleData: CircleDto.fromMap(merged),
        role: _circleRoleFromRaw(merged['role']),
        joinStatus: (merged['joinStatus'] ?? state.joinStatus).toString(),
        isFollowed: merged['isFollowed'] as bool? ?? state.isFollowed,
        clearLoadError: true,
      );
      return true;
    } catch (e) {
      state = state.copyWith(loadError: e);
      return false;
    }
  }
}

final circleStateProvider =
    NotifierProvider.family<CircleStateNotifier, CircleState, String>(
      CircleStateNotifier.new,
    );

class CircleDirectoryRefreshNotifier extends Notifier<int> {
  @override
  int build() => 0;

  void bump() => state++;
}

final circleDirectoryRefreshProvider =
    NotifierProvider<CircleDirectoryRefreshNotifier, int>(
      CircleDirectoryRefreshNotifier.new,
    );
