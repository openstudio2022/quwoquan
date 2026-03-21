import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/legacy.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
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
    this.stats = const {},
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
  final Map<String, dynamic> stats;

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
    Map<String, dynamic>? stats,
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
      stats: stats ?? this.stats,
    );
  }
}

class CircleStateNotifier extends ChangeNotifier {
  CircleStateNotifier(this._ref, this._circleId) {
    loadCircle();
  }

  final Ref _ref;
  final String _circleId;
  CircleState _state = const CircleState(circleId: '');

  CircleState get state => _state;

  Future<void> loadCircle() async {
    _state = CircleState(circleId: _circleId).copyWith(isLoading: true);
    notifyListeners();
    try {
      final repo = _ref.read(circleRepositoryProvider);
      final data = await repo.getCircle(_circleId);
      final stats = await repo.getCircleStats(_circleId);
      _state = _state.copyWith(
        circleData: CircleDto.fromMap(data),
        role: _circleRoleFromRaw(data['role']),
        joinStatus: (data['joinStatus'] ?? _state.joinStatus).toString(),
        isFollowed: data['isFollowed'] as bool? ?? _state.isFollowed,
        stats: stats,
        isLoading: false,
      );
    } catch (e) {
      _state = _state.copyWith(isLoading: false, error: e.toString());
    }
    notifyListeners();
  }

  void setActiveTab(String type) {
    _state = _state.copyWith(activeTabType: type);
    notifyListeners();
  }

  void setSubTab(CreationSubTab tab) {
    _state = _state.copyWith(
      activeSubTab: tab,
      activeWorkFormat: tab == CreationSubTab.work
          ? _state.activeWorkFormat
          : CreationWorkFormat.all,
    );
    notifyListeners();
  }

  void setWorkFormat(CreationWorkFormat format) {
    _state = _state.copyWith(activeWorkFormat: format);
    notifyListeners();
  }

  void setSortMode(CreationSortMode mode) {
    _state = _state.copyWith(sortMode: mode);
    notifyListeners();
  }

  void setViewMode(CreationViewMode mode) {
    _state = _state.copyWith(viewMode: mode);
    notifyListeners();
  }

  Future<void> joinCircle() async {
    final previousStatus = _state.joinStatus;
    final previousFollowed = _state.isFollowed;
    _state = _state.copyWith(joinStatus: 'joined', isFollowed: true);
    notifyListeners();
    try {
      final repo = _ref.read(circleRepositoryProvider);
      await repo.joinCircle(_circleId);
    } catch (_) {
      _state = _state.copyWith(
        joinStatus: previousStatus,
        isFollowed: previousFollowed,
      );
      notifyListeners();
    }
  }

  Future<void> leaveCircle() async {
    final previousStatus = _state.joinStatus;
    final previousFollowed = _state.isFollowed;
    _state = _state.copyWith(joinStatus: 'none', isFollowed: false);
    notifyListeners();
    try {
      final repo = _ref.read(circleRepositoryProvider);
      await repo.leaveCircle(_circleId);
    } catch (_) {
      _state = _state.copyWith(
        joinStatus: previousStatus,
        isFollowed: previousFollowed,
      );
      notifyListeners();
    }
  }

  Future<void> toggleFollow() async {
    final wasFollowed = _state.isFollowed;
    _state = _state.copyWith(isFollowed: !wasFollowed);
    notifyListeners();
    try {
      final repo = _ref.read(circleRepositoryProvider);
      if (wasFollowed) {
        await repo.leaveCircle(_circleId);
      } else {
        await repo.joinCircle(_circleId);
      }
    } catch (_) {
      _state = _state.copyWith(isFollowed: wasFollowed);
      notifyListeners();
    }
  }

  Future<bool> updateCircleDetails(Map<String, dynamic> data) async {
    try {
      final repo = _ref.read(circleRepositoryProvider);
      final updated = await repo.updateCircle(_circleId, data);
      final merged = {
        ...?_state.circleData?.toMap(),
        ...updated,
      };
      _state = _state.copyWith(
        circleData: CircleDto.fromMap(merged),
        role: _circleRoleFromRaw(updated['role'] ?? merged['role']),
        joinStatus: (updated['joinStatus'] ?? merged['joinStatus'] ?? _state.joinStatus)
            .toString(),
        isFollowed: updated['isFollowed'] as bool? ??
            merged['isFollowed'] as bool? ??
            _state.isFollowed,
        error: null,
      );
      notifyListeners();
      return true;
    } catch (e) {
      _state = _state.copyWith(error: e.toString());
      notifyListeners();
      return false;
    }
  }
}

final circleStateProvider =
    ChangeNotifierProvider.family<CircleStateNotifier, String>(
      (ref, circleId) => CircleStateNotifier(ref, circleId),
    );
