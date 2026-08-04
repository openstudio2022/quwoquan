import 'dart:async';

import 'package:quwoquan_app/assistant/assistant/skill_data_control_request/application/skill_data_control_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:uuid/uuid.dart';

typedef SkillDataControlIntentFactory = String Function();
typedef SkillDataControlDelay = Future<void> Function(Duration duration);

enum SkillDataControlFlowPhase {
  idle,
  creating,
  pendingConfirmation,
  confirming,
  cancelling,
  executing,
  completed,
  cancelled,
  failed,
}

final class SkillDataControlFlowState {
  const SkillDataControlFlowState({
    this.phase = SkillDataControlFlowPhase.idle,
    this.request,
    this.error,
  });

  final SkillDataControlFlowPhase phase;
  final SkillDataControlRequest? request;
  final Object? error;

  bool get isBusy => switch (phase) {
    SkillDataControlFlowPhase.creating ||
    SkillDataControlFlowPhase.confirming ||
    SkillDataControlFlowPhase.cancelling => true,
    _ => false,
  };

  bool get canConfirm => switch (request?.status) {
    SkillDataControlRequestStatus.pendingConfirmation ||
    SkillDataControlRequestStatus.failed => !isBusy,
    _ => false,
  };
}

/// Skill 数据控制的端侧编排器。
///
/// 它只编排 canonical typed Facet，不拥有任何数据控制业务事实。创建结果未知时
/// 保留同一个 idempotency intent；确认冲突时读取同一个 request，再以最新 revision
/// 恢复。Executing 是真实后台状态，轮询到达边界后不会伪装为失败或完成。
final class SkillDataControlCoordinator {
  SkillDataControlCoordinator({
    required this._facet,
    SkillDataControlIntentFactory? intentFactory,
    SkillDataControlDelay? delay,
    this.maximumPollAttempts = 6,
    this.onStateChanged,
  }) : _intentFactory = intentFactory ?? const Uuid().v4,
       _delay = delay ?? ((duration) => Future<void>.delayed(duration));

  final AssistantSkillDataControlFacet _facet;
  final SkillDataControlIntentFactory _intentFactory;
  final SkillDataControlDelay _delay;
  final int maximumPollAttempts;
  final void Function(SkillDataControlFlowState state)? onStateChanged;

  SkillDataControlFlowState _state = const SkillDataControlFlowState();
  String? _createIntentId;
  String? _createSkillId;
  List<SkillDataControlAction> _createActions =
      const <SkillDataControlAction>[];
  String? _confirmationIntentId;
  String? _confirmationRequestId;
  int? _confirmationRevision;
  bool? _confirmationValue;

  SkillDataControlFlowState get state => _state;

  Future<SkillDataControlFlowState> create({
    required String skillId,
    required List<SkillDataControlAction> requestedActions,
  }) async {
    final normalizedSkillId = skillId.trim();
    final actions = requestedActions.toSet().toList(growable: false);
    if (normalizedSkillId.isEmpty || actions.isEmpty) {
      throw ArgumentError('skillId and requestedActions must not be empty');
    }
    _createIntentId = _intentFactory();
    _createSkillId = normalizedSkillId;
    _createActions = List<SkillDataControlAction>.unmodifiable(actions);
    return _performCreate();
  }

  /// 仅用于“创建结果未知”的显式重试；复用原 intent，禁止生成第二个请求。
  Future<SkillDataControlFlowState> retryCreate() {
    if (_createIntentId == null || _createSkillId == null) {
      throw StateError('there is no pending create intent');
    }
    return _performCreate();
  }

  Future<SkillDataControlFlowState> _performCreate() async {
    _emit(
      SkillDataControlFlowState(
        phase: SkillDataControlFlowPhase.creating,
        request: _state.request,
      ),
    );
    try {
      final receipt = await _facet.createSkillDataControlRequest(
        skillId: _createSkillId!,
        requestedActions: _createActions,
        clientRequestId: _createIntentId!,
      );
      return _accept(receipt.request);
    } catch (error) {
      _emit(
        SkillDataControlFlowState(
          phase: SkillDataControlFlowPhase.failed,
          request: _state.request,
          error: error,
        ),
      );
      rethrow;
    }
  }

  Future<SkillDataControlFlowState> confirm() => _confirm(confirmed: true);

  Future<SkillDataControlFlowState> cancelPending() =>
      _confirm(confirmed: false);

