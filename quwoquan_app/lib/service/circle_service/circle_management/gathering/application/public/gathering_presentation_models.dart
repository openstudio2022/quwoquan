// Gathering 的跨对象公开展示值。
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';

final class GatheringCreateInitialValue {
  const GatheringCreateInitialValue({
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

enum GatheringPrimaryAction {
  join,
  apply,
  acceptInvitation,
  watchAvailability,
  enterChat,
  readOnly,
  noAction,
}

final class GatheringDetailQuery {
  const GatheringDetailQuery({required this.gatheringId});

  final String gatheringId;
}

final class GatheringHostPresentationSlice {
  const GatheringHostPresentationSlice({
    required this.subjectKind,
    required this.subjectId,
    required this.displayName,
  });

  final GatheringHostSubjectKind subjectKind;
  final String subjectId;
  final String displayName;
}

final class GatheringPublicPurposeSlice {
  const GatheringPublicPurposeSlice({
    required this.title,
    required this.summary,
    this.sourceRefs = const <GatheringSourceRef>[],
    this.requirementLabels = const <String>[],
  });

  final String title;
  final String summary;
  final List<GatheringSourceRef> sourceRefs;
  final List<String> requirementLabels;
}

final class GatheringPublicScheduleSlice {
  const GatheringPublicScheduleSlice({
    required this.timezone,
    required this.startAt,
    required this.endAt,
    this.admissionClosesAt,
  });

  final String timezone;
  final DateTime? startAt;
  final DateTime? endAt;
  final DateTime? admissionClosesAt;
}

final class GatheringPublicPlaceSlice {
  const GatheringPublicPlaceSlice({
    required this.mode,
    required this.coarsePlaceLabel,
    this.exactMeetingPoint,
    this.onlineLocationLabel,
  });

  final GatheringPlaceMode mode;
  final String coarsePlaceLabel;
  final String? exactMeetingPoint;
  final String? onlineLocationLabel;
}

final class GatheringCapacitySlice {
  const GatheringCapacitySlice({
    required this.maxParticipants,
    required this.activeSeatCount,
    required this.invitedSeatHoldCount,
    required this.occupiedSeats,
    required this.remainingSeats,
    required this.full,
  });

  final int maxParticipants;
  final int activeSeatCount;
  final int invitedSeatHoldCount;
  final int occupiedSeats;
  final int remainingSeats;
  final bool full;
}

final class GatheringPolicyPresentationSlice {
  const GatheringPolicyPresentationSlice({
    required this.audience,
    required this.admission,
    required this.timeDisclosure,
    required this.placeDisclosure,
    required this.rosterDisclosure,
  });

  final GatheringAudiencePolicy audience;
  final GatheringAdmissionPolicy admission;
  final GatheringTimeDisclosure timeDisclosure;
  final GatheringPlaceDisclosure placeDisclosure;
  final GatheringRosterDisclosure rosterDisclosure;
}

final class GatheringRevisionSummarySlice {
  const GatheringRevisionSummarySlice({
    required this.revisionNumber,
    required this.materialChange,
    required this.createdAt,
  });

  final int revisionNumber;
  final bool materialChange;
  final DateTime createdAt;
}

final class GatheringViewerParticipationSlice {
  const GatheringViewerParticipationSlice({
    required this.state,
    required this.version,
    required this.admissionSource,
  });

  final GatheringParticipationState state;
  final int version;
  final GatheringAdmissionSource admissionSource;
}

final class GatheringPublicDetailSlice {
  const GatheringPublicDetailSlice({
    required this.gatheringId,
    required this.aggregateVersion,
    required this.host,
    required this.purpose,
    required this.schedule,
    required this.place,
    required this.capacity,
    required this.policy,
    required this.lifecycleStatus,
    required this.temporalPhase,
    required this.admissionState,
    required this.roomBindingStatus,
    required this.revisions,
    this.viewerParticipation,
    this.outcomeStatus,
    this.conversationId,
  });

  final String gatheringId;
  final int aggregateVersion;
  final GatheringHostPresentationSlice host;
  final GatheringPublicPurposeSlice purpose;
  final GatheringPublicScheduleSlice schedule;
  final GatheringPublicPlaceSlice place;
  final GatheringCapacitySlice capacity;
  final GatheringPolicyPresentationSlice policy;
  final GatheringLifecycleStatus lifecycleStatus;
  final GatheringTemporalPhase temporalPhase;
  final GatheringAdmissionState admissionState;
  final GatheringRoomBindingStatus roomBindingStatus;
  final List<GatheringRevisionSummarySlice> revisions;
  final GatheringViewerParticipationSlice? viewerParticipation;
  final GatheringOutcomeStatus? outcomeStatus;
  final String? conversationId;

  GatheringPrimaryAction get primaryAction {
    if (lifecycleStatus == GatheringLifecycleStatus.cancelled ||
        lifecycleStatus == GatheringLifecycleStatus.completed ||
        temporalPhase == GatheringTemporalPhase.ended) {
      return GatheringPrimaryAction.readOnly;
    }

    final participation = viewerParticipation;
    if (participation?.state == GatheringParticipationState.active) {
      final roomReady =
          roomBindingStatus == GatheringRoomBindingStatus.ready &&
          (conversationId?.trim().isNotEmpty ?? false);
      return roomReady
          ? GatheringPrimaryAction.enterChat
          : GatheringPrimaryAction.readOnly;
    }
    if (participation?.state == GatheringParticipationState.invitedPending) {
      return GatheringPrimaryAction.acceptInvitation;
    }
    if (participation?.state ==
        GatheringParticipationState.applicationPending) {
      return GatheringPrimaryAction.readOnly;
    }
    if (temporalPhase == GatheringTemporalPhase.inProgress) {
      return GatheringPrimaryAction.readOnly;
    }
    if (capacity.full || admissionState == GatheringAdmissionState.full) {
      return GatheringPrimaryAction.watchAvailability;
    }
    if (admissionState != GatheringAdmissionState.accepting) {
      return GatheringPrimaryAction.readOnly;
    }
    return switch (policy.admission) {
      GatheringAdmissionPolicy.open => GatheringPrimaryAction.join,
      GatheringAdmissionPolicy.approval => GatheringPrimaryAction.apply,
      GatheringAdmissionPolicy.inviteOnly => GatheringPrimaryAction.noAction,
    };
  }
}

final class GatheringViewerAuthoritySlice {
  const GatheringViewerAuthoritySlice({
    required this.isOrganizer,
    required this.isActiveParticipant,
    required this.canReviewApplications,
    required this.canInvite,
    required this.canRemoveParticipants,
    required this.canChangeCapacity,
    required this.canChangeAdmission,
    required this.canUpdateMaterialDetails,
    required this.canCancel,
    required this.canStart,
    required this.canRecordOutcome,
  });

  static const GatheringViewerAuthoritySlice none =
      GatheringViewerAuthoritySlice(
        isOrganizer: false,
        isActiveParticipant: false,
        canReviewApplications: false,
        canInvite: false,
        canRemoveParticipants: false,
        canChangeCapacity: false,
        canChangeAdmission: false,
        canUpdateMaterialDetails: false,
        canCancel: false,
        canStart: false,
        canRecordOutcome: false,
      );

  final bool isOrganizer;
  final bool isActiveParticipant;
  final bool canReviewApplications;
  final bool canInvite;
  final bool canRemoveParticipants;
  final bool canChangeCapacity;
  final bool canChangeAdmission;
  final bool canUpdateMaterialDetails;
  final bool canCancel;
  final bool canStart;
  final bool canRecordOutcome;

  bool get canViewPrivatePlace => isOrganizer || isActiveParticipant;

  bool get hasHostConsole =>
      canReviewApplications ||
      canInvite ||
      canRemoveParticipants ||
      canChangeCapacity ||
      canChangeAdmission ||
      canUpdateMaterialDetails ||
      canCancel ||
      canStart ||
      canRecordOutcome;
}

final class GatheringApplicationInboxItemSlice {
  const GatheringApplicationInboxItemSlice({
    required this.personaId,
    required this.displayName,
    required this.participationVersion,
    this.answers = const <GatheringApplicationAnswerInput>[],
  });

  final String personaId;
  final String displayName;
  final int participationVersion;
  final List<GatheringApplicationAnswerInput> answers;
}

final class GatheringRosterItemSlice {
  const GatheringRosterItemSlice({
    required this.personaId,
    required this.displayName,
    required this.state,
    required this.admissionSource,
    required this.participationVersion,
  });

  final String personaId;
  final String displayName;
  final GatheringParticipationState state;
  final GatheringAdmissionSource admissionSource;
  final int participationVersion;
}

final class GatheringPrivateDetailSlice {
  const GatheringPrivateDetailSlice({
    required this.authority,
    required this.host,
    required this.purpose,
    required this.schedule,
    required this.place,
    required this.policy,
    required this.applications,
    required this.roster,
    required this.admissionPaused,
    required this.admissionControlVersion,
  });

  final GatheringViewerAuthoritySlice authority;
  final GatheringHostInput host;
  final GatheringPurposeDraft purpose;
  final GatheringScheduleDraft schedule;
  final GatheringPlaceDraft place;
  final GatheringPolicyDraft policy;
  final List<GatheringApplicationInboxItemSlice> applications;
  final List<GatheringRosterItemSlice> roster;
  final bool admissionPaused;
  final int admissionControlVersion;
}

/// 来源对象（实体主页等）「近期公开行动」卡的最小展示投影。
///
/// 只透传云侧 PublicCard 可枚举事实：标题、档期标签、名额与生命周期；
/// 不本地推断到场/成行，计数语义由服务端 disclosure 裁剪。
final class GatheringSourceCardSummary {
  const GatheringSourceCardSummary({
    required this.gatheringId,
    required this.title,
    this.dateLabel,
    this.startAt,
    required this.remainingSeats,
    required this.full,
    required this.lifecycleStatusWire,
  });

  final String gatheringId;
  final String title;

  /// 云侧档期标签（如「本周六下午」）；缺失时由调用方按 startAt 本地化格式。
  final String? dateLabel;
  final DateTime? startAt;
  final int remainingSeats;
  final bool full;
  final String lifecycleStatusWire;
}

/// Host 本人的公开行动卡摘要（「我的行动」入口与分组页；REQ-008）。
///
/// 数据来自 `ListGatheringsByHost` 公开披露读面（仅 audiencePolicy=public 的
/// published/cancelled/completed 行动）；分组事实只由云侧 `lifecycleStatus` 与
/// `temporalPhase` 派生，端不做时间推断。
final class GatheringHostCardSummary {
  const GatheringHostCardSummary({
    required this.gatheringId,
    required this.title,
    this.dateLabel,
    this.startAt,
    required this.remainingSeats,
    required this.full,
    required this.lifecycleStatusWire,
    required this.temporalPhaseWire,
  });

  final String gatheringId;
  final String title;

  /// 云侧档期标签；缺失时由调用方按 startAt 本地化格式。
  final String? dateLabel;
  final DateTime? startAt;
  final int remainingSeats;
  final bool full;
  final String lifecycleStatusWire;

  /// 云侧评估的时态（upcoming / in_progress / ended）。
  final String temporalPhaseWire;
}

/// Host 公开行动 typed page（cursor 分页）。
final class GatheringHostCardPage {
  const GatheringHostCardPage({
    required this.items,
    required this.nextCursor,
    required this.hasMore,
  });

  static const GatheringHostCardPage empty = GatheringHostCardPage(
    items: <GatheringHostCardSummary>[],
    nextCursor: '',
    hasMore: false,
  );

  final List<GatheringHostCardSummary> items;
  final String nextCursor;
  final bool hasMore;
}

final class GatheringDetailPresentationSlice {
  const GatheringDetailPresentationSlice({
    required this.publicDetail,
    this.privateDetail,
  });

  final GatheringPublicDetailSlice publicDetail;
  final GatheringPrivateDetailSlice? privateDetail;

  String? get visibleExactMeetingPoint {
    final publicValue = publicDetail.place.exactMeetingPoint?.trim();
    if (publicValue != null && publicValue.isNotEmpty) {
      return publicValue;
    }
    final privateValue = privateDetail;
    if (privateValue == null ||
        !privateValue.authority.canViewPrivatePlace ||
        privateValue.place.exactMeetingPoint.trim().isEmpty) {
      return null;
    }
    return privateValue.place.exactMeetingPoint.trim();
  }
}
