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
}
