import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/gathering_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/route_unavailable_state.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_create_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_detail_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_page_copy.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/gathering_create_navigation_request.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

const GatheringCreatePageCopy _productionCreateCopy = GatheringCreatePageCopy(
  pageTitle: GatheringText.createPageTitle,
  purposeSection: GatheringText.createPurposeSection,
  titleLabel: GatheringText.createTitleLabel,
  titlePlaceholder: GatheringText.createTitlePlaceholder,
  summaryLabel: GatheringText.createSummaryLabel,
  summaryPlaceholder: GatheringText.createSummaryPlaceholder,
  sourceReferencesLabel: GatheringText.createSourceReferencesLabel,
  scheduleSection: GatheringText.createScheduleSection,
  timezoneLabel: GatheringText.createTimezoneLabel,
  startAtLabel: GatheringText.createStartAtLabel,
  endAtLabel: GatheringText.createEndAtLabel,
  admissionClosesAtLabel: GatheringText.createAdmissionClosesAtLabel,
  dateTimePlaceholder: GatheringText.createDateTimePlaceholder,
  placeSection: GatheringText.createPlaceSection,
  placeModeLabel: GatheringText.createPlaceModeLabel,
  placeModePhysical: GatheringText.createPlaceModePhysical,
  placeModeOnline: GatheringText.createPlaceModeOnline,
  placeModeHybrid: GatheringText.createPlaceModeHybrid,
  coarsePlaceLabel: GatheringText.createCoarsePlaceLabel,
  exactMeetingPointLabel: GatheringText.createExactMeetingPointLabel,
  onlineLocationLabel: GatheringText.createOnlineLocationLabel,
  policySection: GatheringText.createPolicySection,
  audienceLabel: GatheringText.createAudienceLabel,
  audiencePublic: GatheringText.audiencePublic,
  audienceUnlisted: GatheringText.audienceUnlisted,
  audienceCommunityMembers: GatheringText.audienceCommunityMembers,
  audienceInviteOnly: GatheringText.audienceInviteOnly,
  admissionLabel: GatheringText.createAdmissionLabel,
  admissionOpen: GatheringText.admissionOpen,
  admissionApproval: GatheringText.admissionApproval,
  admissionInviteOnly: GatheringText.admissionInviteOnly,
  capacityLabel: GatheringText.createCapacityLabel,
  timeDisclosureLabel: GatheringText.createTimeDisclosureLabel,
  placeDisclosureLabel: GatheringText.createPlaceDisclosureLabel,
  rosterDisclosureLabel: GatheringText.createRosterDisclosureLabel,
  disclosureExact: GatheringText.disclosureExact,
  disclosureDateOnly: GatheringText.disclosureDateOnly,
  disclosureCoarse: GatheringText.disclosureCoarse,
  disclosureAfterJoin: GatheringText.disclosureAfterJoin,
  rosterCountOnly: GatheringText.rosterCountOnly,
  rosterJoinedMembers: GatheringText.rosterJoinedMembers,
  rosterPublicOptIn: GatheringText.rosterPublicOptIn,
  riskControlPolicyLabel: GatheringText.createRiskControlPolicyLabel,
  hostSection: GatheringText.createHostSection,
  hostKindLabel: GatheringText.createHostKindLabel,
  hostPersona: GatheringText.createHostPersona,
  hostEntity: GatheringText.createHostEntity,
  hostCircle: GatheringText.createHostCircle,
  hostSubjectIdLabel: GatheringText.createHostSubjectIdLabel,
  authorityEvidenceLabel: GatheringText.createAuthorityEvidenceLabel,
  authorityVersionLabel: GatheringText.createAuthorityVersionLabel,
  creatorParticipatesLabel: GatheringText.createCreatorParticipatesLabel,
  submitAction: GatheringText.createSubmitAction,
  retryAction: GatheringText.retryAction,
  invalidFormMessage: GatheringText.createInvalidFormMessage,
  draftStepLabel: GatheringText.createDraftStepLabel,
  roomStepLabel: GatheringText.createRoomStepLabel,
  publishStepLabel: GatheringText.createPublishStepLabel,
  completedStepLabel: GatheringText.createCompletedStepLabel,
);

