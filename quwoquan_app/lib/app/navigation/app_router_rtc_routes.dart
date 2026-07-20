part of 'app_router.dart';

List<GoRoute> _rtcRoutes() => <GoRoute>[
  GoRoute(
    path: AppRoutePaths.rtcOutgoingPathTemplate.replaceAll(
      '{callId}',
      ':callId',
    ),
    pageBuilder: (context, state) {
      final callId = state.pathParameters['callId'] ?? '';
      return appRoutePage<void>(
        state: state,
        child: OutgoingCallPage(callId: callId),
      );
    },
  ),
  GoRoute(
    path: AppRoutePaths.rtcIncomingPathTemplate.replaceAll(
      '{callId}',
      ':callId',
    ),
    pageBuilder: (context, state) {
      final callId = state.pathParameters['callId'] ?? '';
      return appRoutePage<void>(
        state: state,
        child: IncomingCallPage(callId: callId),
      );
    },
  ),
  GoRoute(
    path: AppRoutePaths.rtcVoicePathTemplate.replaceAll('{callId}', ':callId'),
    pageBuilder: (context, state) {
      final callId = state.pathParameters['callId'] ?? '';
      return appRoutePage<void>(
        state: state,
        child: VoiceCallPage(callId: callId),
      );
    },
  ),
  GoRoute(
    path: AppRoutePaths.rtcVideoPathTemplate.replaceAll('{callId}', ':callId'),
    pageBuilder: (context, state) {
      final callId = state.pathParameters['callId'] ?? '';
      return appRoutePage<void>(
        state: state,
        child: VideoCallPage(callId: callId),
      );
    },
  ),
  GoRoute(
    path: AppRoutePaths.rtcPickParticipants,
    pageBuilder: (context, state) {
      final extra = CallParticipantPickerRouteExtra.fromRouter(state.extra);
      return appRoutePage<void>(
        state: state,
        child: CallParticipantPickerPage(routeExtra: extra),
      );
    },
  ),
];
