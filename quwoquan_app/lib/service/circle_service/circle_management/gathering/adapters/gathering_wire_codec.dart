import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart'
    as domain;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as cloud;

domain.GatheringCommandResult gatheringCommandResultFromWire(
  cloud.GatheringCommandResult wire,
) {
  return domain.GatheringCommandResult(
    gatheringId: wire.gatheringId,
    aggregateVersion: wire.aggregateVersion,
    lifecycleStatus: _lifecycleFromWire(wire.lifecycleStatus),
    roomBindingStatus: _roomBindingFromWire(wire.roomBindingStatus),
    idempotentReplay: wire.idempotentReplay,
    participationState: wire.participationState == null
        ? null
        : _participationFromWire(wire.participationState!),
    participationVersion: wire.participationVersion,
    conversationId: wire.conversationId,
    outcomeStatus: wire.outcomeStatus == null
        ? null
        : _outcomeFromWire(wire.outcomeStatus!),
  );
}

cloud.HostBinding hostBindingToWire(domain.GatheringHostInput host) {
  return cloud.HostBinding(
    hostSubjectKind: _hostKindToWire(host.subjectKind),
    hostSubjectId: host.subjectId,
    authorityEvidenceRef: host.authorityEvidenceRef,
    authorityVersion: host.authorityVersion,
  );
}

cloud.CreateGatheringDraftCommand createDraftCommandToWire(
  domain.GatheringCreateDraftInput input,
) {
  return cloud.CreateGatheringDraftCommand(
    hostBinding: hostBindingToWire(input.host),
    creatorParticipates: input.creatorParticipates,
    purpose: _purposeDraftToWire(input.purpose),
    schedule: _scheduleDraftToWire(input.schedule),
    place: _placeDraftToWire(input.place),
    policySet: _policyDraftToWire(input.policy),
  );
}

cloud.UpdateGatheringCommand updateGatheringCommandToWire(
  domain.GatheringUpdateInput input,
) {
  return cloud.UpdateGatheringCommand(
    gatheringId: input.gatheringId,
    expectedGatheringVersion: input.expectedGatheringVersion,
    hostBinding: hostBindingToWire(input.host),
    purpose: _purposeDraftToWire(input.purpose),
    schedule: _scheduleDraftToWire(input.schedule),
    place: _placeDraftToWire(input.place),
    policySet: _policyDraftToWire(input.policy),
    acknowledgementDeadlineAt: input.acknowledgementDeadlineAt,
  );
}

cloud.GatheringVersionCommand versionCommandToWire(
  domain.GatheringVersionCommandInput input,
) {
  return cloud.GatheringVersionCommand(
    gatheringId: input.gatheringId,
    expectedGatheringVersion: input.expectedGatheringVersion,
  );
}

cloud.GatheringParticipationVersionCommand participationCommandToWire(
  domain.GatheringParticipationCommandInput input,
) {
  return cloud.GatheringParticipationVersionCommand(
    gatheringId: input.gatheringId,
    expectedGatheringVersion: input.expectedGatheringVersion,
    expectedParticipationVersion: input.expectedParticipationVersion,
  );
}

cloud.ApplyToGatheringCommand applyCommandToWire(
  domain.GatheringApplyInput input,
) {
  return cloud.ApplyToGatheringCommand(
    gatheringId: input.gatheringId,
    expectedGatheringVersion: input.expectedGatheringVersion,
    expectedParticipationVersion: input.expectedParticipationVersion,
    answers: input.answers
        .map(
          (answer) => cloud.GatheringApplicationAnswer(
            questionId: answer.questionId,
            answerText: answer.answerText,
            selectedOptionIds: answer.selectedOptionIds,
          ),
        )
        .toList(growable: false),
  );
}

cloud.ReviewGatheringApplicationCommand reviewApplicationCommandToWire(
  domain.GatheringReviewApplicationInput input,
) {
  return cloud.ReviewGatheringApplicationCommand(
    gatheringId: input.gatheringId,
    participantPersonaId: input.participantPersonaId,
    decision: input.decision == domain.GatheringApplicationDecision.approve
        ? cloud.GatheringApplicationReviewDecision.approve
        : cloud.GatheringApplicationReviewDecision.reject,
    expectedGatheringVersion: input.expectedGatheringVersion,
    expectedParticipationVersion: input.expectedParticipationVersion,
    reasonRef: input.reasonRef,
  );
}

