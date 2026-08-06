import 'dart:async';

import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/application/public/circle_group_membership_access.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

enum CircleGroupMembershipViewStatus {
  initial,
  loading,
  notJoined,
  pending,
  active,
  rejected,
  left,
  removed,
  failed,
}

enum CircleGroupMembershipRecoveryAction { load, apply, leave }

/// CircleGroupMembership 页面投影状态；不复制服务端 Slice，只保存展示所需状态。
final class CircleGroupMembershipViewState {
  const CircleGroupMembershipViewState({
    required this.status,
    this.role,
    this.version,
    this.isMutating = false,
    this.error,
    this.recoveryAction,
  });

  const CircleGroupMembershipViewState.initial()
    : this(status: CircleGroupMembershipViewStatus.initial);

  final CircleGroupMembershipViewStatus status;
  final CircleGroupMembershipRole? role;
  final int? version;
  final bool isMutating;
  final Object? error;
  final CircleGroupMembershipRecoveryAction? recoveryAction;

  bool get canApply =>
      !isMutating &&
      (status == CircleGroupMembershipViewStatus.notJoined ||
          status == CircleGroupMembershipViewStatus.rejected ||
          status == CircleGroupMembershipViewStatus.left ||
          status == CircleGroupMembershipViewStatus.removed);

  bool get canLeave =>
      !isMutating &&
      status == CircleGroupMembershipViewStatus.active &&
      role != CircleGroupMembershipRole.owner;

  static CircleGroupMembershipViewState fromSlice(
    CircleGroupMembershipSlice slice,
  ) => CircleGroupMembershipViewState(
    status: _statusFromWire(slice.state),
    role: slice.role,
    version: slice.version,
  );

  static CircleGroupMembershipViewState fromResult(
    CircleGroupMembershipCommandResult result,
  ) => CircleGroupMembershipViewState(
    status: _statusFromWire(result.state),
    role: result.role,
    version: result.version,
  );
}

CircleGroupMembershipViewStatus _statusFromWire(
  CircleGroupMembershipState state,
) => switch (state) {
  CircleGroupMembershipState.pending => CircleGroupMembershipViewStatus.pending,
  CircleGroupMembershipState.active => CircleGroupMembershipViewStatus.active,
  CircleGroupMembershipState.rejected =>
    CircleGroupMembershipViewStatus.rejected,
  CircleGroupMembershipState.left => CircleGroupMembershipViewStatus.left,
  CircleGroupMembershipState.removed => CircleGroupMembershipViewStatus.removed,
};

typedef CircleGroupMembershipStateListener =
    void Function(CircleGroupMembershipViewState state);

/// 固定 circle/group identity 的纯 application 状态机。
///
/// 所有请求共享一个 in-flight slot，保证重复点击或同时重试不会并发提交第二条
/// Apply/Leave command；dispose 后的迟到结果不会写回 presentation。
final class CircleGroupMembershipFlow {
  CircleGroupMembershipFlow({
    required this.circleId,
    required this.groupId,
    required this.access,
    required this.onStateChanged,
  });

  final String circleId;
  final String groupId;
  final CircleGroupMembershipAccess access;
  final CircleGroupMembershipStateListener onStateChanged;

  CircleGroupMembershipViewState state =
      const CircleGroupMembershipViewState.initial();
  Future<void>? _inFlight;
  bool _disposed = false;

  Future<void> load() => _run(_load);

  Future<void> apply() {
    if (!state.canApply) {
      return _inFlight ?? Future<void>.value();
    }
    return _run(_apply);
  }

  Future<void> leave() {
    if (!state.canLeave) {
      return _inFlight ?? Future<void>.value();
    }
    return _run(_leave);
  }

  Future<void> retry() => switch (state.recoveryAction) {
    CircleGroupMembershipRecoveryAction.apply => apply(),
    CircleGroupMembershipRecoveryAction.leave => leave(),
    CircleGroupMembershipRecoveryAction.load || null => load(),
  };

  void dispose() {
    _disposed = true;
  }

  Future<void> _run(Future<void> Function() operation) {
    final current = _inFlight;
    if (current != null) {
      return current;
    }
    final future = operation();
    _inFlight = future;
    return future.whenComplete(() {
      if (identical(_inFlight, future)) {
        _inFlight = null;
      }
    });
  }

  Future<void> _load() async {
    _emit(
      const CircleGroupMembershipViewState(
        status: CircleGroupMembershipViewStatus.loading,
      ),
    );
    try {
      final membership = await access.findMy(
        MyCircleGroupMembershipQuery(circleId: circleId, groupId: groupId),
      );
      if (_disposed) return;
      _emit(
        membership == null
            ? const CircleGroupMembershipViewState(
                status: CircleGroupMembershipViewStatus.notJoined,
              )
            : CircleGroupMembershipViewState.fromSlice(membership),
      );
    } catch (error) {
      if (_disposed) return;
      _emit(
        CircleGroupMembershipViewState(
          status: CircleGroupMembershipViewStatus.failed,
          error: error,
          recoveryAction: CircleGroupMembershipRecoveryAction.load,
        ),
      );
    }
  }

  Future<void> _apply() async {
    final previous = state;
    _emit(
      CircleGroupMembershipViewState(
        status: previous.status,
        role: previous.role,
        version: previous.version,
        isMutating: true,
      ),
    );
    try {
      final result = await access.apply(
        ApplyCircleGroupMembershipCommand(circleId: circleId, groupId: groupId),
      );
      if (_disposed) return;
      _emit(CircleGroupMembershipViewState.fromResult(result));
    } catch (error) {
      if (_disposed) return;
      _emit(
        CircleGroupMembershipViewState(
          status: previous.status,
          role: previous.role,
          version: previous.version,
          error: error,
          recoveryAction: CircleGroupMembershipRecoveryAction.apply,
        ),
      );
    }
  }

  Future<void> _leave() async {
    final previous = state;
    _emit(
      CircleGroupMembershipViewState(
        status: previous.status,
        role: previous.role,
        version: previous.version,
        isMutating: true,
      ),
    );
    try {
      final result = await access.leave(
        LeaveCircleGroupMembershipCommand(circleId: circleId, groupId: groupId),
      );
      if (_disposed) return;
      _emit(CircleGroupMembershipViewState.fromResult(result));
    } catch (error) {
      if (_disposed) return;
      _emit(
        CircleGroupMembershipViewState(
          status: previous.status,
          role: previous.role,
          version: previous.version,
          error: error,
          recoveryAction: CircleGroupMembershipRecoveryAction.leave,
        ),
      );
    }
  }

  void _emit(CircleGroupMembershipViewState next) {
    if (_disposed) return;
    state = next;
    onStateChanged(next);
  }
}
