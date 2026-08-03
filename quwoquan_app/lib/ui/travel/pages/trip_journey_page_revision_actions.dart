part of 'trip_journey_page.dart';

mixin _TripJourneyPageRevisionActions on ConsumerState<TripJourneyPage> {
  bool _revisingPlan = false;
  bool _transitioningPlan = false;

  Future<void> _composeRevision(TripJourneySnapshot snapshot) async {
    if (_revisingPlan) {
      return;
    }
    final intent = await composeTripPlanRevision(
      context,
      plan: snapshot.plan,
      coordinator: ref.read(tripPlanRevisionCoordinatorProvider),
      itemIdFactory: () => 'item-${const Uuid().v4()}',
    );
    if (!mounted || intent == null) {
      return;
    }
    await _submitRevision(intent);
  }

  Future<void> _submitRevision(TripPlanRevisionIntent intent) async {
    if (_revisingPlan) {
      return;
    }
    setState(() => _revisingPlan = true);
    AppToast.show(context, TravelText.planRevising);
    try {
      await ref.read(tripPlanRevisionCoordinatorProvider).revise(intent);
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      AppToast.show(context, TravelText.planRevised);
      ref.invalidate(tripJourneySnapshotProvider(widget.tripId));
    } catch (error) {
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      setState(() => _revisingPlan = false);
      await AppActionErrorFeedback.show(
        context,
        semantic: ensureRetryUiErrorSemantic(
          runtimeErrorSemantic(
            context,
            error: error,
            category: UiErrorCategory.submit,
            scope: UiErrorScope.global,
            sourceRouteId: AppUiSurfaces.travelTimeline.routeId,
            sourceSurfaceId: AppUiSurfaces.travelTimeline.id,
            sourceOperationId:
                AppCloudOperationIds.travelTripPlanReviseTripPlan,
          ),
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _submitRevision(intent);
          }
        },
      );
    } finally {
      if (mounted && _revisingPlan) {
        setState(() => _revisingPlan = false);
      }
    }
  }

  Future<void> _confirmPlanTransition(TripPlanSlice plan) async {
    if (_transitioningPlan) {
      return;
    }
    final target = nextTripPlanStatus(plan.status);
    final confirmed = await showAppActionSheet<TripPlanStatus>(
      context,
      title: tripStatusActionLabel(plan.status),
      message: TravelText.transitionPlanMessage,
      sections: <AppActionSheetSection<TripPlanStatus>>[
        AppActionSheetSection<TripPlanStatus>(
          items: <AppActionSheetItem<TripPlanStatus>>[
            AppActionSheetItem<TripPlanStatus>(
              value: target,
              label: tripStatusActionLabel(plan.status),
              icon: CupertinoIcons.flag,
            ),
          ],
        ),
      ],
    );
    if (!mounted || confirmed == null) {
      return;
    }
    final intent = ref
        .read(tripPlanRevisionCoordinatorProvider)
        .prepareTransition(plan: plan, targetStatus: confirmed);
    await _submitPlanTransition(intent);
  }

  Future<void> _submitPlanTransition(TripPlanTransitionIntent intent) async {
    if (_transitioningPlan) {
      return;
    }
    setState(() => _transitioningPlan = true);
    AppToast.show(context, TravelText.planTransitioning);
    try {
      await ref.read(tripPlanRevisionCoordinatorProvider).transition(intent);
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      AppToast.show(context, TravelText.planTransitioned);
      ref.invalidate(tripJourneySnapshotProvider(widget.tripId));
    } catch (error) {
      if (!mounted) {
        return;
      }
      AppToast.dismiss();
      setState(() => _transitioningPlan = false);
      await AppActionErrorFeedback.show(
        context,
        semantic: ensureRetryUiErrorSemantic(
          runtimeErrorSemantic(
            context,
            error: error,
            category: UiErrorCategory.submit,
            scope: UiErrorScope.global,
            sourceRouteId: AppUiSurfaces.travelTimeline.routeId,
            sourceSurfaceId: AppUiSurfaces.travelTimeline.id,
            sourceOperationId:
                AppCloudOperationIds.travelTripPlanTransitionTripPlan,
          ),
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _submitPlanTransition(intent);
          }
        },
      );
    } finally {
      if (mounted && _transitioningPlan) {
        setState(() => _transitioningPlan = false);
      }
    }
  }
}
