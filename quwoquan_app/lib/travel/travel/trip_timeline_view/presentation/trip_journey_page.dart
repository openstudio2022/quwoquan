import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/travel/travel/trip_guide_assignment/application/trip_guide_assignment_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_timeline_view/application/trip_journey_query.dart';
import 'package:quwoquan_app/travel/travel/trip_moment/application/trip_moment_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_revision/application/trip_plan_revision_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_share_snapshot/application/trip_share_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_template/application/trip_template_coordinator.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_action_sheet.dart';
import 'package:quwoquan_app/core/widgets/app_modal_presenter.dart';
import 'package:quwoquan_app/core/widgets/app_request_feedback.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';
import 'package:quwoquan_app/ui/travel/widgets/trip_item_semantics.dart';
import 'package:quwoquan_app/travel/travel/trip_timeline_view/presentation/trip_journey_overview.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_revision/presentation/trip_plan_revision_flow.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:uuid/uuid.dart';

part 'trip_journey_page_revision_actions.dart';
part 'trip_journey_page_template_actions.dart';
part 'trip_journey_page_guide_assignment_actions.dart';

final class TripJourneyPage extends ConsumerStatefulWidget {
  const TripJourneyPage({
    super.key,
    required this.tripId,
    required this.onBack,
    required this.onOpenMap,
    required this.onOpenShare,
    this.onOpenPost,
  });

  final String tripId;
  final VoidCallback onBack;
  final VoidCallback onOpenMap;
  final ValueChanged<String> onOpenShare;
  final ValueChanged<String>? onOpenPost;

  @override
  ConsumerState<TripJourneyPage> createState() => _TripJourneyPageState();
}