cloud.InviteToGatheringCommand inviteCommandToWire(
  domain.GatheringInviteInput input,
) {
  return cloud.InviteToGatheringCommand(
    gatheringId: input.gatheringId,
    participantPersonaId: input.participantPersonaId,
    seatHoldUntil: input.seatHoldUntil,
    expectedGatheringVersion: input.expectedGatheringVersion,
    expectedParticipationVersion: input.expectedParticipationVersion,
  );
}

cloud.TargetGatheringParticipationCommand removeParticipantCommandToWire(
  domain.GatheringRemoveParticipantInput input,
) {
  return cloud.TargetGatheringParticipationCommand(
    gatheringId: input.gatheringId,
    participantPersonaId: input.participantPersonaId,
    reasonRef: input.reasonRef,
    expectedGatheringVersion: input.expectedGatheringVersion,
    expectedParticipationVersion: input.expectedParticipationVersion,
  );
}

cloud.ChangeGatheringCapacityCommand changeCapacityCommandToWire(
  domain.GatheringChangeCapacityInput input,
) {
  return cloud.ChangeGatheringCapacityCommand(
    gatheringId: input.gatheringId,
    maxParticipants: input.maxParticipants,
    expectedGatheringVersion: input.expectedGatheringVersion,
    acknowledgementDeadlineAt: input.acknowledgementDeadlineAt,
  );
}

cloud.ChangeGatheringAdmissionCommand admissionControlCommandToWire(
  domain.GatheringChangeAdmissionInput input,
) {
  return cloud.ChangeGatheringAdmissionCommand(
    gatheringId: input.gatheringId,
    reasonRef: input.reasonRef.isEmpty ? null : input.reasonRef,
    expectedGatheringVersion: input.expectedGatheringVersion,
    expectedAdmissionControlVersion: input.expectedAdmissionControlVersion,
  );
}

cloud.GatheringReasonCommand reasonCommandToWire(
  domain.GatheringReasonCommandInput input,
) {
  return cloud.GatheringReasonCommand(
    gatheringId: input.gatheringId,
    reasonRef: input.reasonRef,
    expectedGatheringVersion: input.expectedGatheringVersion,
    evidenceRefs: input.evidenceRefs
        .map(
          (ref) => cloud.CanonicalObjectRef(
            objectTypeRef: ref.objectTypeRef,
            objectId: ref.objectId,
          ),
        )
        .toList(growable: false),
  );
}

cloud.GatheringAvailabilityWatchCommand watchAvailabilityCommandToWire(
  domain.GatheringAvailabilityWatchCommandInput input,
) {
  return cloud.GatheringAvailabilityWatchCommand(
    gatheringId: input.gatheringId,
    expectedGatheringVersion: input.expectedGatheringVersion,
    expectedWatchVersion: input.expectedWatchVersion,
  );
}

