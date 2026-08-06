enum GatheringHostSubjectKind { persona, entityHomepage, circle }

enum GatheringPlaceMode { physical, online, hybrid }

enum GatheringAudiencePolicy { public, unlisted, communityMembers, inviteOnly }

enum GatheringAdmissionPolicy { open, approval, inviteOnly }

enum GatheringTimeDisclosure { exact, dateOnly, afterJoin }

enum GatheringPlaceDisclosure { exact, coarse, afterJoin }

enum GatheringRosterDisclosure { countOnly, joinedMembers, publicOptIn }

enum GatheringLifecycleStatus { draft, published, cancelled, completed }

enum GatheringRoomBindingStatus { pending, ready, failed }

enum GatheringTemporalPhase { upcoming, inProgress, ended }

enum GatheringAdmissionState { accepting, full, paused, closed }

enum GatheringParticipationState {
  invitedPending,
  applicationPending,
  active,
  closed,
}

enum GatheringAdmissionSource { open, application, invitation }

enum GatheringOutcomeStatus {
  occurred,
  didNotHappen,
  endedEarly,
  safetyTerminated,
  disputed,
  unverified,
}

enum GatheringApplicationDecision { approve, reject }

enum GatheringAdmissionControlAction { pause, resume }

final class GatheringCanonicalObjectRef {
  const GatheringCanonicalObjectRef({
    required this.objectTypeRef,
    required this.objectId,
  });

  final String objectTypeRef;
  final String objectId;
}

final class GatheringSourceRef {
  const GatheringSourceRef({
    required this.objectRef,
    required this.routeId,
    required this.sourceDigest,
  });

  final GatheringCanonicalObjectRef objectRef;
  final String routeId;
  final String sourceDigest;
}

final class GatheringHostInput {
  const GatheringHostInput({
    required this.subjectKind,
    required this.subjectId,
    required this.authorityEvidenceRef,
    required this.authorityVersion,
  });

  final GatheringHostSubjectKind subjectKind;
  final String subjectId;
  final String authorityEvidenceRef;
  final int authorityVersion;
}

final class GatheringPurposeDraft {
  const GatheringPurposeDraft({
    required this.title,
    required this.summary,
    this.sourceRefs = const <GatheringSourceRef>[],
    this.topicRefs = const <String>[],
    this.requirementRefs = const <String>[],
  });

  final String title;
  final String summary;
  final List<GatheringSourceRef> sourceRefs;
  final List<String> topicRefs;
  final List<String> requirementRefs;
}

final class GatheringScheduleDraft {
  const GatheringScheduleDraft({
    required this.timezone,
    required this.startAt,
    required this.endAt,
    this.admissionClosesAt,
  });

  final String timezone;
  final DateTime startAt;
  final DateTime endAt;
  final DateTime? admissionClosesAt;
}

final class GatheringPlaceDraft {
  const GatheringPlaceDraft({
    required this.mode,
    required this.coarsePlaceLabel,
    required this.exactMeetingPoint,
    required this.onlineLocationRef,
    this.coarsePlaceRef,
  });

  final GatheringPlaceMode mode;
  final GatheringCanonicalObjectRef? coarsePlaceRef;
  final String coarsePlaceLabel;
  final String exactMeetingPoint;
  final String onlineLocationRef;
}

final class GatheringDisclosurePolicyDraft {
  const GatheringDisclosurePolicyDraft({
    required this.time,
    required this.place,
    required this.roster,
  });

  final GatheringTimeDisclosure time;
  final GatheringPlaceDisclosure place;
  final GatheringRosterDisclosure roster;
}

final class GatheringPolicyDraft {
  const GatheringPolicyDraft({
    required this.audience,
    required this.admission,
    required this.maxParticipants,
    required this.disclosure,
    required this.riskControlPolicyRef,
  });

  final GatheringAudiencePolicy audience;
  final GatheringAdmissionPolicy admission;
  final int maxParticipants;
  final GatheringDisclosurePolicyDraft disclosure;
  final String riskControlPolicyRef;
}

final class GatheringCreateDraftInput {
  const GatheringCreateDraftInput({
    required this.idempotencyKey,
    required this.host,
    required this.creatorParticipates,
    required this.purpose,
    required this.schedule,
    required this.place,
    required this.policy,
  });

  final String idempotencyKey;
  final GatheringHostInput host;
  final bool creatorParticipates;
  final GatheringPurposeDraft purpose;
  final GatheringScheduleDraft schedule;
  final GatheringPlaceDraft place;
  final GatheringPolicyDraft policy;
}

final class GatheringUpdateInput {
  const GatheringUpdateInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.expectedGatheringVersion,
    required this.host,
    required this.purpose,
    required this.schedule,
    required this.place,
    required this.policy,
    this.acknowledgementDeadlineAt,
  });

  final String idempotencyKey;
  final String gatheringId;
  final int expectedGatheringVersion;
  final GatheringHostInput host;
  final GatheringPurposeDraft purpose;
  final GatheringScheduleDraft schedule;
  final GatheringPlaceDraft place;
  final GatheringPolicyDraft policy;
  final DateTime? acknowledgementDeadlineAt;
}

