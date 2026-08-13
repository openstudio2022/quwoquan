import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';

final class GatheringCreatePageCopy {
  const GatheringCreatePageCopy({
    required this.pageTitle,
    required this.purposeSection,
    required this.titleLabel,
    required this.titlePlaceholder,
    required this.summaryLabel,
    required this.summaryPlaceholder,
    required this.sourceReferencesLabel,
    required this.scheduleSection,
    required this.timezoneLabel,
    required this.startAtLabel,
    required this.endAtLabel,
    required this.admissionClosesAtLabel,
    required this.dateTimePlaceholder,
    required this.placeSection,
    required this.placeModeLabel,
    required this.placeModePhysical,
    required this.placeModeOnline,
    required this.placeModeHybrid,
    required this.coarsePlaceLabel,
    required this.exactMeetingPointLabel,
    required this.onlineLocationLabel,
    required this.policySection,
    required this.audienceLabel,
    required this.audiencePublic,
    required this.audienceUnlisted,
    required this.audienceCommunityMembers,
    required this.audienceInviteOnly,
    required this.admissionLabel,
    required this.admissionOpen,
    required this.admissionApproval,
    required this.admissionInviteOnly,
    required this.capacityLabel,
    required this.timeDisclosureLabel,
    required this.placeDisclosureLabel,
    required this.rosterDisclosureLabel,
    required this.disclosureExact,
    required this.disclosureDateOnly,
    required this.disclosureCoarse,
    required this.disclosureAfterJoin,
    required this.rosterCountOnly,
    required this.rosterJoinedMembers,
    required this.rosterPublicOptIn,
    required this.riskControlPolicyLabel,
    required this.hostSection,
    required this.hostKindLabel,
    required this.hostPersona,
    required this.hostEntity,
    required this.hostCircle,
    required this.hostSubjectIdLabel,
    required this.authorityEvidenceLabel,
    required this.authorityVersionLabel,
    required this.creatorParticipatesLabel,
    required this.submitAction,
    required this.retryAction,
    required this.invalidFormMessage,
    required this.draftStepLabel,
    required this.roomStepLabel,
    required this.publishStepLabel,
    required this.completedStepLabel,
  });

  final String pageTitle;
  final String purposeSection;
  final String titleLabel;
  final String titlePlaceholder;
  final String summaryLabel;
  final String summaryPlaceholder;
  final String sourceReferencesLabel;
  final String scheduleSection;
  final String timezoneLabel;
  final String startAtLabel;
  final String endAtLabel;
  final String admissionClosesAtLabel;
  final String dateTimePlaceholder;
  final String placeSection;
  final String placeModeLabel;
  final String placeModePhysical;
  final String placeModeOnline;
  final String placeModeHybrid;
  final String coarsePlaceLabel;
  final String exactMeetingPointLabel;
  final String onlineLocationLabel;
  final String policySection;
  final String audienceLabel;
  final String audiencePublic;
  final String audienceUnlisted;
  final String audienceCommunityMembers;
  final String audienceInviteOnly;
  final String admissionLabel;
  final String admissionOpen;
  final String admissionApproval;
  final String admissionInviteOnly;
  final String capacityLabel;
  final String timeDisclosureLabel;
  final String placeDisclosureLabel;
  final String rosterDisclosureLabel;
  final String disclosureExact;
  final String disclosureDateOnly;
  final String disclosureCoarse;
  final String disclosureAfterJoin;
  final String rosterCountOnly;
  final String rosterJoinedMembers;
  final String rosterPublicOptIn;
  final String riskControlPolicyLabel;
  final String hostSection;
  final String hostKindLabel;
  final String hostPersona;
  final String hostEntity;
  final String hostCircle;
  final String hostSubjectIdLabel;
  final String authorityEvidenceLabel;
  final String authorityVersionLabel;
  final String creatorParticipatesLabel;
  final String submitAction;
  final String retryAction;
  final String invalidFormMessage;
  final String draftStepLabel;
  final String roomStepLabel;
  final String publishStepLabel;
  final String completedStepLabel;

  String placeMode(GatheringPlaceMode value) => switch (value) {
    GatheringPlaceMode.physical => placeModePhysical,
    GatheringPlaceMode.online => placeModeOnline,
    GatheringPlaceMode.hybrid => placeModeHybrid,
  };

  String audience(GatheringAudiencePolicy value) => switch (value) {
    GatheringAudiencePolicy.public => audiencePublic,
    GatheringAudiencePolicy.unlisted => audienceUnlisted,
    GatheringAudiencePolicy.communityMembers => audienceCommunityMembers,
    GatheringAudiencePolicy.inviteOnly => audienceInviteOnly,
  };

  String admission(GatheringAdmissionPolicy value) => switch (value) {
    GatheringAdmissionPolicy.open => admissionOpen,
    GatheringAdmissionPolicy.approval => admissionApproval,
    GatheringAdmissionPolicy.inviteOnly => admissionInviteOnly,
  };

  String timeDisclosure(GatheringTimeDisclosure value) => switch (value) {
    GatheringTimeDisclosure.exact => disclosureExact,
    GatheringTimeDisclosure.dateOnly => disclosureDateOnly,
    GatheringTimeDisclosure.afterJoin => disclosureAfterJoin,
  };

  String placeDisclosure(GatheringPlaceDisclosure value) => switch (value) {
    GatheringPlaceDisclosure.exact => disclosureExact,
    GatheringPlaceDisclosure.coarse => disclosureCoarse,
    GatheringPlaceDisclosure.afterJoin => disclosureAfterJoin,
  };