GatheringDetailPresentationSlice? presentationFromPublicWire(
  cloud.GatheringPublicDetailSlice wire,
) {
  final card = wire.card;
  return GatheringDetailPresentationSlice(
    publicDetail: GatheringPublicDetailSlice(
      gatheringId: card.gatheringId,
      aggregateVersion: card.aggregateVersion,
      host: GatheringHostPresentationSlice(
        subjectKind: _hostKindFromWire(card.host.hostSubjectKind),
        subjectId: card.host.hostSubjectId,
        displayName: card.host.hostSubjectId,
      ),
      purpose: GatheringPublicPurposeSlice(
        title: card.purpose.title,
        summary: card.purpose.summary ?? '',
        requirementLabels: card.purpose.requirementRefs,
      ),
      schedule: GatheringPublicScheduleSlice(
        timezone: card.schedule.timezone,
        startAt: card.schedule.startAt,
        endAt: card.schedule.endAt,
      ),
      place: GatheringPublicPlaceSlice(
        mode: _placeModeFromWire(card.place.mode),
        coarsePlaceLabel: card.place.coarsePlaceLabel ?? '',
        exactMeetingPoint: card.place.exactMeetingPoint,
      ),
      capacity: GatheringCapacitySlice(
        maxParticipants: card.capacity.maxParticipants,
        activeSeatCount: card.capacity.activeSeatCount,
        invitedSeatHoldCount: card.capacity.invitedSeatHoldCount,
        occupiedSeats: card.capacity.occupiedSeats,
        remainingSeats: card.capacity.remainingSeats,
        full: card.capacity.full,
      ),
      policy: GatheringPolicyPresentationSlice(
        audience: _audienceFromWire(wire.audiencePolicy),
        admission: _admissionPolicyFromWire(wire.admissionPolicy),
        timeDisclosure: _timeDisclosureFromWire(
          wire.disclosurePolicy.timeDisclosure,
        ),
        placeDisclosure: _placeDisclosureFromWire(
          wire.disclosurePolicy.placeDisclosure,
        ),
        rosterDisclosure: _rosterDisclosureFromWire(
          wire.disclosurePolicy.rosterDisclosure,
        ),
      ),
      lifecycleStatus: _lifecycleFromWire(card.lifecycleStatus),
      temporalPhase: _temporalFromWire(card.temporal.temporalPhase),
      admissionState: _admissionStateFromWire(card.admission.admissionState),
      roomBindingStatus: domain.GatheringRoomBindingStatus.pending,
      revisions: wire.revisions
          .map(
            (revision) => GatheringRevisionSummarySlice(
              revisionNumber: revision.revisionNumber,
              materialChange: revision.materialChange,
              createdAt: revision.createdAt,
            ),
          )
          .toList(growable: false),
      viewerParticipation: wire.viewerParticipationState == null
          ? null
          : GatheringViewerParticipationSlice(
              state: _participationFromWire(wire.viewerParticipationState!),
              version: 0,
              admissionSource: domain.GatheringAdmissionSource.open,
            ),
      outcomeStatus: card.outcomeStatus == null
          ? null
          : _outcomeFromWire(card.outcomeStatus!),
      conversationId: wire.conversationId,
    ),
  );
}

cloud.GatheringPurpose _purposeDraftToWire(
  domain.GatheringPurposeDraft purpose,
) {
  return cloud.GatheringPurpose(
    title: purpose.title,
    summary: purpose.summary,
    topicRefs: purpose.topicRefs,
    requirementRefs: purpose.requirementRefs,
    sourceObjectRefs: purpose.sourceRefs
        .map(
          (ref) => cloud.GatheringSourceRef(
            objectRef: cloud.CanonicalObjectRef(
              objectTypeRef: ref.objectRef.objectTypeRef,
              objectId: ref.objectRef.objectId,
            ),
            routeId: ref.routeId,
            sourceDigest: ref.sourceDigest,
          ),
        )
        .toList(growable: false),
    costNotice: cloud.GatheringCostNotice.free,
  );
}

cloud.GatheringSchedule _scheduleDraftToWire(
  domain.GatheringScheduleDraft schedule,
) {
  return cloud.GatheringSchedule(
    timezone: schedule.timezone,
    startAt: schedule.startAt,
    endAt: schedule.endAt,
    admissionClosesAt: schedule.admissionClosesAt,
  );
}

cloud.GatheringPlace _placeDraftToWire(domain.GatheringPlaceDraft place) {
  return cloud.GatheringPlace(
    mode: _placeModeToWire(place.mode),
    coarsePlaceRef: place.coarsePlaceRef == null
        ? null
        : cloud.CanonicalObjectRef(
            objectTypeRef: place.coarsePlaceRef!.objectTypeRef,
            objectId: place.coarsePlaceRef!.objectId,
          ),
    coarsePlaceLabel: place.coarsePlaceLabel,
    exactMeetingPoint: place.exactMeetingPoint,
    onlineLocationRef: place.onlineLocationRef,
  );
}

cloud.GatheringPolicySet _policyDraftToWire(
  domain.GatheringPolicyDraft policy,
) {
  return cloud.GatheringPolicySet(
    audiencePolicy: _audienceToWire(policy.audience),
    admissionPolicy: _admissionPolicyToWire(policy.admission),
    capacityPolicy: cloud.GatheringCapacityPolicy(
      maxParticipants: policy.maxParticipants,
    ),
    disclosurePolicy: cloud.GatheringDisclosurePolicy(
      timeDisclosure: _timeDisclosureToWire(policy.disclosure.time),
      placeDisclosure: _placeDisclosureToWire(policy.disclosure.place),
      rosterDisclosure: _rosterDisclosureToWire(policy.disclosure.roster),
    ),
    applicationQuestions: const <cloud.GatheringApplicationQuestion>[],
    riskControlPolicyRef: policy.riskControlPolicyRef,
  );
}