final class _TripJourneyPageState extends ConsumerState<TripJourneyPage>
    with
        _TripJourneyPageRevisionActions,
        _TripJourneyPageTemplateActions,
        _TripJourneyPageGuideAssignmentActions {
  bool _creatingShare = false;
  bool _creatingMoment = false;
  String? _updatingMomentId;
  String? _transitioningGuideTaskKey;

  @override
  Widget build(BuildContext context) {
    final journey = ref.watch(tripJourneySnapshotProvider(widget.tripId));
    final activePersonaId =
        ref.watch(activePersonaContextProvider).asData?.value.personaId ?? '';
    final guideAssigneeLabels = ref.watch(
      tripGuideAssigneeLabelsProvider(widget.tripId),
    );
    return AppScaffold(
      navigationBar: AppNavigationBar(
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: widget.onBack,
        ),
        middle: const Text(TravelText.journeyTitle),
      ),
      child: SafeArea(
        child: journey.when(
          loading: AppRequestFeedback.page,
          data: (snapshot) => TripJourneyOverview(
            snapshot: snapshot,
            onRevisePlan:
                activePersonaId == snapshot.plan.organizerPersonaId &&
                    !_revisingPlan
                ? () => _composeRevision(snapshot)
                : null,
            transitionPlanLabel:
                activePersonaId == snapshot.plan.organizerPersonaId
                ? tripStatusActionLabel(snapshot.plan.status)
                : null,
            onTransitionPlan:
                activePersonaId == snapshot.plan.organizerPersonaId &&
                    !_transitioningPlan
                ? () => _confirmPlanTransition(snapshot.plan)
                : null,
            onAddMoment: _creatingMoment
                ? null
                : () => _composeTextMoment(snapshot),
            onManageMoment: _updatingMomentId == null
                ? (momentId) =>
                      _manageMoment(snapshot, momentId, activePersonaId)
                : null,
            onOpenMap: widget.onOpenMap,
            onOpenPost: widget.onOpenPost,
            onShare: _creatingShare ? null : () => _composeShare(snapshot),
            onSaveTemplate:
                activePersonaId == snapshot.plan.organizerPersonaId &&
                    !_creatingTemplate
                ? () => _composeTemplate(snapshot)
                : null,
            activePersonaId: activePersonaId,
            onAdvanceGuideTask: _transitioningGuideTaskKey == null
                ? _advanceGuideTask
                : null,
            onCreateGuideAssignment:
                activePersonaId == snapshot.plan.organizerPersonaId &&
                    _puttingGuideTaskKey == null
                ? () => _composeGuideAssignment(snapshot, activePersonaId)
                : null,
            onReassignGuideAssignment:
                activePersonaId == snapshot.plan.organizerPersonaId &&
                    _puttingGuideTaskKey == null
                ? (assignment) => _reassignGuideAssignment(
                    snapshot,
                    activePersonaId,
                    assignment,
                  )
                : null,
            guideAssigneeLabels:
                guideAssigneeLabels.asData?.value ?? const <String, String>{},
            guideAssigneeLabelsPending: guideAssigneeLabels.isLoading,
          ),
          error: (error, _) => AppPageErrorState(
            semantic: ensureRetryUiErrorSemantic(
              runtimeErrorSemantic(
                context,
                error: error,
                category: UiErrorCategory.pageLoad,
                scope: UiErrorScope.page,
                sourceRouteId: AppUiSurfaces.travelTimeline.routeId,
                sourceSurfaceId: AppUiSurfaces.travelTimeline.id,
              ),
            ),
            onRecovery: _recoverJourney,
          ),
        ),
      ),
    );
  }

  Future<UiRecoveryOutcome> _recoverJourney(UiErrorAction action) async {
    if (action.type != UiErrorActionType.retry &&
        action.type != UiErrorActionType.resubmit) {
      return UiRecoveryOutcome.cancelled;
    }
    try {
      ref.invalidate(tripJourneySnapshotProvider(widget.tripId));
      await ref.read(tripJourneySnapshotProvider(widget.tripId).future);
      return mounted
          ? UiRecoveryOutcome.recovered
          : UiRecoveryOutcome.superseded;
    } catch (_) {
      return mounted
          ? UiRecoveryOutcome.stillBlocked
          : UiRecoveryOutcome.superseded;
    }
  }

  Future<void> _advanceGuideTask(TripGuideAssignment assignment) async {
    final intent = ref
        .read(tripGuideAssignmentCoordinatorProvider)
        .prepareNext(assignment);
    if (intent == null) {
      return;
    }
    await _transitionGuideTask(intent);
  }

  Future<void> _transitionGuideTask(TripGuideTransitionIntent intent) async {
    if (_transitioningGuideTaskKey != null) {
      return;
    }
    setState(() => _transitioningGuideTaskKey = intent.command.taskKey);
    AppToast.show(context, TravelText.guideTransitioning);
    try {
      await ref.read(tripGuideAssignmentCoordinatorProvider).transition(intent);
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      AppToast.show(context, TravelText.guideTransitioned);
      ref.invalidate(tripJourneySnapshotProvider(widget.tripId));
    } catch (error) {
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      setState(() => _transitioningGuideTaskKey = null);
      final semantic = ensureRetryUiErrorSemantic(
        runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
          sourceRouteId: AppUiSurfaces.travelTimeline.routeId,
          sourceSurfaceId: AppUiSurfaces.travelTimeline.id,
          sourceOperationId: AppCloudOperationIds
              .travelTripGuideAssignmentTransitionTripGuideAssignment,
        ),
      );
      await AppActionErrorFeedback.show(
        context,
        semantic: semantic,
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _transitionGuideTask(intent);
          }
        },
      );
    } finally {
      if (mounted && _transitioningGuideTaskKey != null) {
        setState(() => _transitioningGuideTaskKey = null);
      }
    }
  }

  Future<void> _composeTextMoment(TripJourneySnapshot snapshot) async {
    final text = await _promptMomentText();
    if (!mounted || text == null) {
      return;
    }
    final target = await _selectMomentTarget(snapshot);
    if (!mounted || target == null) {
      return;
    }
    final visibility = target.target == null
        ? TripMomentVisibility.personal
        : await _selectMomentVisibility();
    if (!mounted || visibility == null) {
      return;
    }
    final intent = ref
        .read(tripMomentCoordinatorProvider)
        .prepareText(
          snapshot: snapshot,
          text: text,
          target: target.target,
          visibility: visibility,
        );
    await _createMoment(intent);
  }

  Future<String?> _promptMomentText() async {
    final controller = TextEditingController();
    try {
      final value = await showAppCupertinoDialog<String>(
        context: context,
        builder: (dialogContext) => CupertinoAlertDialog(
          title: const Text(TravelText.momentTextTitle),
          content: Padding(
            padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
            child: CupertinoTextField(
              controller: controller,
              autofocus: true,
              minLines: 2,
              maxLines: 5,
              placeholder: TravelText.momentTextHint,
              textInputAction: TextInputAction.done,
              onSubmitted: (text) =>
                  Navigator.of(dialogContext).pop(text.trim()),
            ),
          ),
          actions: <Widget>[
            CupertinoDialogAction(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text(FoundationText.cancel),
            ),
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () =>
                  Navigator.of(dialogContext).pop(controller.text.trim()),
              child: const Text(CommunityText.done),
            ),
          ],
        ),
      );
      final normalized = value?.trim() ?? '';
      return normalized.isEmpty ? null : normalized;
    } finally {
      controller.dispose();
    }
  }

  Future<_MomentTargetChoice?> _selectMomentTarget(
    TripJourneySnapshot snapshot,
  ) {
    return showAppActionSheet<_MomentTargetChoice>(
      context,
      title: TravelText.momentTargetTitle,
      message: TravelText.momentTargetMessage,
      sections: <AppActionSheetSection<_MomentTargetChoice>>[
        const AppActionSheetSection<_MomentTargetChoice>(
          items: <AppActionSheetItem<_MomentTargetChoice>>[
            AppActionSheetItem<_MomentTargetChoice>(
              value: _MomentTargetChoice(),
              label: TravelText.momentKeepPersonal,
              icon: CupertinoIcons.person,
            ),
          ],
        ),
        for (final day in snapshot.timeline.days)
          if (day.items.isNotEmpty)
            AppActionSheetSection<_MomentTargetChoice>(
              items: <AppActionSheetItem<_MomentTargetChoice>>[
                for (final item in day.items)
                  AppActionSheetItem<_MomentTargetChoice>(
                    value: _MomentTargetChoice(
                      target: TripMomentTarget(
                        dayIndex: day.dayIndex,
                        itemId: item.itemId,
                      ),
                    ),
                    label:
                        '${TravelText.dayPrefix}${day.dayIndex}${TravelText.daySuffix} · ${item.title}',
                    icon: CupertinoIcons.location,
                  ),
              ],
            ),
      ],
    );
  }

  Future<TripMomentVisibility?> _selectMomentVisibility() {
    return showAppActionSheet<TripMomentVisibility>(
      context,
      title: TravelText.momentVisibilityTitle,
      message: TravelText.momentVisibilityMessage,
      sections: const <AppActionSheetSection<TripMomentVisibility>>[
        AppActionSheetSection<TripMomentVisibility>(
          items: <AppActionSheetItem<TripMomentVisibility>>[
            AppActionSheetItem<TripMomentVisibility>(
              value: TripMomentVisibility.tripMembers,
              label: TravelText.momentTripMembers,
              icon: CupertinoIcons.person_2,
            ),
            AppActionSheetItem<TripMomentVisibility>(
              value: TripMomentVisibility.personal,
              label: TravelText.momentPersonal,
              icon: CupertinoIcons.person,
            ),
          ],
        ),
      ],
    );
  }

  Future<void> _createMoment(TripMomentCreateIntent intent) async {
    if (_creatingMoment) {
      return;
    }
    setState(() => _creatingMoment = true);
    AppToast.show(context, TravelText.momentSaving);
    try {
      await ref.read(tripMomentCoordinatorProvider).create(intent);
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      AppToast.show(context, TravelText.momentSaved);
      ref.invalidate(tripJourneySnapshotProvider(widget.tripId));
    } catch (error) {
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      setState(() => _creatingMoment = false);
      final semantic = ensureRetryUiErrorSemantic(
        runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
          sourceRouteId: AppUiSurfaces.travelTimeline.routeId,
          sourceSurfaceId: AppUiSurfaces.travelTimeline.id,
          sourceOperationId:
              AppCloudOperationIds.travelTripMomentCreateTripMoment,
        ),
      );
      await AppActionErrorFeedback.show(
        context,
        semantic: semantic,
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _createMoment(intent);
          }
        },
      );
    } finally {
      if (mounted && _creatingMoment) {
        setState(() => _creatingMoment = false);
      }
    }
  }

  Future<void> _manageMoment(
    TripJourneySnapshot snapshot,
    String momentId,
    String activePersonaId,
  ) async {
    if (_updatingMomentId != null) {
      return;
    }
    final matches = snapshot.moments.moments
        .where(
          (moment) =>
              moment.momentId == momentId &&
              moment.status == TripMomentStatus.active,
        )
        .toList(growable: false);
    if (matches.length != 1) {
      return;
    }
    final moment = matches.single;
    final mayManage =
        activePersonaId.isNotEmpty &&
        (activePersonaId == moment.attributionPersonaId ||
            activePersonaId == snapshot.plan.organizerPersonaId);
    if (!mayManage) {
      return;
    }
    final action = await showAppActionSheet<_MomentManageAction>(
      context,
      title: TravelText.momentManageTitle,
      message: TravelText.momentManageMessage,
      sections: const <AppActionSheetSection<_MomentManageAction>>[
        AppActionSheetSection<_MomentManageAction>(
          items: <AppActionSheetItem<_MomentManageAction>>[
            AppActionSheetItem<_MomentManageAction>(
              value: _MomentManageAction.move,
              label: TravelText.momentMove,
              icon: CupertinoIcons.arrow_right_arrow_left,
            ),
            AppActionSheetItem<_MomentManageAction>(
              value: _MomentManageAction.delete,
              label: TravelText.momentDelete,
              icon: CupertinoIcons.delete,
              isDestructive: true,
            ),
          ],
        ),
      ],
    );
    if (!mounted || action == null) {
      return;
    }
    if (action == _MomentManageAction.delete) {
      if (!await _confirmMomentDelete() || !mounted) {
        return;
      }
      final intent = ref
          .read(tripMomentCoordinatorProvider)
          .prepareDelete(
            snapshot: snapshot,
            momentId: momentId,
            reason: TravelText.momentDeleteReason,
          );
      await _deleteMoment(intent);
      return;
    }
    final target = await _selectAssignedMomentTarget(snapshot);
    if (!mounted || target == null) {
      return;
    }
    final visibility = await _selectMomentVisibility();
    if (!mounted || visibility == null) {
      return;
    }
    final intent = ref
        .read(tripMomentCoordinatorProvider)
        .prepareAssignment(
          snapshot: snapshot,
          momentId: momentId,
          target: target,
          visibility: visibility,
        );
    await _assignMoment(intent);
  }

  Future<TripMomentTarget?> _selectAssignedMomentTarget(
    TripJourneySnapshot snapshot,
  ) {
    return showAppActionSheet<TripMomentTarget>(
      context,
      title: TravelText.momentTargetTitle,
      message: TravelText.momentTargetMessage,
      sections: <AppActionSheetSection<TripMomentTarget>>[
        for (final day in snapshot.timeline.days)
          if (day.items.isNotEmpty)
            AppActionSheetSection<TripMomentTarget>(
              items: <AppActionSheetItem<TripMomentTarget>>[
                for (final item in day.items)
                  AppActionSheetItem<TripMomentTarget>(
                    value: TripMomentTarget(
                      dayIndex: day.dayIndex,
                      itemId: item.itemId,
                    ),
                    label:
                        '${TravelText.dayPrefix}${day.dayIndex}${TravelText.daySuffix} · ${item.title}',
                    icon: CupertinoIcons.location,
                  ),
              ],
            ),
      ],
    );
  }

  Future<bool> _confirmMomentDelete() async {
    final confirmed = await showAppCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text(TravelText.momentDeleteConfirmTitle),
        content: const Text(TravelText.momentDeleteConfirmMessage),
        actions: <Widget>[
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text(FoundationText.cancel),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text(TravelText.momentDelete),
          ),
        ],
      ),
    );
    return confirmed ?? false;
  }

  Future<void> _assignMoment(TripMomentAssignIntent intent) async {
    final momentId = intent.command.momentId;
    if (_updatingMomentId != null) {
      return;
    }
    setState(() => _updatingMomentId = momentId);
    AppToast.show(context, TravelText.momentMoving);
    try {
      await ref.read(tripMomentCoordinatorProvider).assign(intent);
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      AppToast.show(context, TravelText.momentMoved);
      ref.invalidate(tripJourneySnapshotProvider(widget.tripId));
    } catch (error) {
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      setState(() => _updatingMomentId = null);
      await _showMomentMutationError(
        error,
        operationId: AppCloudOperationIds.travelTripMomentAssignTripMoment,
        retry: () => _assignMoment(intent),
      );
    } finally {
      if (mounted && _updatingMomentId == momentId) {
        setState(() => _updatingMomentId = null);
      }
    }
  }

  Future<void> _deleteMoment(TripMomentDeleteIntent intent) async {
    final momentId = intent.command.momentId;
    if (_updatingMomentId != null) {
      return;
    }
    setState(() => _updatingMomentId = momentId);
    AppToast.show(context, TravelText.momentDeleting);
    try {
      await ref.read(tripMomentCoordinatorProvider).delete(intent);
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      AppToast.show(context, TravelText.momentDeleted);
      ref.invalidate(tripJourneySnapshotProvider(widget.tripId));
    } catch (error) {
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      setState(() => _updatingMomentId = null);
      await _showMomentMutationError(
        error,
        operationId: AppCloudOperationIds.travelTripMomentDeleteTripMoment,
        retry: () => _deleteMoment(intent),
      );
    } finally {
      if (mounted && _updatingMomentId == momentId) {
        setState(() => _updatingMomentId = null);
      }
    }
  }

  Future<void> _showMomentMutationError(
    Object error, {
    required String operationId,
    required Future<void> Function() retry,
  }) async {
    final semantic = ensureRetryUiErrorSemantic(
      runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
        sourceRouteId: AppUiSurfaces.travelTimeline.routeId,
        sourceSurfaceId: AppUiSurfaces.travelTimeline.id,
        sourceOperationId: operationId,
      ),
    );
    await AppActionErrorFeedback.show(
      context,
      semantic: semantic,
      onAction: (action) async {
        if (action.type == UiErrorActionType.retry ||
            action.type == UiErrorActionType.resubmit) {
          await retry();
        }
      },
    );
  }

  Future<void> _composeShare(TripJourneySnapshot snapshot) async {
    final scope = await showAppActionSheet<TripShareSelection>(
      context,
      title: TravelText.shareScopeTitle,
      message: TravelText.shareScopeMessage,
      sections: <AppActionSheetSection<TripShareSelection>>[
        AppActionSheetSection<TripShareSelection>(
          items: <AppActionSheetItem<TripShareSelection>>[
            const AppActionSheetItem<TripShareSelection>(
              value: TripShareSelection.full(),
              label: TravelText.shareWholeJourney,
              icon: CupertinoIcons.square_stack_3d_up,
            ),
            const AppActionSheetItem<TripShareSelection>(
              value: TripShareSelection.route(),
              label: TravelText.shareRouteOnly,
              icon: CupertinoIcons.map,
            ),
            for (final day in snapshot.timeline.days)
              AppActionSheetItem<TripShareSelection>(
                value: TripShareSelection.day(dayIndex: day.dayIndex),
                label:
                    '${TravelText.dayPrefix}${day.dayIndex}${TravelText.daySuffix} · ${TravelText.shareDay}',
                icon: CupertinoIcons.calendar,
              ),
          ],
        ),
      ],
    );
    if (!mounted || scope == null) {
      return;
    }
    final visibility = await showAppActionSheet<TripShareSnapshotVisibility>(
      context,
      title: TravelText.shareVisibilityTitle,
      message: TravelText.shareVisibilityMessage,
      sections: const <AppActionSheetSection<TripShareSnapshotVisibility>>[
        AppActionSheetSection<TripShareSnapshotVisibility>(
          items: <AppActionSheetItem<TripShareSnapshotVisibility>>[
            AppActionSheetItem<TripShareSnapshotVisibility>(
              value: TripShareSnapshotVisibility.public,
              label: TravelText.sharePublic,
              icon: CupertinoIcons.globe,
            ),
            AppActionSheetItem<TripShareSnapshotVisibility>(
              value: TripShareSnapshotVisibility.tripMembers,
              label: TravelText.shareTripMembers,
              icon: CupertinoIcons.person_2,
            ),
          ],
        ),
      ],
    );
    if (!mounted || visibility == null) {
      return;
    }
    await _createShare(snapshot, scope.withVisibility(visibility));
  }

  Future<void> _createShare(
    TripJourneySnapshot snapshot,
    TripShareSelection selection,
  ) async {
    if (_creatingShare) {
      return;
    }
    setState(() => _creatingShare = true);
    AppToast.show(context, TravelText.shareCreating);
    try {
      final result = await ref
          .read(tripShareCoordinatorProvider)
          .create(snapshot, selection);
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      widget.onOpenShare(result.id);
    } catch (error) {
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      setState(() => _creatingShare = false);
      final semantic = ensureRetryUiErrorSemantic(
        runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
          sourceRouteId: AppUiSurfaces.travelTimeline.routeId,
          sourceSurfaceId: AppUiSurfaces.travelTimeline.id,
          sourceOperationId: AppCloudOperationIds
              .travelTripShareSnapshotCreateTripShareSnapshot,
        ),
      );
      await AppActionErrorFeedback.show(
        context,
        semantic: semantic,
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _createShare(snapshot, selection);
          }
        },
      );
    } finally {
      if (mounted && _creatingShare) {
        setState(() => _creatingShare = false);
      }
    }
  }
}

final class _MomentTargetChoice {
  const _MomentTargetChoice({this.target});

  final TripMomentTarget? target;
}

enum _MomentManageAction { move, delete }
