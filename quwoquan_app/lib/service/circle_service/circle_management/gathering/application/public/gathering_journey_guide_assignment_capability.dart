enum GatheringJourneySupportRole {
  leader,
  assistant,
  licensedGuide,
  localExpert,
}

enum GatheringJourneySupportTaskKind {
  collection,
  briefing,
  routeGuidance,
  commentary,
  generalSupport,
}

enum GatheringJourneySupportStatus {
  assigned,
  accepted,
  inProgress,
  completed,
  cancelled,
}

final class GatheringJourneySupportAssignment {
  const GatheringJourneySupportAssignment({
    required this.assignmentId,
    required this.gatheringId,
    required this.planItemId,
    required this.assigneeParticipationRef,
    required this.role,
    required this.taskKind,
    required this.title,
    required this.status,
    required this.version,
    this.dueAt,
  });

  final String assignmentId;
  final String gatheringId;
  final String planItemId;
  final String assigneeParticipationRef;
  final GatheringJourneySupportRole role;
  final GatheringJourneySupportTaskKind taskKind;
  final String title;
  final GatheringJourneySupportStatus status;
  final int version;
  final DateTime? dueAt;
}

final class PutGatheringJourneySupportAssignmentInput {
  const PutGatheringJourneySupportAssignmentInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.planItemId,
    required this.assigneeParticipationRef,
    required this.role,
    required this.taskKind,
    required this.title,
    this.dueAt,
  });

  final String idempotencyKey;
  final String gatheringId;
  final String planItemId;
  final String assigneeParticipationRef;
  final GatheringJourneySupportRole role;
  final GatheringJourneySupportTaskKind taskKind;
  final String title;
  final DateTime? dueAt;
}

final class TransitionGatheringJourneySupportAssignmentInput {
  const TransitionGatheringJourneySupportAssignmentInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.assignmentId,
    required this.expectedVersion,
    required this.targetStatus,
  });

  final String idempotencyKey;
  final String gatheringId;
  final String assignmentId;
  final int expectedVersion;
  final GatheringJourneySupportStatus targetStatus;
}

abstract interface class GatheringJourneySupportAssignmentWriter {
  Future<GatheringJourneySupportAssignment> put(
    PutGatheringJourneySupportAssignmentInput input,
  );

  Future<GatheringJourneySupportAssignment> transition(
    TransitionGatheringJourneySupportAssignmentInput input,
  );
}

GatheringJourneySupportStatus? nextGatheringJourneySupportStatus(
  GatheringJourneySupportStatus current,
) => switch (current) {
  GatheringJourneySupportStatus.assigned =>
    GatheringJourneySupportStatus.accepted,
  GatheringJourneySupportStatus.accepted =>
    GatheringJourneySupportStatus.inProgress,
  GatheringJourneySupportStatus.inProgress =>
    GatheringJourneySupportStatus.completed,
  GatheringJourneySupportStatus.completed ||
  GatheringJourneySupportStatus.cancelled => null,
};
