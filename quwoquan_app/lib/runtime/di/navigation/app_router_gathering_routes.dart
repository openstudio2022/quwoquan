import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/native_back_navigation.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/gathering_board_route_host.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_route_hosts.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/gathering_create_navigation_request.dart';

List<GoRoute> gatheringRoutes() => <GoRoute>[
  GoRoute(
    path: AppRoutePaths.gatheringCreate,
    pageBuilder: (context, state) => appRoutePage<void>(
      state: state,
      kind: AppRoutePageKind.fullscreenDialog,
      fullscreenDialog: true,
      child: GatheringCreatePageRouteHost(
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
      child: GatheringDetailPageRouteHost(
        gatheringId: state.pathParameters['id'] ?? '',
      ),
    ),
  ),
];

GoRoute gatheringBoardRoute() {
  return GoRoute(
    path: AppRoutePaths.gatheringBoardSegment,
    pageBuilder: (context, state) => appRoutePage<void>(
      state: state,
      child: GatheringBoardPageRouteHost(
        conversationId: state.pathParameters['id'] ?? '',
      ),
    ),
  );
}