  Future<SkillDataControlFlowState> _confirm({
    required bool confirmed,
    bool reconcileOnce = true,
  }) async {
    final request = _state.request;
    if (request == null || !_state.canConfirm) {
      throw StateError('data control request is not confirmable');
    }
    _emit(
      SkillDataControlFlowState(
        phase: confirmed
            ? SkillDataControlFlowPhase.confirming
            : SkillDataControlFlowPhase.cancelling,
        request: request,
      ),
    );
    try {
      final receipt = await _facet.confirmSkillDataControlRequest(
        requestId: request.requestId,
        expectedRevision: request.revision,
        confirmed: confirmed,
        clientRequestId: _confirmationIntentFor(
          requestId: request.requestId,
          revision: request.revision,
          confirmed: confirmed,
        ),
      );
      final accepted = _accept(receipt.request);
      if (accepted.request?.status == SkillDataControlRequestStatus.executing) {
        return _pollUntilStable();
      }
      return accepted;
    } catch (error) {
      if (reconcileOnce) {
        final latest = await _tryGet(request.requestId);
        if (latest != null) {
          final reconciled = _accept(latest);
          if (latest.status == SkillDataControlRequestStatus.executing) {
            return _pollUntilStable();
          }
          if (latest.status == SkillDataControlRequestStatus.completed ||
              latest.status == SkillDataControlRequestStatus.cancelled) {
            return reconciled;
          }
          if (latest.status ==
                  SkillDataControlRequestStatus.pendingConfirmation ||
              latest.status == SkillDataControlRequestStatus.failed) {
            return _confirm(confirmed: confirmed, reconcileOnce: false);
          }
        }
      }
      _emit(
        SkillDataControlFlowState(
          phase: _phaseFor(request.status),
          request: request,
          error: error,
        ),
      );
      rethrow;
    }
  }

  /// 从 Activity 的 typed dataControlRequestId 恢复；不解析 sourceObjectRef。
  Future<SkillDataControlFlowState> resume(String requestId) async {
    final normalized = requestId.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(requestId, 'requestId', 'must not be blank');
    }
    final request = await _facet.getSkillDataControlRequest(
      requestId: normalized,
    );
    _accept(request);
    if (request.status == SkillDataControlRequestStatus.executing) {
      return _pollUntilStable();
    }
    return _state;
  }

  Future<SkillDataControlFlowState> refresh() async {
    final request = _state.request;
    if (request == null) {
      throw StateError('there is no data control request to refresh');
    }
    final latest = await _facet.getSkillDataControlRequest(
      requestId: request.requestId,
    );
    return _accept(latest);
  }

  Future<SkillDataControlFlowState> _pollUntilStable() async {
    final requestId = _state.request?.requestId;
    if (requestId == null || requestId.isEmpty) {
      throw StateError('executing request has no canonical requestId');
    }
    for (var attempt = 0; attempt < maximumPollAttempts; attempt++) {
      final exponent = attempt < 3 ? attempt : 3;
      final milliseconds = 250 * (1 << exponent);
      await _delay(Duration(milliseconds: milliseconds));
      final latest = await _facet.getSkillDataControlRequest(
        requestId: requestId,
      );
      _accept(latest);
      if (latest.status != SkillDataControlRequestStatus.executing) {
        return _state;
      }
    }
    // 后台仍在真实执行：保持 executing，允许用户关闭并从 Activity 恢复。
    return _state;
  }

  Future<SkillDataControlRequest?> _tryGet(String requestId) async {
    try {
      return await _facet.getSkillDataControlRequest(requestId: requestId);
    } on Object {
      return null;
    }
  }

  String _confirmationIntentFor({
    required String requestId,
    required int revision,
    required bool confirmed,
  }) {
    if (_confirmationRequestId == requestId &&
        _confirmationRevision == revision &&
        _confirmationValue == confirmed &&
        _confirmationIntentId != null) {
      return _confirmationIntentId!;
    }
    final next = _intentFactory();
    _confirmationRequestId = requestId;
    _confirmationRevision = revision;
    _confirmationValue = confirmed;
    _confirmationIntentId = next;
    return next;
  }

  SkillDataControlFlowState _accept(SkillDataControlRequest request) {
    final next = SkillDataControlFlowState(
      phase: _phaseFor(request.status),
      request: request,
    );
    _emit(next);
    return next;
  }

  SkillDataControlFlowPhase _phaseFor(SkillDataControlRequestStatus status) {
    return switch (status) {
      SkillDataControlRequestStatus.pendingConfirmation =>
        SkillDataControlFlowPhase.pendingConfirmation,
      SkillDataControlRequestStatus.executing =>
        SkillDataControlFlowPhase.executing,
      SkillDataControlRequestStatus.completed =>
        SkillDataControlFlowPhase.completed,
      SkillDataControlRequestStatus.cancelled =>
        SkillDataControlFlowPhase.cancelled,
      SkillDataControlRequestStatus.failed => SkillDataControlFlowPhase.failed,
    };
  }

  void _emit(SkillDataControlFlowState next) {
    _state = next;
    onStateChanged?.call(next);
  }
}