cloud.GatheringHostSubjectKind _hostKindToWire(
  domain.GatheringHostSubjectKind value,
) {
  return switch (value) {
    domain.GatheringHostSubjectKind.persona =>
      cloud.GatheringHostSubjectKind.persona,
    domain.GatheringHostSubjectKind.entityHomepage =>
      cloud.GatheringHostSubjectKind.entityHomepage,
    domain.GatheringHostSubjectKind.circle =>
      cloud.GatheringHostSubjectKind.circle,
  };
}

domain.GatheringHostSubjectKind _hostKindFromWire(
  cloud.GatheringHostSubjectKind value,
) {
  return switch (value) {
    cloud.GatheringHostSubjectKind.persona =>
      domain.GatheringHostSubjectKind.persona,
    cloud.GatheringHostSubjectKind.entityHomepage =>
      domain.GatheringHostSubjectKind.entityHomepage,
    cloud.GatheringHostSubjectKind.circle =>
      domain.GatheringHostSubjectKind.circle,
  };
}

cloud.GatheringPlaceMode _placeModeToWire(domain.GatheringPlaceMode value) {
  return switch (value) {
    domain.GatheringPlaceMode.physical => cloud.GatheringPlaceMode.physical,
    domain.GatheringPlaceMode.online => cloud.GatheringPlaceMode.online,
    domain.GatheringPlaceMode.hybrid => cloud.GatheringPlaceMode.hybrid,
  };
}

domain.GatheringPlaceMode _placeModeFromWire(cloud.GatheringPlaceMode value) {
  return switch (value) {
    cloud.GatheringPlaceMode.physical => domain.GatheringPlaceMode.physical,
    cloud.GatheringPlaceMode.online => domain.GatheringPlaceMode.online,
    cloud.GatheringPlaceMode.hybrid => domain.GatheringPlaceMode.hybrid,
  };
}

cloud.GatheringAudiencePolicy _audienceToWire(
  domain.GatheringAudiencePolicy value,
) {
  return switch (value) {
    domain.GatheringAudiencePolicy.public =>
      cloud.GatheringAudiencePolicy.public,
    domain.GatheringAudiencePolicy.unlisted =>
      cloud.GatheringAudiencePolicy.unlisted,
    domain.GatheringAudiencePolicy.communityMembers =>
      cloud.GatheringAudiencePolicy.communityMembers,
    domain.GatheringAudiencePolicy.inviteOnly =>
      cloud.GatheringAudiencePolicy.inviteOnly,
  };
}

domain.GatheringAudiencePolicy _audienceFromWire(
  cloud.GatheringAudiencePolicy value,
) {
  return switch (value) {
    cloud.GatheringAudiencePolicy.public =>
      domain.GatheringAudiencePolicy.public,
    cloud.GatheringAudiencePolicy.unlisted =>
      domain.GatheringAudiencePolicy.unlisted,
    cloud.GatheringAudiencePolicy.communityMembers =>
      domain.GatheringAudiencePolicy.communityMembers,
    cloud.GatheringAudiencePolicy.inviteOnly =>
      domain.GatheringAudiencePolicy.inviteOnly,
  };
}

cloud.GatheringAdmissionPolicy _admissionPolicyToWire(
  domain.GatheringAdmissionPolicy value,
) {
  return switch (value) {
    domain.GatheringAdmissionPolicy.open => cloud.GatheringAdmissionPolicy.open,
    domain.GatheringAdmissionPolicy.approval =>
      cloud.GatheringAdmissionPolicy.approval,
    domain.GatheringAdmissionPolicy.inviteOnly =>
      cloud.GatheringAdmissionPolicy.inviteOnly,
  };
}

domain.GatheringAdmissionPolicy _admissionPolicyFromWire(
  cloud.GatheringAdmissionPolicy value,
) {
  return switch (value) {
    cloud.GatheringAdmissionPolicy.open => domain.GatheringAdmissionPolicy.open,
    cloud.GatheringAdmissionPolicy.approval =>
      domain.GatheringAdmissionPolicy.approval,
    cloud.GatheringAdmissionPolicy.inviteOnly =>
      domain.GatheringAdmissionPolicy.inviteOnly,
  };
}

