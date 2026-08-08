/// 对象级端云契约：Remote adapter 的 HTTP path 与 generated metadata 对齐。
library;

// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-009
// readiness_case: profile_interaction_activity_view_list_profile_interaction_activities_received_app_local
// readiness_case: profile_interaction_activity_view_list_profile_interaction_activities_sent_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/adapters/profile_interaction_activity_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/runtime/remote_api_path_test_harness.dart';

http.Response _responseFor(http.Request request) {
  final path = request.url.path;
  if (request.method == 'GET' &&
      (path ==
              canonicalRemoteApiPath(
                AppCloudOperationIds
                    .contentProfileInteractionActivityViewListProfileInteractionActivitiesReceived,
                pathParameters: const <String, String>{
                  'personaId': 'persona-1',
                },
              ) ||
          path ==
              canonicalRemoteApiPath(
                AppCloudOperationIds
                    .contentProfileInteractionActivityViewListProfileInteractionActivitiesSent,
                pathParameters: const <String, String>{
                  'personaId': 'persona-1',
                },
              ))) {
    return remoteApiPathJsonResponse('{"items":[],"hasMore":false}');
  }
  return remoteApiPathJsonResponse({
    'items': <dynamic>[],
    'data': <String, dynamic>{'id': 'mock_id', 'type': 'mock'},
    'cursor': null,
  });
}

void main() {
  group('Profile interaction activity adapter — generated operation 路径对齐', () {
    late List<CapturedRemoteApiPathRequest> log;
    late RemoteProfileInteractionActivityQuery activityQuery;

    setUp(() {
      log = [];
      final client = buildRemoteApiPathOperationClient(
        log,
        responseFor: _responseFor,
      );
      activityQuery = RemoteProfileInteractionActivityQuery(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.profileHome.id,
          routeId: AppUiSurfaces.profileHome.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            accountId: 'account-1',
            personaId: 'persona-1',
          ),
        ),
      );
    });

    test('received activities → canonical received path', () async {
      await activityQuery.listActivities(
        ContentProfileInteractionPageQuery(
          personaId: 'persona-1',
          type: InteractionActivityType.share,
          limit: 9,
        ),
        direction: InteractionDirection.received,
      );
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds
              .contentProfileInteractionActivityViewListProfileInteractionActivitiesReceived,
          pathParameters: const <String, String>{'personaId': 'persona-1'},
        ),
      );
    });

    test('sent activities → canonical sent path', () async {
      await activityQuery.listActivities(
        ContentProfileInteractionPageQuery(
          personaId: 'persona-1',
          type: InteractionActivityType.comment,
        ),
        direction: InteractionDirection.sent,
      );
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds
              .contentProfileInteractionActivityViewListProfileInteractionActivitiesSent,
          pathParameters: const <String, String>{'personaId': 'persona-1'},
        ),
      );
    });
  });
}
