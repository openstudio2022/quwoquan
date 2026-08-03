part of 'app_router.dart';

List<GoRoute> _travelRoutes() => <GoRoute>[
  GoRoute(
    path: AppRoutePaths.travelTrips,
    pageBuilder: (context, state) => appRoutePage<void>(
      state: state,
      child: TripPlansPage(
        onOpenTrip: (tripId) =>
            context.push(AppRoutePaths.travelTimeline(id: tripId)),
        onOpenTemplates: () => context.push(AppRoutePaths.travelTemplates),
      ),
    ),
  ),
  GoRoute(
    path: AppRoutePaths.travelTemplates,
    pageBuilder: (context, state) => appRoutePage<void>(
      state: state,
      child: TripTemplatesPage(
        onBack: () => _leaveTravelDetail(context),
        onOpenTrip: (tripId) =>
            context.go(AppRoutePaths.travelTimeline(id: tripId)),
      ),
    ),
  ),
  GoRoute(
    path: AppRoutePaths.travelTimelinePathTemplate.replaceAll('{id}', ':id'),
    pageBuilder: (context, state) {
      final tripId = state.pathParameters['id'] ?? '';
      return appRoutePage<void>(
        state: state,
        child: TripJourneyPage(
          tripId: tripId,
          onBack: () => _leaveTravelDetail(context),
          onOpenMap: () => context.push(AppRoutePaths.travelMap(id: tripId)),
          onOpenShare: (snapshotId) =>
              context.push(AppRoutePaths.travelShare(id: snapshotId)),
          onOpenPost: (postId) =>
              context.push(AppRoutePaths.workBrowser(workId: postId)),
        ),
      );
    },
  ),
  GoRoute(
    path: AppRoutePaths.travelMapPathTemplate.replaceAll('{id}', ':id'),
    pageBuilder: (context, state) {
      final tripId = state.pathParameters['id'] ?? '';
      return appRoutePage<void>(
        state: state,
        child: TripMapPage(
          tripId: tripId,
          onBack: () => _leaveTravelDetail(context),
        ),
      );
    },
  ),
  GoRoute(
    path: AppRoutePaths.travelSharePathTemplate.replaceAll('{id}', ':id'),
    pageBuilder: (context, state) {
      final snapshotId = state.pathParameters['id'] ?? '';
      return appRoutePage<void>(
        state: state,
        child: TripSharePage(
          snapshotId: snapshotId,
          onBack: () => _leaveTravelDetail(context),
          onOpenDraft: (draftId) =>
              context.push(AppRoutePaths.create(draftId: draftId)),
        ),
      );
    },
  ),
];

void _leaveTravelDetail(BuildContext context) {
  if (context.canPop()) {
    context.pop();
  } else {
    context.go(AppRoutePaths.home);
  }
}