cloud.GatheringTimeDisclosure _timeDisclosureToWire(
  domain.GatheringTimeDisclosure value,
) {
  return switch (value) {
    domain.GatheringTimeDisclosure.exact => cloud.GatheringTimeDisclosure.exact,
    domain.GatheringTimeDisclosure.dateOnly =>
      cloud.GatheringTimeDisclosure.dateOnly,
    domain.GatheringTimeDisclosure.afterJoin =>
      cloud.GatheringTimeDisclosure.afterJoin,
  };
}

domain.GatheringTimeDisclosure _timeDisclosureFromWire(
  cloud.GatheringTimeDisclosure value,
) {
  return switch (value) {
    cloud.GatheringTimeDisclosure.exact => domain.GatheringTimeDisclosure.exact,
    cloud.GatheringTimeDisclosure.dateOnly =>
      domain.GatheringTimeDisclosure.dateOnly,
    cloud.GatheringTimeDisclosure.afterJoin =>
      domain.GatheringTimeDisclosure.afterJoin,
  };
}

cloud.GatheringPlaceDisclosure _placeDisclosureToWire(
  domain.GatheringPlaceDisclosure value,
) {
  return switch (value) {
    domain.GatheringPlaceDisclosure.exact =>
      cloud.GatheringPlaceDisclosure.exact,
    domain.GatheringPlaceDisclosure.coarse =>
      cloud.GatheringPlaceDisclosure.coarse,
    domain.GatheringPlaceDisclosure.afterJoin =>
      cloud.GatheringPlaceDisclosure.afterJoin,
  };
}

domain.GatheringPlaceDisclosure _placeDisclosureFromWire(
  cloud.GatheringPlaceDisclosure value,
) {
  return switch (value) {
    cloud.GatheringPlaceDisclosure.exact =>
      domain.GatheringPlaceDisclosure.exact,
    cloud.GatheringPlaceDisclosure.coarse =>
      domain.GatheringPlaceDisclosure.coarse,
    cloud.GatheringPlaceDisclosure.afterJoin =>
      domain.GatheringPlaceDisclosure.afterJoin,
  };
}

cloud.GatheringRosterDisclosure _rosterDisclosureToWire(
  domain.GatheringRosterDisclosure value,
) {
  return switch (value) {
    domain.GatheringRosterDisclosure.countOnly =>
      cloud.GatheringRosterDisclosure.countOnly,
    domain.GatheringRosterDisclosure.joinedMembers =>
      cloud.GatheringRosterDisclosure.joinedMembers,
    domain.GatheringRosterDisclosure.publicOptIn =>
      cloud.GatheringRosterDisclosure.publicOptIn,
  };
}

domain.GatheringRosterDisclosure _rosterDisclosureFromWire(
  cloud.GatheringRosterDisclosure value,
) {
  return switch (value) {
    cloud.GatheringRosterDisclosure.countOnly =>
      domain.GatheringRosterDisclosure.countOnly,
    cloud.GatheringRosterDisclosure.joinedMembers =>
      domain.GatheringRosterDisclosure.joinedMembers,
    cloud.GatheringRosterDisclosure.publicOptIn =>
      domain.GatheringRosterDisclosure.publicOptIn,
  };
}

domain.GatheringLifecycleStatus _lifecycleFromWire(
  cloud.GatheringLifecycleStatus value,
) {
  return switch (value) {
    cloud.GatheringLifecycleStatus.draft =>
      domain.GatheringLifecycleStatus.draft,
    cloud.GatheringLifecycleStatus.published =>
      domain.GatheringLifecycleStatus.published,
    cloud.GatheringLifecycleStatus.cancelled =>
      domain.GatheringLifecycleStatus.cancelled,
    cloud.GatheringLifecycleStatus.completed =>
      domain.GatheringLifecycleStatus.completed,
  };
}

domain.GatheringRoomBindingStatus _roomBindingFromWire(
  cloud.GatheringRoomBindingStatus value,
) {
  return switch (value) {
    cloud.GatheringRoomBindingStatus.pending =>
      domain.GatheringRoomBindingStatus.pending,
    cloud.GatheringRoomBindingStatus.ready =>
      domain.GatheringRoomBindingStatus.ready,
    cloud.GatheringRoomBindingStatus.failed =>
      domain.GatheringRoomBindingStatus.failed,
  };
}

