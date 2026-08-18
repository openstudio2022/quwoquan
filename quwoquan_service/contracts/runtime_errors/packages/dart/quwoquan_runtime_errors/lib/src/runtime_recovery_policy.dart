import 'package:quwoquan_runtime_errors/src/runtime_failure.dart';

enum RuntimeRecoveryAction {
  absorb,
  retry,
  fallback,
  surface,
  escalate,
  compensate,
}

enum UserDisruptionLevel {
  silent,
  passiveIndicator,
  snackbar,
  inlineCard,
  permissionCard,
}

class EntryContext {
  const EntryContext({
    required this.kind,
    required this.entryId,
    required this.actorType,
    required this.actorId,
    required this.surfaceId,
    this.sessionId = '',
  });

  final String kind;
  final String entryId;
  final String actorType;
  final String actorId;
  final String surfaceId;
  final String sessionId;
}

class BoundaryContext {
  const BoundaryContext({
    required this.boundary,
    this.stage = '',
    this.remainingBudget = 0,
  });

  final String boundary;
  final String stage;
  final int remainingBudget;
}

class RuntimeRecoveryDecision {
  const RuntimeRecoveryDecision({
    required this.action,
    required this.disruptionLevel,
    required this.policyId,
  });

  final RuntimeRecoveryAction action;
  final UserDisruptionLevel disruptionLevel;
  final String policyId;
}

abstract interface class RuntimeRecoveryPolicy {
  RuntimeRecoveryDecision decide(
    RuntimeFailureBase failure,
    EntryContext entryContext,
    BoundaryContext boundaryContext,
  );
}

class DefaultRuntimeRecoveryPolicy implements RuntimeRecoveryPolicy {
  const DefaultRuntimeRecoveryPolicy();

  @override
  RuntimeRecoveryDecision decide(
    RuntimeFailureBase failure,
    EntryContext entryContext,
    BoundaryContext boundaryContext,
  ) {
    // 唯一真相源：优先消费云侧随响应下发的 recovery 指令（来自 errors.yaml）。
    final directive = failure.recovery;
    if (directive.isPresent) {
      final action = _actionFromName(directive.action);
      if (action != null) {
        return RuntimeRecoveryDecision(
          action: action,
          disruptionLevel:
              _levelFromName(directive.disruptionLevel) ??
              _defaultLevelForAction(action),
          policyId: 'downlink.recovery',
        );
      }
    }
    // 防御边界：云侧契约缺失（未下发 recovery）时按 nature 派生，门禁保证云侧必然下发。
    if (failure.nature == RuntimeFailureNature.transient &&
        boundaryContext.remainingBudget > 0) {
      return const RuntimeRecoveryDecision(
        action: RuntimeRecoveryAction.retry,
        disruptionLevel: UserDisruptionLevel.silent,
        policyId: 'default.transient.retry',
      );
    }
    if (failure.nature == RuntimeFailureNature.requiresPermission) {
      return const RuntimeRecoveryDecision(
        action: RuntimeRecoveryAction.surface,
        disruptionLevel: UserDisruptionLevel.permissionCard,
        policyId: 'default.permission.surface',
      );
    }
    return const RuntimeRecoveryDecision(
      action: RuntimeRecoveryAction.surface,
      disruptionLevel: UserDisruptionLevel.inlineCard,
      policyId: 'default.surface',
    );
  }

  RuntimeRecoveryAction? _actionFromName(String raw) {
    for (final value in RuntimeRecoveryAction.values) {
      if (value.name == raw) return value;
    }
    return null;
  }

  UserDisruptionLevel? _levelFromName(String raw) {
    for (final value in UserDisruptionLevel.values) {
      if (value.name == raw) return value;
    }
    return null;
  }

  UserDisruptionLevel _defaultLevelForAction(RuntimeRecoveryAction action) {
    switch (action) {
      case RuntimeRecoveryAction.absorb:
        return UserDisruptionLevel.silent;
      case RuntimeRecoveryAction.retry:
        return UserDisruptionLevel.snackbar;
      case RuntimeRecoveryAction.surface:
      case RuntimeRecoveryAction.fallback:
      case RuntimeRecoveryAction.escalate:
      case RuntimeRecoveryAction.compensate:
        return UserDisruptionLevel.inlineCard;
    }
  }
}
