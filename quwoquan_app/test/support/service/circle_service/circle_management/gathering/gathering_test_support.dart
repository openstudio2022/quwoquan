import 'dart:async';

// Canonical object-owned support for Gathering local-contract suites.

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_page_copy.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';
import 'package:quwoquan_app/runtime/di/gathering_dependencies.dart';

const GatheringCreatePageCopy gatheringCreateTestCopy = GatheringCreatePageCopy(
  pageTitle: 'CREATE',
  purposeSection: 'PURPOSE',
  titleLabel: 'TITLE',
  titlePlaceholder: 'TITLE_HINT',
  summaryLabel: 'SUMMARY',
  summaryPlaceholder: 'SUMMARY_HINT',
  sourceReferencesLabel: 'SOURCES',
  scheduleSection: 'SCHEDULE',
  timezoneLabel: 'TIMEZONE',
  startAtLabel: 'START',
  endAtLabel: 'END',
  admissionClosesAtLabel: 'ADMISSION_CLOSE',
  dateTimePlaceholder: 'ISO_TIME',
  placeSection: 'PLACE',
  placeModeLabel: 'PLACE_MODE',
  placeModePhysical: 'PHYSICAL',
  placeModeOnline: 'ONLINE',
  placeModeHybrid: 'HYBRID',
  coarsePlaceLabel: 'COARSE_PLACE',
  exactMeetingPointLabel: 'EXACT_PLACE',
  onlineLocationLabel: 'ONLINE_LOCATION',
  policySection: 'POLICY',
  audienceLabel: 'AUDIENCE',
  audiencePublic: 'PUBLIC',
  audienceUnlisted: 'UNLISTED',
  audienceCommunityMembers: 'COMMUNITY',
  audienceInviteOnly: 'INVITE_AUDIENCE',
  admissionLabel: 'ADMISSION',
  admissionOpen: 'OPEN',
  admissionApproval: 'APPROVAL',
  admissionInviteOnly: 'INVITE_ADMISSION',
  capacityLabel: 'CAPACITY',
  timeDisclosureLabel: 'TIME_DISCLOSURE',
  placeDisclosureLabel: 'PLACE_DISCLOSURE',
  rosterDisclosureLabel: 'ROSTER_DISCLOSURE',
  disclosureExact: 'EXACT',
  disclosureDateOnly: 'DATE_ONLY',
  disclosureCoarse: 'COARSE',
  disclosureAfterJoin: 'AFTER_JOIN',
  rosterCountOnly: 'COUNT_ONLY',
  rosterJoinedMembers: 'JOINED_MEMBERS',
  rosterPublicOptIn: 'PUBLIC_OPT_IN',
  riskControlPolicyLabel: 'RISK_POLICY',
  hostSection: 'HOST',
  hostKindLabel: 'HOST_KIND',
  hostPersona: 'PERSONA',
  hostEntity: 'ENTITY',
  hostCircle: 'CIRCLE',
  hostSubjectIdLabel: 'HOST_ID',
  authorityEvidenceLabel: 'AUTHORITY_EVIDENCE',
  authorityVersionLabel: 'AUTHORITY_VERSION',
  creatorParticipatesLabel: 'CREATOR_PARTICIPATES',
  submitAction: 'SUBMIT',
  retryAction: 'RETRY',
  invalidFormMessage: 'INVALID_FORM',
  draftStepLabel: 'DRAFT_STEP',
  roomStepLabel: 'ROOM_STEP',
  publishStepLabel: 'PUBLISH_STEP',
  completedStepLabel: 'COMPLETED_STEP',
);