domain.GatheringTemporalPhase _temporalFromWire(
  cloud.GatheringTemporalPhase value,
) {
  return switch (value) {
    cloud.GatheringTemporalPhase.upcoming =>
      domain.GatheringTemporalPhase.upcoming,
    cloud.GatheringTemporalPhase.inProgress =>
      domain.GatheringTemporalPhase.inProgress,
    cloud.GatheringTemporalPhase.ended => domain.GatheringTemporalPhase.ended,
  };
}

domain.GatheringAdmissionState _admissionStateFromWire(
  cloud.GatheringAdmissionState value,
) {
  return switch (value) {
    cloud.GatheringAdmissionState.accepting =>
      domain.GatheringAdmissionState.accepting,
    cloud.GatheringAdmissionState.full => domain.GatheringAdmissionState.full,
    cloud.GatheringAdmissionState.paused =>
      domain.GatheringAdmissionState.paused,
    cloud.GatheringAdmissionState.closed =>
      domain.GatheringAdmissionState.closed,
  };
}

domain.GatheringParticipationState _participationFromWire(
  cloud.GatheringParticipationState value,
) {
  return switch (value) {
    cloud.GatheringParticipationState.invitedPending =>
      domain.GatheringParticipationState.invitedPending,
    cloud.GatheringParticipationState.applicationPending =>
      domain.GatheringParticipationState.applicationPending,
    cloud.GatheringParticipationState.active =>
      domain.GatheringParticipationState.active,
    cloud.GatheringParticipationState.closed =>
      domain.GatheringParticipationState.closed,
  };
}

domain.GatheringOutcomeStatus _outcomeFromWire(
  cloud.GatheringOutcomeStatus value,
) {
  return switch (value) {
    cloud.GatheringOutcomeStatus.occurred =>
      domain.GatheringOutcomeStatus.occurred,
    cloud.GatheringOutcomeStatus.didNotHappen =>
      domain.GatheringOutcomeStatus.didNotHappen,
    cloud.GatheringOutcomeStatus.endedEarly =>
      domain.GatheringOutcomeStatus.endedEarly,
    cloud.GatheringOutcomeStatus.safetyTerminated =>
      domain.GatheringOutcomeStatus.safetyTerminated,
    cloud.GatheringOutcomeStatus.disputed =>
      domain.GatheringOutcomeStatus.disputed,
    cloud.GatheringOutcomeStatus.unverified =>
      domain.GatheringOutcomeStatus.unverified,
  };
}

GatheringPrivateDetailSlice? privatePresentationFromWire(
  cloud.GatheringPrivateDetailSlice wire,
) {
  final host = domain.GatheringHostInput(
    subjectKind: _hostKindFromWire(wire.hostBinding.hostSubjectKind),
    subjectId: wire.hostBinding.hostSubjectId,
    authorityEvidenceRef: wire.hostBinding.authorityEvidenceRef,
    authorityVersion: wire.hostBinding.authorityVersion,
  );
  final isOrganizer = wire.organizerAssignments.any(
    (assignment) => assignment.revokedAt == null,
  );
  return GatheringPrivateDetailSlice(
    authority: GatheringViewerAuthoritySlice(
      isOrganizer: isOrganizer,
      isActiveParticipant: false,
      canReviewApplications: isOrganizer,
      canInvite: isOrganizer,
      canRemoveParticipants: isOrganizer,
      canChangeCapacity: isOrganizer,
      canChangeAdmission: isOrganizer,
      canUpdateMaterialDetails: isOrganizer,
      canCancel: isOrganizer,
      canStart: isOrganizer,
      canRecordOutcome: isOrganizer,
    ),
    host: host,
    purpose: domain.GatheringPurposeDraft(
      title: wire.purpose.title ?? '',
      summary: wire.purpose.summary ?? '',
      topicRefs: wire.purpose.topicRefs,
      requirementRefs: wire.purpose.requirementRefs,
      sourceRefs: const <domain.GatheringSourceRef>[],
    ),
    schedule: domain.GatheringScheduleDraft(
      timezone: wire.schedule.timezone ?? 'UTC',
      startAt: wire.schedule.startAt ?? wire.createdAt,
      endAt: wire.schedule.endAt ?? wire.createdAt,
      admissionClosesAt: wire.schedule.admissionClosesAt,
    ),
    place: domain.GatheringPlaceDraft(
      mode: _placeModeFromWire(wire.place.mode),
      coarsePlaceRef: wire.place.coarsePlaceRef == null
          ? null
          : domain.GatheringCanonicalObjectRef(
              objectTypeRef: wire.place.coarsePlaceRef!.objectTypeRef,
              objectId: wire.place.coarsePlaceRef!.objectId,
            ),
      coarsePlaceLabel: wire.place.coarsePlaceLabel ?? '',
      exactMeetingPoint: wire.place.exactMeetingPoint ?? '',
      onlineLocationRef: wire.place.onlineLocationRef ?? '',
    ),
    policy: domain.GatheringPolicyDraft(
      audience: _audienceFromWire(wire.policySet.audiencePolicy),
      admission: _admissionPolicyFromWire(wire.policySet.admissionPolicy),
      maxParticipants: wire.policySet.capacityPolicy.maxParticipants,
      disclosure: domain.GatheringDisclosurePolicyDraft(
        time: _timeDisclosureFromWire(
          wire.policySet.disclosurePolicy.timeDisclosure,
        ),
        place: _placeDisclosureFromWire(
          wire.policySet.disclosurePolicy.placeDisclosure,
        ),
        roster: _rosterDisclosureFromWire(
          wire.policySet.disclosurePolicy.rosterDisclosure,
        ),
      ),
      riskControlPolicyRef: wire.policySet.riskControlPolicyRef,
    ),
    applications: const <GatheringApplicationInboxItemSlice>[],
    roster: const <GatheringRosterItemSlice>[],
    admissionPaused:
        wire.admissionControl.status ==
        cloud.GatheringAdmissionControlStatus.paused,
    admissionControlVersion: wire.admissionControl.version,
  );
}