  String rosterDisclosure(GatheringRosterDisclosure value) => switch (value) {
    GatheringRosterDisclosure.countOnly => rosterCountOnly,
    GatheringRosterDisclosure.joinedMembers => rosterJoinedMembers,
    GatheringRosterDisclosure.publicOptIn => rosterPublicOptIn,
  };

  String hostKind(GatheringHostSubjectKind value) => switch (value) {
    GatheringHostSubjectKind.persona => hostPersona,
    GatheringHostSubjectKind.entityHomepage => hostEntity,
    GatheringHostSubjectKind.circle => hostCircle,
  };
}

final class GatheringDetailPageCopy {
  const GatheringDetailPageCopy({
    required this.pageTitle,
    required this.emptyTitle,
    required this.retryAction,
    required this.hostLabel,
    required this.timeLabel,
    required this.placeLabel,
    required this.privatePlaceLabel,
    required this.capacityLabel,
    required this.policyLabel,
    required this.requirementsLabel,
    required this.revisionsLabel,
    required this.joinAction,
    required this.applyAction,
    required this.acceptInvitationAction,
    required this.watchAvailabilityAction,
    required this.enterChatAction,
    required this.readOnlyAction,
    required this.hostConsoleTitle,
    required this.applicationsTitle,
    required this.applicationAnswersLabel,
    required this.approveAction,
    required this.rejectAction,
    required this.inviteTitle,
    required this.personaIdLabel,
    required this.inviteAction,
    required this.rosterTitle,
    required this.removeAction,
    required this.capacityAction,
    required this.pauseAdmissionAction,
    required this.resumeAdmissionAction,
    required this.materialUpdateAction,
    required this.cancelAction,
    required this.startAction,
    required this.outcomeAction,
    required this.reasonLabel,
    required this.occurredOutcome,
    required this.didNotHappenOutcome,
    required this.endedEarlyOutcome,
    required this.safetyTerminatedOutcome,
    required this.disputedOutcome,
    required this.unverifiedOutcome,
    required this.audiencePublic,
    required this.audienceUnlisted,
    required this.audienceCommunityMembers,
    required this.audienceInviteOnly,
    required this.admissionOpen,
    required this.admissionApproval,
    required this.admissionInviteOnly,
    required this.noRequirements,
    required this.recapAction,
    required this.sharedExperienceTitle,
    required this.sharedExperienceSingleTitle,
    required this.sharedExperienceEndedEmpty,
    required this.organizerStatsLabel,
  });

  final String pageTitle;
  final String emptyTitle;
  final String retryAction;
  final String hostLabel;
  final String timeLabel;
  final String placeLabel;
  final String privatePlaceLabel;
  final String capacityLabel;
  final String policyLabel;
  final String requirementsLabel;
  final String revisionsLabel;
  final String joinAction;
  final String applyAction;
  final String acceptInvitationAction;
  final String watchAvailabilityAction;
  final String enterChatAction;
  final String readOnlyAction;
  final String hostConsoleTitle;
  final String applicationsTitle;
  final String applicationAnswersLabel;
  final String approveAction;
  final String rejectAction;
  final String inviteTitle;
  final String personaIdLabel;
  final String inviteAction;
  final String rosterTitle;
  final String removeAction;
  final String capacityAction;
  final String pauseAdmissionAction;
  final String resumeAdmissionAction;
  final String materialUpdateAction;
  final String cancelAction;
  final String startAction;
  final String outcomeAction;
  final String reasonLabel;
  final String occurredOutcome;
  final String didNotHappenOutcome;
  final String endedEarlyOutcome;
  final String safetyTerminatedOutcome;
  final String disputedOutcome;
  final String unverifiedOutcome;
  final String audiencePublic;
  final String audienceUnlisted;
  final String audienceCommunityMembers;
  final String audienceInviteOnly;
  final String admissionOpen;
  final String admissionApproval;
  final String admissionInviteOnly;
  final String noRequirements;
  final String recapAction;
  final String sharedExperienceTitle;
  final String sharedExperienceSingleTitle;
  final String sharedExperienceEndedEmpty;
  final String organizerStatsLabel;

  String primaryAction(GatheringPrimaryAction value) => switch (value) {
    GatheringPrimaryAction.join => joinAction,
    GatheringPrimaryAction.apply => applyAction,
    GatheringPrimaryAction.acceptInvitation => acceptInvitationAction,
    GatheringPrimaryAction.watchAvailability => watchAvailabilityAction,
    GatheringPrimaryAction.enterChat => enterChatAction,
    GatheringPrimaryAction.readOnly => readOnlyAction,
    GatheringPrimaryAction.noAction => readOnlyAction,
  };

  String audience(GatheringAudiencePolicy value) => switch (value) {
    GatheringAudiencePolicy.public => audiencePublic,
    GatheringAudiencePolicy.unlisted => audienceUnlisted,
    GatheringAudiencePolicy.communityMembers => audienceCommunityMembers,
    GatheringAudiencePolicy.inviteOnly => audienceInviteOnly,
  };

  String admission(GatheringAdmissionPolicy value) => switch (value) {
    GatheringAdmissionPolicy.open => admissionOpen,
    GatheringAdmissionPolicy.approval => admissionApproval,
    GatheringAdmissionPolicy.inviteOnly => admissionInviteOnly,
  };

  String outcome(GatheringOutcomeStatus value) => switch (value) {
    GatheringOutcomeStatus.occurred => occurredOutcome,
    GatheringOutcomeStatus.didNotHappen => didNotHappenOutcome,
    GatheringOutcomeStatus.endedEarly => endedEarlyOutcome,
    GatheringOutcomeStatus.safetyTerminated => safetyTerminatedOutcome,
    GatheringOutcomeStatus.disputed => disputedOutcome,
    GatheringOutcomeStatus.unverified => unverifiedOutcome,
  };
}
