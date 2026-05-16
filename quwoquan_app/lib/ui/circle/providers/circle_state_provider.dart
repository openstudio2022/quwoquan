import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/circle/models/circle_stats_view_data.dart';
import 'package:quwoquan_app/ui/circle/models/circle_tab.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart';

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
    this.role = CircleRole.visitor,
    this.joinStatus = 'none',
    this.isFollowed = false,
    this.activeTabType = 'works',
    this.activeSubTab = CreationSubTab.all,
    this.activeWorkFormat = CreationWorkFormat.all,
    this.sortMode = CreationSortMode.latest,
    this.viewMode = CreationViewMode.grid,
    this.isLoading = false,
    this.error,
    this.circleStats = CircleStatsViewData.empty,
  });

  final String circleId;
  final CircleDto? circleData;
  final CircleRole role;
  final String joinStatus;
  final bool isFollowed;
  final String activeTabType;
  final CreationSubTab activeSubTab;
  final CreationWorkFormat activeWorkFormat;
  final CreationSortMode sortMode;
  final CreationViewMode viewMode;
  final bool isLoading;
  final String? error;
  final CircleStatsViewData circleStats;

  CircleState copyWith({
    CircleDto? circleData,
    CircleRole? role,
    String? joinStatus,
    bool? isFollowed,
    String? activeTabType,
    CreationSubTab? activeSubTab,
    CreationWorkFormat? activeWorkFormat,
    CreationSortMode? sortMode,
    CreationViewMode? viewMode,
    bool? isLoading,
    String? error,
    CircleStatsViewData? circleStats,
  }) {
    return CircleState(
      circleId: circleId,
      circleData: circleData ?? this.circleData,
      role: role ?? this.role,
      joinStatus: joinStatus ?? this.joinStatus,
      isFollowed: isFollowed ?? this.isFollowed,
      activeTabType: activeTabType ?? this.activeTabType,
      activeSubTab: activeSubTab ?? this.activeSubTab,
      activeWorkFormat: activeWorkFormat ?? this.activeWorkFormat,
      sortMode: sortMode ?? this.sortMode,
      viewMode: viewMode ?? this.viewMode,
      isLoading: isLoading ?? this.isLoading,
      error: error,
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
      state = state.copyWith(
        circleData: dto,
        role: _circleRoleFromRaw(detail.viewerRole),
        joinStatus: detail.joinStatusIfPresent ?? state.joinStatus,
        isFollowed: detail.isFollowedIfPresent ?? state.isFollowed,
        circleStats: CircleStatsViewData.fromStatsWire(
          statsWire,
          circleFallback: dto,
        ),
        isLoading: false,
      );
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: runtimeErrorDisplayMessage(e),
      );
    }
  }

  void setActiveTab(String type) {
    state = state.copyWith(activeTabType: type);
  }

  void setSubTab(CreationSubTab tab) {
    state = state.copyWith(
      activeSubTab: tab,
      activeWorkFormat: tab == CreationSubTab.work
          ? state.activeWorkFormat
          : CreationWorkFormat.all,
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
        error: null,
      );
      return true;
    } catch (e) {
      state = state.copyWith(error: runtimeErrorDisplayMessage(e));
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