const GatheringDetailPageCopy gatheringDetailTestCopy = GatheringDetailPageCopy(
  pageTitle: 'DETAIL',
  emptyTitle: 'EMPTY',
  retryAction: 'RETRY',
  hostLabel: 'HOST',
  timeLabel: 'TIME',
  placeLabel: 'PLACE',
  privatePlaceLabel: 'PRIVATE_PLACE',
  capacityLabel: 'CAPACITY',
  policyLabel: 'POLICY',
  requirementsLabel: 'REQUIREMENTS',
  revisionsLabel: 'REVISIONS',
  joinAction: 'JOIN',
  applyAction: 'APPLY',
  acceptInvitationAction: 'ACCEPT',
  watchAvailabilityAction: 'WATCH',
  enterChatAction: 'ENTER_CHAT',
  readOnlyAction: 'READ_ONLY',
  hostConsoleTitle: 'HOST_CONSOLE',
  applicationsTitle: 'APPLICATIONS',
  applicationAnswersLabel: 'ANSWERS',
  approveAction: 'APPROVE',
  rejectAction: 'REJECT',
  inviteTitle: 'INVITE',
  personaIdLabel: 'PERSONA_ID',
  inviteAction: 'INVITE_ACTION',
  rosterTitle: 'ROSTER',
  removeAction: 'REMOVE',
  capacityAction: 'CHANGE_CAPACITY',
  pauseAdmissionAction: 'PAUSE',
  resumeAdmissionAction: 'RESUME',
  materialUpdateAction: 'MATERIAL_UPDATE',
  cancelAction: 'CANCEL',
  startAction: 'START',
  outcomeAction: 'OUTCOME',
  reasonLabel: 'REASON',
  occurredOutcome: 'OCCURRED',
  didNotHappenOutcome: 'DID_NOT_HAPPEN',
  endedEarlyOutcome: 'ENDED_EARLY',
  safetyTerminatedOutcome: 'SAFETY_TERMINATED',
  disputedOutcome: 'DISPUTED',
  unverifiedOutcome: 'UNVERIFIED',
  audiencePublic: 'PUBLIC',
  audienceUnlisted: 'UNLISTED',
  audienceCommunityMembers: 'COMMUNITY',
  audienceInviteOnly: 'INVITE_AUDIENCE',
  admissionOpen: 'OPEN',
  admissionApproval: 'APPROVAL',
  admissionInviteOnly: 'INVITE_ADMISSION',
  noRequirements: 'NO_REQUIREMENTS',
);

GatheringCreateInitialSeedData gatheringInitialSeedData({
  int maxParticipants = 4,
}) {
  return GatheringCreateInitialSeedData(
    host: const GatheringHostInput(
      subjectKind: GatheringHostSubjectKind.persona,
      subjectId: 'host-persona',
      authorityEvidenceRef: 'authority-evidence',
      authorityVersion: 1,
    ),
    creatorParticipates: true,
    purpose: GatheringPurposeDraft(
      title: 'Gathering title',
      summary: 'Gathering summary',
      sourceRefs: <GatheringSourceRef>[
        GatheringSourceRef(
          objectRef: GatheringCanonicalObjectRef(
            objectTypeRef: 'content.post',
            objectId: 'post-1',
          ),
          routeId: 'post_detail',
          sourceDigest: 'source-digest',
        ),
      ],
    ),
    schedule: GatheringScheduleDraft(
      timezone: 'Asia/Shanghai',
      startAt: DateTime.utc(2026, 8, 8, 10),
      endAt: DateTime.utc(2026, 8, 8, 12),
      admissionClosesAt: DateTime.utc(2026, 8, 8, 9),
    ),
    place: GatheringPlaceDraft(
      mode: GatheringPlaceMode.physical,
      coarsePlaceLabel: 'Shanghai',
      exactMeetingPoint: 'Gate 1',
      onlineLocationRef: '',
    ),
    policy: GatheringPolicyDraft(
      audience: GatheringAudiencePolicy.public,
      admission: GatheringAdmissionPolicy.open,
      maxParticipants: maxParticipants,
      disclosure: GatheringDisclosurePolicyDraft(
        time: GatheringTimeDisclosure.exact,
        place: GatheringPlaceDisclosure.afterJoin,
        roster: GatheringRosterDisclosure.countOnly,
      ),
      riskControlPolicyRef: 'risk-policy',
    ),
  );
}

final class GatheringCreateInitialSeedData {
  const GatheringCreateInitialSeedData({
    required this.host,
    required this.creatorParticipates,
    required this.purpose,
    required this.schedule,
    required this.place,
    required this.policy,
  });

  final GatheringHostInput host;
  final bool creatorParticipates;
  final GatheringPurposeDraft purpose;
  final GatheringScheduleDraft schedule;
  final GatheringPlaceDraft place;
  final GatheringPolicyDraft policy;
}