final class GatheringVersionCommandInput {
  const GatheringVersionCommandInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.expectedGatheringVersion,
  });

  final String idempotencyKey;
  final String gatheringId;
  final int expectedGatheringVersion;
}

final class GatheringParticipationCommandInput {
  const GatheringParticipationCommandInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.expectedGatheringVersion,
    required this.expectedParticipationVersion,
  });

  final String idempotencyKey;
  final String gatheringId;
  final int expectedGatheringVersion;
  final int expectedParticipationVersion;
}

final class GatheringApplyInput {
  const GatheringApplyInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.expectedGatheringVersion,
    required this.expectedParticipationVersion,
    this.answers = const <GatheringApplicationAnswerInput>[],
  });

  final String idempotencyKey;
  final String gatheringId;
  final int expectedGatheringVersion;
  final int expectedParticipationVersion;
  final List<GatheringApplicationAnswerInput> answers;
}

final class GatheringApplicationAnswerInput {
  const GatheringApplicationAnswerInput({
    required this.questionId,
    required this.answerText,
    this.selectedOptionIds = const <String>[],
  });

  final String questionId;
  final String answerText;
  final List<String> selectedOptionIds;
}

final class GatheringReviewApplicationInput {
  const GatheringReviewApplicationInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.participantPersonaId,
    required this.decision,
    required this.expectedGatheringVersion,
    required this.expectedParticipationVersion,
    required this.reasonRef,
  });

  final String idempotencyKey;
  final String gatheringId;
  final String participantPersonaId;
  final GatheringApplicationDecision decision;
  final int expectedGatheringVersion;
  final int expectedParticipationVersion;
  final String reasonRef;
}

final class GatheringInviteInput {
  const GatheringInviteInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.participantPersonaId,
    required this.seatHoldUntil,
    required this.expectedGatheringVersion,
    required this.expectedParticipationVersion,
  });

  final String idempotencyKey;
  final String gatheringId;
  final String participantPersonaId;
  final DateTime seatHoldUntil;
  final int expectedGatheringVersion;
  final int expectedParticipationVersion;
}

final class GatheringRemoveParticipantInput {
  const GatheringRemoveParticipantInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.participantPersonaId,
    required this.reasonRef,
    required this.expectedGatheringVersion,
    required this.expectedParticipationVersion,
  });

  final String idempotencyKey;
  final String gatheringId;
  final String participantPersonaId;
  final String reasonRef;
  final int expectedGatheringVersion;
  final int expectedParticipationVersion;
}

final class GatheringChangeCapacityInput {
  const GatheringChangeCapacityInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.maxParticipants,
    required this.expectedGatheringVersion,
    this.acknowledgementDeadlineAt,
  });

  final String idempotencyKey;
  final String gatheringId;
  final int maxParticipants;
  final int expectedGatheringVersion;
  final DateTime? acknowledgementDeadlineAt;
}

final class GatheringChangeAdmissionInput {
  const GatheringChangeAdmissionInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.action,
    required this.reasonRef,
    required this.expectedGatheringVersion,
    required this.expectedAdmissionControlVersion,
  });

  final String idempotencyKey;
  final String gatheringId;
  final GatheringAdmissionControlAction action;
  final String reasonRef;
  final int expectedGatheringVersion;
  final int expectedAdmissionControlVersion;
}

final class GatheringReasonCommandInput {
  const GatheringReasonCommandInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.reasonRef,
    required this.expectedGatheringVersion,
    this.evidenceRefs = const <GatheringCanonicalObjectRef>[],
  });

  final String idempotencyKey;
  final String gatheringId;
  final String reasonRef;
  final int expectedGatheringVersion;
  final List<GatheringCanonicalObjectRef> evidenceRefs;
}

final class GatheringOutcomeCommandInput {
  const GatheringOutcomeCommandInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.status,
    required this.expectedGatheringVersion,
    this.evidenceRefs = const <GatheringCanonicalObjectRef>[],
  });

  final String idempotencyKey;
  final String gatheringId;
  final GatheringOutcomeStatus status;
  final int expectedGatheringVersion;
  final List<GatheringCanonicalObjectRef> evidenceRefs;
}

final class GatheringCommandResult {
  const GatheringCommandResult({
    required this.gatheringId,
    required this.aggregateVersion,
    required this.lifecycleStatus,
    required this.roomBindingStatus,
    required this.idempotentReplay,
    this.participationState,
    this.participationVersion,
    this.conversationId,
    this.outcomeStatus,
  });

  final String gatheringId;
  final int aggregateVersion;
  final GatheringLifecycleStatus lifecycleStatus;
  final GatheringRoomBindingStatus roomBindingStatus;
  final bool idempotentReplay;
  final GatheringParticipationState? participationState;
  final int? participationVersion;
  final String? conversationId;
  final GatheringOutcomeStatus? outcomeStatus;
}