const GatheringDetailPageCopy _productionDetailCopy = GatheringDetailPageCopy(
  pageTitle: GatheringText.detailPageTitle,
  emptyTitle: GatheringText.detailEmptyTitle,
  retryAction: GatheringText.retryAction,
  hostLabel: GatheringText.detailHostLabel,
  timeLabel: GatheringText.detailTimeLabel,
  placeLabel: GatheringText.detailPlaceLabel,
  privatePlaceLabel: GatheringText.detailPrivatePlaceLabel,
  capacityLabel: GatheringText.detailCapacityLabel,
  policyLabel: GatheringText.detailPolicyLabel,
  requirementsLabel: GatheringText.detailRequirementsLabel,
  revisionsLabel: GatheringText.detailRevisionsLabel,
  joinAction: GatheringText.detailJoinAction,
  applyAction: GatheringText.detailApplyAction,
  acceptInvitationAction: GatheringText.detailAcceptInvitationAction,
  watchAvailabilityAction: GatheringText.detailWatchAvailabilityAction,
  enterChatAction: GatheringText.detailEnterChatAction,
  readOnlyAction: GatheringText.detailReadOnlyAction,
  hostConsoleTitle: GatheringText.detailHostConsoleTitle,
  applicationsTitle: GatheringText.detailApplicationsTitle,
  applicationAnswersLabel: GatheringText.detailApplicationAnswersLabel,
  approveAction: GatheringText.detailApproveAction,
  rejectAction: GatheringText.detailRejectAction,
  inviteTitle: GatheringText.detailInviteTitle,
  personaIdLabel: GatheringText.detailPersonaIdLabel,
  inviteAction: GatheringText.detailInviteAction,
  rosterTitle: GatheringText.detailRosterTitle,
  removeAction: GatheringText.detailRemoveAction,
  capacityAction: GatheringText.detailCapacityAction,
  pauseAdmissionAction: GatheringText.detailPauseAdmissionAction,
  resumeAdmissionAction: GatheringText.detailResumeAdmissionAction,
  materialUpdateAction: GatheringText.detailMaterialUpdateAction,
  cancelAction: GatheringText.detailCancelAction,
  startAction: GatheringText.detailStartAction,
  outcomeAction: GatheringText.detailOutcomeAction,
  reasonLabel: GatheringText.detailReasonLabel,
  occurredOutcome: GatheringText.detailOccurredOutcome,
  didNotHappenOutcome: GatheringText.detailDidNotHappenOutcome,
  endedEarlyOutcome: GatheringText.detailEndedEarlyOutcome,
  safetyTerminatedOutcome: GatheringText.detailSafetyTerminatedOutcome,
  disputedOutcome: GatheringText.detailDisputedOutcome,
  unverifiedOutcome: GatheringText.detailUnverifiedOutcome,
  audiencePublic: GatheringText.audiencePublic,
  audienceUnlisted: GatheringText.audienceUnlisted,
  audienceCommunityMembers: GatheringText.audienceCommunityMembers,
  audienceInviteOnly: GatheringText.audienceInviteOnly,
  admissionOpen: GatheringText.admissionOpen,
  admissionApproval: GatheringText.admissionApproval,
  admissionInviteOnly: GatheringText.admissionInviteOnly,
  noRequirements: GatheringText.detailNoRequirements,
);

/// Circle Gathering create composition host.
class GatheringCreatePageRouteHost extends ConsumerWidget {
  const GatheringCreatePageRouteHost({super.key, this.navigationRequest});

  final GatheringCreateNavigationRequest? navigationRequest;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    try {
      final session = ref.watch(authSessionControllerProvider);
      final activePersonaId = session.activePersonaId.trim();
      if (!session.isAuthenticated || activePersonaId.isEmpty) {
        throw _routeFailure(
          semanticReason: 'gathering_create_identity_unavailable',
          port: 'AuthSession.activePersonaId',
        );
      }
      final initialValue = ref.watch(
        gatheringCreateInitialValueProvider((
          activePersonaId: activePersonaId,
          navigationRequest: navigationRequest,
        )),
      );
      final host = initialValue.host;
      if (host.authorityEvidenceRef.trim().isEmpty ||
          host.authorityVersion <= 0 ||
          (host.subjectKind == GatheringHostSubjectKind.persona &&
              host.subjectId.trim() != activePersonaId)) {
        throw _routeFailure(
          semanticReason: 'gathering_host_authority_invalid',
          port: 'GatheringHostAuthorityComposer',
        );
      }
      ref.watch(gatheringCommandWriterProvider);
      return GatheringCreatePage(
        copy: _productionCreateCopy,
        initialValue: initialValue,
        onPublished: (result) => _openPublishedGathering(context, result),
      );
    } catch (error) {
      return RouteUnavailableState(
        error: error,
        surface: AppUiSurfaces.gatheringCreate,
        pageTitle: GatheringText.createPageTitle,
      );
    }
  }
}

/// Circle Gathering detail composition host.
class GatheringDetailPageRouteHost extends ConsumerWidget {
  const GatheringDetailPageRouteHost({super.key, required this.gatheringId});

  final String gatheringId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    try {
      if (gatheringId.trim().isEmpty) {
        throw _routeFailure(
          semanticReason: 'gathering_id_missing',
          port: 'GatheringQueryReader',
        );
      }
      ref.watch(gatheringQueryReaderProvider);
      return GatheringDetailPage(
        gatheringId: gatheringId,
        copy: _productionDetailCopy,
        onEnterChat: (conversationId) {
          context.push<void>(AppRoutePaths.chatDetail(id: conversationId));
        },
      );
    } catch (error) {
      return RouteUnavailableState(
        error: error,
        surface: AppUiSurfaces.gatheringDetail,
        pageTitle: GatheringText.detailPageTitle,
      );
    }
  }
}

void _openPublishedGathering(
  BuildContext context,
  GatheringCommandResult result,
) {
  final conversationId = result.conversationId?.trim() ?? '';
  if (result.roomBindingStatus == GatheringRoomBindingStatus.ready &&
      conversationId.isNotEmpty) {
    context.go(AppRoutePaths.chatDetail(id: conversationId));
    return;
  }
  context.go(AppRoutePaths.gatheringDetail(id: result.gatheringId));
}

RuntimeFailure _routeFailure({
  required String semanticReason,
  required String port,
}) {
  return RuntimeFailure(
    code: RuntimeFailureCodes.appSystemUnknownError,
    semanticReason: semanticReason,
    origin: RuntimeFailureOrigin.environment,
    kind: RuntimeFailureKind.unavailable,
    nature: RuntimeFailureNature.permanent,
    location: const RuntimeFailureLocation(
      businessObject: 'circle.gathering',
      functionModule: 'gathering_route_hosts',
    ),
    context: RuntimeFailureContext(
      attributes: <RuntimeContextAttribute>[
        RuntimeContextAttribute(key: 'port', value: port),
      ],
    ),
    recovery: const RuntimeRecoveryDirective(
      action: 'surface',
      disruptionLevel: 'fullPage',
    ),
  );
}