GatheringPublicDetailSlice publicGatheringDetail({
  int maxParticipants = 4,
  int occupiedSeats = 1,
  bool full = false,
  GatheringAdmissionPolicy admission = GatheringAdmissionPolicy.open,
  GatheringAudiencePolicy audience = GatheringAudiencePolicy.public,
  GatheringLifecycleStatus lifecycle = GatheringLifecycleStatus.published,
  GatheringTemporalPhase temporal = GatheringTemporalPhase.upcoming,
  GatheringAdmissionState admissionState = GatheringAdmissionState.accepting,
  GatheringParticipationState? participationState,
  GatheringAdmissionSource participationSource = GatheringAdmissionSource.open,
  GatheringRoomBindingStatus roomBinding = GatheringRoomBindingStatus.ready,
  String? conversationId,
  String? exactMeetingPoint,
  GatheringOutcomeStatus? outcome,
  int aggregateVersion = 3,
}) {
  return GatheringPublicDetailSlice(
    gatheringId: 'gathering-1',
    aggregateVersion: aggregateVersion,
    host: GatheringHostPresentationSlice(
      subjectKind: GatheringHostSubjectKind.persona,
      subjectId: 'host-persona',
      displayName: 'Host Name',
    ),
    purpose: GatheringPublicPurposeSlice(
      title: 'Public Gathering',
      summary: 'Public summary',
      requirementLabels: <String>['Bring water'],
    ),
    schedule: GatheringPublicScheduleSlice(
      timezone: 'Asia/Shanghai',
      startAt: DateTime.utc(2026, 8, 8, 10),
      endAt: DateTime.utc(2026, 8, 8, 12),
    ),
    place: GatheringPublicPlaceSlice(
      mode: GatheringPlaceMode.physical,
      coarsePlaceLabel: 'Shanghai',
      exactMeetingPoint: exactMeetingPoint,
    ),
    capacity: GatheringCapacitySlice(
      maxParticipants: maxParticipants,
      activeSeatCount: occupiedSeats,
      invitedSeatHoldCount: 0,
      occupiedSeats: occupiedSeats,
      remainingSeats: maxParticipants - occupiedSeats,
      full: full,
    ),
    policy: GatheringPolicyPresentationSlice(
      audience: audience,
      admission: admission,
      timeDisclosure: GatheringTimeDisclosure.exact,
      placeDisclosure: GatheringPlaceDisclosure.afterJoin,
      rosterDisclosure: GatheringRosterDisclosure.countOnly,
    ),
    lifecycleStatus: lifecycle,
    temporalPhase: temporal,
    admissionState: admissionState,
    roomBindingStatus: roomBinding,
    revisions: const <GatheringRevisionSummarySlice>[],
    viewerParticipation: participationState == null
        ? null
        : GatheringViewerParticipationSlice(
            state: participationState,
            version: 2,
            admissionSource: participationSource,
          ),
    outcomeStatus: outcome,
    conversationId: conversationId,
  );
}

GatheringPrivateDetailSlice privateGatheringDetail({
  GatheringViewerAuthoritySlice authority = GatheringViewerAuthoritySlice.none,
  String exactMeetingPoint = 'Private gate',
  List<GatheringApplicationInboxItemSlice> applications =
      const <GatheringApplicationInboxItemSlice>[],
  List<GatheringRosterItemSlice> roster = const <GatheringRosterItemSlice>[],
}) {
  final seed = gatheringInitialSeedData();
  return GatheringPrivateDetailSlice(
    authority: authority,
    host: seed.host,
    purpose: seed.purpose,
    schedule: seed.schedule,
    place: GatheringPlaceDraft(
      mode: seed.place.mode,
      coarsePlaceLabel: seed.place.coarsePlaceLabel,
      exactMeetingPoint: exactMeetingPoint,
      onlineLocationRef: seed.place.onlineLocationRef,
    ),
    policy: seed.policy,
    applications: applications,
    roster: roster,
    admissionPaused: false,
    admissionControlVersion: 1,
  );
}

const GatheringViewerAuthoritySlice hostAuthority =
    GatheringViewerAuthoritySlice(
      isOrganizer: true,
      isActiveParticipant: false,
      canReviewApplications: true,
      canInvite: true,
      canRemoveParticipants: true,
      canChangeCapacity: true,
      canChangeAdmission: true,
      canUpdateMaterialDetails: true,
      canCancel: true,
      canStart: true,
      canRecordOutcome: true,
    );

