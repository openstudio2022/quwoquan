import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/runtime/di/navigation/create_entry_navigation_arguments.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show journeyEventTrackerProvider;
import 'package:quwoquan_app/runtime/di/gathering_dependencies.dart';
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart'
    show exceptionTelemetryPortProvider;
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart'
    show UiErrorTone;
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
  recapAction: GatheringText.detailRecapAction,
  sharedExperienceTitle: GatheringText.detailSharedExperienceTitle,
  sharedExperienceSingleTitle: GatheringText.detailSharedExperienceSingleTitle,
  sharedExperienceEndedEmpty: GatheringText.detailSharedExperienceEndedEmpty,
  organizerStatsLabel: GatheringText.detailOrganizerStatsLabel,
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
      final initialValueAsync = ref.watch(
        gatheringCreateInitialValueProvider((
          activePersonaId: activePersonaId,
          navigationRequest: navigationRequest,
        )),
      );
      return initialValueAsync.when(
        loading: () => AppScaffold(
          navigationBar: const AppNavigationBar(
            middle: Text(GatheringText.createPageTitle),
          ),
          body: AppRequestFeedback.page(),
        ),
        error: (error, _) => RouteUnavailableState(
          error: error,
          surface: AppUiSurfaces.gatheringCreate,
          pageTitle: GatheringText.createPageTitle,
        ),
        data: (initialValue) {
          final host = initialValue.host;
          if (host.authorityEvidenceRef.trim().isEmpty ||
              host.authorityVersion <= 0 ||
              (host.subjectKind == GatheringHostSubjectKind.persona &&
                  host.subjectId.trim() != activePersonaId)) {
            return RouteUnavailableState(
              error: _routeFailure(
                semanticReason: 'gathering_host_authority_invalid',
                port: 'GatheringHostAuthorityComposer',
              ),
              surface: AppUiSurfaces.gatheringCreate,
              pageTitle: GatheringText.createPageTitle,
            );
          }
          ref.watch(gatheringCommandWriterProvider);
          return GatheringCreatePage(
            copy: _productionCreateCopy,
            initialValue: initialValue,
            onPublished: (result) => _completeDuoInvitationThenOpen(
              context,
              ref,
              result,
              navigationRequest,
            ),
          );
        },
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
        onPublishRecap: (gatheringId, gatheringTitle) {
          context.push<void>(
            AppRoutePaths.create(),
            extra: CreateEntryArguments(
              gatheringId: gatheringId,
              gatheringTitle: gatheringTitle,
            ),
          );
        },
        onOpenRecapPost: (postId) {
          context.push<void>(AppRoutePaths.workBrowser(workId: postId));
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

/// 双人邀约（1对1）：发布成功后自动向受邀者发出披露安全邀请，再进入
/// 成行页面；邀请失败不阻断发布结果（详情 Host 控制台可重发），只提示。
void _completeDuoInvitationThenOpen(
  BuildContext context,
  WidgetRef ref,
  GatheringCommandResult result,
  GatheringCreateNavigationRequest? navigation,
) {
  // 漏斗辅证埋点：发布成功事实（分子分母真相源仍是域事实投影）。
  unawaited(
    ref
        .read(journeyEventTrackerProvider)
        .trackAction(
          journey: 'gathering_flywheel',
          action: 'gathering_published',
          pageName: 'gathering_create',
          targetType: 'gathering',
          targetKey: result.gatheringId,
        ),
  );
  final inviteePersonaId = navigation?.inviteePersonaId.trim() ?? '';
  if (inviteePersonaId.isEmpty) {
    _openPublishedGathering(context, result);
    return;
  }
  final writer = ref.read(gatheringCommandWriterProvider);
  unawaited(() async {
    try {
      await writer.invite(
        GatheringInviteInput(
          idempotencyKey: 'duo-invite:${result.gatheringId}:$inviteePersonaId',
          gatheringId: result.gatheringId,
          participantPersonaId: inviteePersonaId,
          seatHoldUntil: DateTime.now().toUtc().add(const Duration(hours: 48)),
          expectedGatheringVersion: result.aggregateVersion,
          expectedParticipationVersion: 0,
        ),
      );
    } catch (error, stackTrace) {
      unawaited(
        ref
            .read(exceptionTelemetryPortProvider)
            .recordHandledException(
              source: 'circle.gathering_create.duo_auto_invite',
              error: error,
              stackTrace: stackTrace,
            ),
      );
      if (context.mounted) {
        AppToast.show(
          context,
          GatheringText.duoInviteFailedToast,
          tone: UiErrorTone.caution,
        );
      }
    }
  }());
  _openPublishedGathering(context, result);
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
