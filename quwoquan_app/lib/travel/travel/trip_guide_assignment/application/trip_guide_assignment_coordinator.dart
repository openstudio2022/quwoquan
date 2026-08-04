import 'package:quwoquan_app/travel/travel/trip_timeline_view/application/trip_journey_query.dart';
import 'package:quwoquan_app/travel/travel/trip_guide_assignment/application/trip_guide_assignment_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class TripGuidePutIntent {
  const TripGuidePutIntent({
    required this.command,
    required this.idempotencyKey,
  });

  final PutTripGuideAssignmentRequest command;
  final String idempotencyKey;
}

final class TripGuideTransitionIntent {
  const TripGuideTransitionIntent({
    required this.command,
    required this.idempotencyKey,
  });

  final TransitionTripGuideAssignmentRequest command;
  final String idempotencyKey;
}

final class TripGuideAssignmentCoordinator {
  const TripGuideAssignmentCoordinator({
    required this.facet,
    required this.idempotencyKeyFactory,
    this.taskKeyFactory,
  });

  final TripGuideAssignmentFacet facet;
  final String Function() idempotencyKeyFactory;
  final String Function()? taskKeyFactory;

  TripGuidePutIntent prepareCreate({
    required TripJourneySnapshot snapshot,
    required String actorPersonaId,
    required String assigneePersonaId,
    required TripGuideRole role,
    required TripGuideTaskKind taskKind,
    required String title,
    DateTime? dueAt,
  }) {
    if (!snapshot.usesOneCurrentRevision) {
      throw StateError('Trip projections do not use one current revision');
    }
    final normalizedActor = actorPersonaId.trim();
    final normalizedAssignee = assigneePersonaId.trim();
    final normalizedTitle = title.trim();
    if (normalizedActor.isEmpty ||
        normalizedActor != snapshot.plan.organizerPersonaId ||
        normalizedAssignee.isEmpty ||
        normalizedTitle.isEmpty) {
      throw ArgumentError('Guide assignment create input is invalid');
    }
    final taskKey = taskKeyFactory?.call().trim() ?? '';
    if (taskKey.isEmpty) {
      throw StateError('GuideAssignment task key must not be blank');
    }
    return _putIntent(
      tripId: snapshot.plan.tripId,
      expectedVersion: 0,
      taskKey: taskKey,
      assigneePersonaId: normalizedAssignee,
      role: role,
      taskKind: taskKind,
      title: normalizedTitle,
      dueAt: dueAt,
      sourceRevisionNumber: snapshot.plan.currentRevisionNumber,
      attributionKind: _attributionKind(taskKind),
      attributionPersonaId: taskKind == TripGuideTaskKind.commentary
          ? normalizedAssignee
          : normalizedActor,
      publicQualificationPersonaId: role == TripGuideRole.licensedGuide
          ? normalizedAssignee
          : null,
    );
  }

  TripGuidePutIntent prepareReassign({
    required TripJourneySnapshot snapshot,
    required String actorPersonaId,
    required TripGuideAssignment assignment,
    required String assigneePersonaId,
  }) {
    if (!snapshot.usesOneCurrentRevision ||
        assignment.tripId != snapshot.plan.tripId ||
        actorPersonaId.trim() != snapshot.plan.organizerPersonaId ||
        assigneePersonaId.trim().isEmpty) {
      throw ArgumentError('Guide assignment reassign input is invalid');
    }
    return _putIntent(
      tripId: assignment.tripId,
      expectedVersion: assignment.version,
      taskKey: assignment.taskKey,
      assigneePersonaId: assigneePersonaId.trim(),
      role: assignment.role,
      taskKind: assignment.taskKind,
      title: assignment.title,
      dueAt: assignment.dueAt,
      sourceRevisionNumber: snapshot.plan.currentRevisionNumber,
      attributionKind: assignment.attributionKind,
      attributionPersonaId:
          assignment.attributionKind ==
              TripGuideAttributionKind.professionalCommentary
          ? assigneePersonaId.trim()
          : assignment.attributionPersonaId,
      publicQualificationPersonaId:
          assignment.role == TripGuideRole.licensedGuide
          ? assigneePersonaId.trim()
          : null,
    );
  }

  TripGuidePutIntent _putIntent({
    required String tripId,
    required int expectedVersion,
    required String taskKey,
    required String assigneePersonaId,
    required TripGuideRole role,
    required TripGuideTaskKind taskKind,
    required String title,
    required DateTime? dueAt,
    required int sourceRevisionNumber,
    required TripGuideAttributionKind attributionKind,
    required String attributionPersonaId,
    required String? publicQualificationPersonaId,
  }) {
    final idempotencyKey = idempotencyKeyFactory().trim();
    if (idempotencyKey.isEmpty) {
      throw StateError('GuideAssignment idempotency key must not be blank');
    }
    return TripGuidePutIntent(
      command: PutTripGuideAssignmentRequest(
        tripId: tripId,
        expectedVersion: expectedVersion,
        taskKey: taskKey,
        assigneePersonaId: assigneePersonaId,
        role: role,
        taskKind: taskKind,
        title: title,
        dueAt: dueAt,
        sourceRevisionNumber: sourceRevisionNumber,
        attributionKind: attributionKind,
        attributionPersonaId: attributionPersonaId,
        publicQualificationPersonaId: publicQualificationPersonaId,
      ),
      idempotencyKey: idempotencyKey,
    );
  }

  Future<TripGuideAssignment> put(TripGuidePutIntent intent) {
    return facet.put(intent.command, idempotencyKey: intent.idempotencyKey);
  }

  TripGuideTransitionIntent? prepareNext(TripGuideAssignment assignment) {
    final targetStatus = nextTripGuideAssignmentStatus(assignment.status);
    if (targetStatus == null) {
      return null;
    }
    final idempotencyKey = idempotencyKeyFactory().trim();
    if (idempotencyKey.isEmpty) {
      throw StateError('GuideAssignment idempotency key must not be blank');
    }
    return TripGuideTransitionIntent(
      command: TransitionTripGuideAssignmentRequest(
        tripId: assignment.tripId,
        taskKey: assignment.taskKey,
        expectedVersion: assignment.version,
        targetStatus: targetStatus,
      ),
      idempotencyKey: idempotencyKey,
    );
  }

  Future<TripGuideAssignment> transition(TripGuideTransitionIntent intent) {
    return facet.transition(
      intent.command,
      idempotencyKey: intent.idempotencyKey,
    );
  }
}

TripGuideAssignmentStatus? nextTripGuideAssignmentStatus(
  TripGuideAssignmentStatus current,
) => switch (current) {
  TripGuideAssignmentStatus.assigned => TripGuideAssignmentStatus.accepted,
  TripGuideAssignmentStatus.accepted => TripGuideAssignmentStatus.inProgress,
  TripGuideAssignmentStatus.inProgress => TripGuideAssignmentStatus.completed,
  TripGuideAssignmentStatus.completed ||
  TripGuideAssignmentStatus.cancelled => null,
};

TripGuideAttributionKind _attributionKind(TripGuideTaskKind taskKind) {
  return switch (taskKind) {
    TripGuideTaskKind.collection ||
    TripGuideTaskKind.briefing => TripGuideAttributionKind.administrative,
    TripGuideTaskKind.commentary =>
      TripGuideAttributionKind.professionalCommentary,
    TripGuideTaskKind.routeGuidance ||
    TripGuideTaskKind.generalSupport => TripGuideAttributionKind.generalFact,
  };
}