final class InMemoryGatheringPort
    implements GatheringCommandWriter, GatheringQueryReader {
  InMemoryGatheringPort({this.detail});

  GatheringDetailPresentationSlice? detail;
  Object? queryError;
  Completer<void>? queryGate;
  Completer<void>? createGate;

  int queryCalls = 0;
  int createCalls = 0;
  int publishCalls = 0;
  int joinCalls = 0;
  int applyCalls = 0;
  int acceptCalls = 0;
  int watchCalls = 0;
  int reviewCalls = 0;
  int inviteCalls = 0;
  int removeCalls = 0;
  int capacityCalls = 0;
  int admissionCalls = 0;
  int updateCalls = 0;
  int cancelCalls = 0;
  int startCalls = 0;
  int outcomeCalls = 0;

  GatheringCreateDraftInput? lastCreate;
  GatheringVersionCommandInput? lastPublish;
  GatheringReviewApplicationInput? lastReview;
  GatheringChangeCapacityInput? lastCapacity;

  GatheringCommandResult _result({
    int version = 4,
    GatheringLifecycleStatus lifecycle = GatheringLifecycleStatus.published,
    GatheringRoomBindingStatus room = GatheringRoomBindingStatus.ready,
    GatheringParticipationState? participation,
    GatheringOutcomeStatus? outcome,
  }) {
    return GatheringCommandResult(
      gatheringId: 'gathering-1',
      aggregateVersion: version,
      lifecycleStatus: lifecycle,
      roomBindingStatus: room,
      idempotentReplay: false,
      participationState: participation,
      participationVersion: participation == null ? null : 3,
      conversationId: room == GatheringRoomBindingStatus.ready
          ? 'conversation-1'
          : null,
      outcomeStatus: outcome,
    );
  }

  @override
  Future<GatheringDetailPresentationSlice?> getDetail(
    GatheringDetailQuery query,
  ) async {
    queryCalls += 1;
    await queryGate?.future;
    final error = queryError;
    if (error != null) throw error;
    return detail;
  }

  @override
  Future<GatheringCommandResult> createDraft(
    GatheringCreateDraftInput input,
  ) async {
    createCalls += 1;
    lastCreate = input;
    await createGate?.future;
    return _result(
      version: 1,
      lifecycle: GatheringLifecycleStatus.draft,
      room: GatheringRoomBindingStatus.pending,
    );
  }

  @override
  Future<GatheringCommandResult> publish(
    GatheringVersionCommandInput input,
  ) async {
    publishCalls += 1;
    lastPublish = input;
    return _result(version: 3);
  }

  @override
  Future<GatheringCommandResult> joinOpen(
    GatheringParticipationCommandInput input,
  ) async {
    joinCalls += 1;
    return _result(participation: GatheringParticipationState.active);
  }

  @override
  Future<GatheringCommandResult> apply(GatheringApplyInput input) async {
    applyCalls += 1;
    return _result(
      participation: GatheringParticipationState.applicationPending,
    );
  }

  @override
  Future<GatheringCommandResult> acceptInvitation(
    GatheringParticipationCommandInput input,
  ) async {
    acceptCalls += 1;
    return _result(participation: GatheringParticipationState.active);
  }

  @override
  Future<GatheringCommandResult> watchAvailability(
    GatheringVersionCommandInput input,
  ) async {
    watchCalls += 1;
    return _result();
  }

  @override
  Future<GatheringCommandResult> reviewApplication(
    GatheringReviewApplicationInput input,
  ) async {
    reviewCalls += 1;
    lastReview = input;
    return _result();
  }

  @override
  Future<GatheringCommandResult> invite(GatheringInviteInput input) async {
    inviteCalls += 1;
    return _result();
  }

  @override
  Future<GatheringCommandResult> removeParticipant(
    GatheringRemoveParticipantInput input,
  ) async {
    removeCalls += 1;
    return _result();
  }

  @override
  Future<GatheringCommandResult> changeCapacity(
    GatheringChangeCapacityInput input,
  ) async {
    capacityCalls += 1;
    lastCapacity = input;
    return _result();
  }

  @override
  Future<GatheringCommandResult> changeAdmission(
    GatheringChangeAdmissionInput input,
  ) async {
    admissionCalls += 1;
    return _result();
  }

  @override
  Future<GatheringCommandResult> update(GatheringUpdateInput input) async {
    updateCalls += 1;
    return _result();
  }

  @override
  Future<GatheringCommandResult> cancel(
    GatheringReasonCommandInput input,
  ) async {
    cancelCalls += 1;
    return _result(lifecycle: GatheringLifecycleStatus.cancelled);
  }

  @override
  Future<GatheringCommandResult> start(
    GatheringVersionCommandInput input,
  ) async {
    startCalls += 1;
    return _result();
  }

  @override
  Future<GatheringCommandResult> recordOutcome(
    GatheringOutcomeCommandInput input,
  ) async {
    outcomeCalls += 1;
    return _result(
      lifecycle: GatheringLifecycleStatus.completed,
      outcome: input.status,
    );
  }
}

List<Override> gatheringBoundaryOverrides(InMemoryGatheringPort port) {
  return <Override>[
    gatheringCommandWriterProvider.overrideWithValue(port),
    gatheringQueryReaderProvider.overrideWithValue(port),
  ];
}

Future<void> pumpGatheringWidget(
  WidgetTester tester, {
  required InMemoryGatheringPort port,
  required Widget child,
}) async {
  await tester.binding.setSurfaceSize(const Size(430, 900));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(
    ProviderScope(
      overrides: gatheringBoundaryOverrides(port),
      child: CupertinoApp(home: child),
    ),
  );
  await tester.pump();
}
