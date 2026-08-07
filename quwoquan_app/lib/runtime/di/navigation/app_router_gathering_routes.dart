import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/gathering_board_dependencies.dart';
import 'package:quwoquan_app/runtime/di/gathering_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/native_back_navigation.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/gathering_board_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_create_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_detail_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_page_copy.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/gathering_create_navigation_request.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// 活动创建页只能消费由批准的 Host authority composer 产出的完整初值。
///
/// 默认 fail-fast，防止 shell 从 active persona 自造 authorityEvidenceRef/version；
/// cloud handoff 完成后由 production composition 覆盖此 provider。
typedef GatheringCreateBootstrapRequest = ({
  String activePersonaId,
  GatheringCreateNavigationRequest? navigationRequest,
});

final gatheringCreateInitialValueProvider =
    Provider.family<
      GatheringCreateInitialValue,
      GatheringCreateBootstrapRequest
    >(
      (ref, request) => throw _gatheringRouteFailure(
        semanticReason: 'gathering_host_authority_adapter_unavailable',
        port: 'GatheringHostAuthorityComposer',
      ),
      // 装配缺口是 permanent/unavailable 的组合边界失败，不是瞬时故障。
      // Riverpod 默认会对非 Error 抛出重试 10 次（指数退避到 6.4s），这里必须关掉，
      // 否则路由每次进入都会空转重建并留下计时器。
      retry: (_, _) => null,
    );

const GatheringCreatePageCopy _gatheringCreateProductionCopy =
    GatheringCreatePageCopy(
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

const GatheringDetailPageCopy _gatheringDetailProductionCopy =
    GatheringDetailPageCopy(
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

List<GoRoute> gatheringRoutes() => <GoRoute>[
  GoRoute(
    path: AppRoutePaths.gatheringCreate,
    pageBuilder: (context, state) => appRoutePage<void>(
      state: state,
      kind: AppRoutePageKind.fullscreenDialog,
      fullscreenDialog: true,
      child: GatheringCreateRouteHost(
        navigationRequest: state.extra is GatheringCreateNavigationRequest
            ? state.extra! as GatheringCreateNavigationRequest
            : null,
      ),
    ),
  ),
  GoRoute(
    path: AppRoutePaths.gatheringDetailPathTemplate.replaceAll('{id}', ':id'),
    pageBuilder: (context, state) => appRoutePage<void>(
      state: state,
      child: GatheringDetailRouteHost(
        gatheringId: state.pathParameters['id'] ?? '',
      ),
    ),
  ),
];

GoRoute gatheringBoardRoute() {
  return GoRoute(
    path: AppRoutePaths.gatheringBoardSegment,
    pageBuilder: (context, state) {
      final id = state.pathParameters['id'] ?? '';
      return appRoutePage<void>(
        state: state,
        child: GatheringBoardRouteHost(conversationId: id),
      );
    },
  );
}

/// Gathering create composition boundary.
///
/// The route reads identity from AuthSession, but the Host authority and the
/// complete form seed must come from the approved composition provider.
class GatheringCreateRouteHost extends ConsumerWidget {
  const GatheringCreateRouteHost({super.key, this.navigationRequest});

  final GatheringCreateNavigationRequest? navigationRequest;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    try {
      final session = ref.watch(authSessionControllerProvider);
      final activePersonaId = session.activePersonaId.trim();
      if (!session.isAuthenticated || activePersonaId.isEmpty) {
        throw _gatheringRouteFailure(
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
        throw _gatheringRouteFailure(
          semanticReason: 'gathering_host_authority_invalid',
          port: 'GatheringHostAuthorityComposer',
        );
      }
      // Force command construction before exposing a writable form. A missing
      // generated adapter therefore fails on the route boundary, not submit.
      ref.watch(gatheringCommandWriterProvider);
      return GatheringCreatePage(
        copy: _gatheringCreateProductionCopy,
        initialValue: initialValue,
        onPublished: (result) => _openPublishedGathering(context, result),
      );
    } catch (error) {
      return GatheringRouteUnavailableState(
        error: error,
        surface: AppUiSurfaces.gatheringCreate,
        pageTitle: GatheringText.createPageTitle,
      );
    }
  }
}

class GatheringDetailRouteHost extends ConsumerWidget {
  const GatheringDetailRouteHost({super.key, required this.gatheringId});

  final String gatheringId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    try {
      if (gatheringId.trim().isEmpty) {
        throw _gatheringRouteFailure(
          semanticReason: 'gathering_id_missing',
          port: 'GatheringQueryReader',
        );
      }
      ref.watch(gatheringQueryReaderProvider);
      return GatheringDetailPage(
        gatheringId: gatheringId,
        copy: _gatheringDetailProductionCopy,
        onEnterChat: (conversationId) {
          context.push<void>(AppRoutePaths.chatDetail(id: conversationId));
        },
      );
    } catch (error) {
      return GatheringRouteUnavailableState(
        error: error,
        surface: AppUiSurfaces.gatheringDetail,
        pageTitle: GatheringText.detailPageTitle,
      );
    }
  }
}

class GatheringBoardRouteHost extends ConsumerWidget {
  const GatheringBoardRouteHost({super.key, required this.conversationId});

  final String conversationId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    try {
      if (conversationId.trim().isEmpty) {
        throw _gatheringRouteFailure(
          semanticReason: 'gathering_board_conversation_id_missing',
          port: 'GatheringBoardQuery',
        );
      }
      final query = ref.watch(gatheringBoardQueryProvider);
      Future<void> openGathering(GatheringBoardNavigationTarget target) {
        return context.push<void>(
          AppRoutePaths.gatheringDetail(id: target.gatheringId),
        );
      }

      return GatheringBoardPage(
        conversationId: conversationId,
        query: query,
        onBack: () {
          if (context.canPop()) {
            context.pop();
          } else {
            context.go(AppRoutePaths.chatDetail(id: conversationId));
          }
        },
        navigation: GatheringBoardNavigationCallbacks(
          openAnnouncement: (target) => context.push<void>(
            AppRoutePaths.chatAnnouncement(id: target.conversationId),
          ),
          openPlan: openGathering,
          openMap: openGathering,
          openCalendar: openGathering,
          openMembers: (target) => context.push<void>(
            AppRoutePaths.chatManage(id: target.conversationId),
          ),
        ),
      );
    } catch (error) {
      return GatheringRouteUnavailableState(
        error: error,
        surface: AppUiSurfaces.gatheringBoard,
        pageTitle: ChatText.groupCapabilityActivity,
      );
    }
  }
}

class GatheringRouteUnavailableState extends StatelessWidget {
  const GatheringRouteUnavailableState({
    super.key,
    required this.error,
    required this.surface,
    required this.pageTitle,
  });

  final Object error;
  final AppUiSurface surface;
  final String pageTitle;

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      navigationBar: CupertinoNavigationBar(middle: Text(pageTitle)),
      child: SafeArea(
        child: KeyedSubtree(
          key: ValueKey<String>('${surface.id}-route-unavailable'),
          child: AppPageErrorState(
            semantic: runtimeErrorSemantic(
              context,
              error: error,
              category: UiErrorCategory.pageLoad,
              scope: UiErrorScope.page,
              sourceRouteId: surface.routeId,
              sourceSurfaceId: surface.id,
            ),
          ),
        ),
      ),
    );
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

RuntimeFailure _gatheringRouteFailure({
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
      functionModule: 'app_router_gathering_routes',
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