String _scheduleLabel(cloud.GatheringSchedule schedule) {
  final start = (schedule.startAt ?? DateTime.fromMillisecondsSinceEpoch(0))
      .toLocal();
  final end = (schedule.endAt ?? start).toLocal();
  return '${start.year}-${start.month.toString().padLeft(2, '0')}-'
      '${start.day.toString().padLeft(2, '0')} '
      '${start.hour.toString().padLeft(2, '0')}:'
      '${start.minute.toString().padLeft(2, '0')}-'
      '${end.hour.toString().padLeft(2, '0')}:'
      '${end.minute.toString().padLeft(2, '0')}';
}

String _placeLabel(cloud.GatheringPlace place) {
  final coarse = place.coarsePlaceLabel?.trim();
  if (coarse != null && coarse.isNotEmpty) {
    return coarse;
  }
  return switch (place.mode) {
    cloud.GatheringPlaceMode.online => 'online',
    cloud.GatheringPlaceMode.hybrid => 'hybrid',
    cloud.GatheringPlaceMode.physical => 'physical',
  };
}

GatheringBoardCircleSlice gatheringBoardCircleFromPrivateWire(
  cloud.GatheringPrivateDetailSlice wire,
) {
  final capacity = wire.capacity;
  return GatheringBoardCircleSlice(
    activity: GatheringBoardActivitySlice(
      gatheringId: wire.gatheringId,
      title: wire.purpose.title ?? '',
      scheduleLabel: _scheduleLabel(wire.schedule),
      placeLabel: _placeLabel(wire.place),
    ),
    participation: GatheringBoardParticipationSlice(
      activeCount: capacity.activeSeatCount,
      maxParticipants: capacity.maxParticipants,
      remainingSeats: capacity.remainingSeats,
      summaryLabel: '${capacity.activeSeatCount}/${capacity.maxParticipants}',
    ),
    plan: const GatheringBoardPlanSlice(
      capability: GatheringBoardCapabilitySummary(
        state: GatheringBoardCapabilityState.unavailable,
        summaryLabel: 'plan',
        unavailableReason:
            GatheringBoardCapabilityUnavailableReason.notConfigured,
      ),
    ),
    mapCapability: const GatheringBoardCapabilitySummary(
      state: GatheringBoardCapabilityState.unavailable,
      summaryLabel: 'map',
      unavailableReason:
          GatheringBoardCapabilityUnavailableReason.notConfigured,
    ),
    calendarCapability: const GatheringBoardCapabilitySummary(
      state: GatheringBoardCapabilityState.unavailable,
      summaryLabel: 'calendar',
      unavailableReason:
          GatheringBoardCapabilityUnavailableReason.notConfigured,
    ),
  );
}
