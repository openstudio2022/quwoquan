/// 对象级端云契约：Remote adapter 的 HTTP path 与 generated metadata 对齐。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/content_service/content/content_reaction/adapters/post_reaction_facets_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/runtime/remote_api_path_test_harness.dart';

http.Response _responseFor(http.Request request) {
  final isWrite =
      request.method == 'POST' ||
      request.method == 'PATCH' ||
      request.method == 'DELETE';
  if (isWrite) {
    return remoteApiPathJsonResponse('{}');
  }
  return remoteApiPathJsonResponse({
    'items': <dynamic>[],
    'data': <String, dynamic>{'id': 'mock_id', 'type': 'mock'},
    'cursor': null,
  });
}

void main() {
  group('Content reaction Remote — operations.yaml 路径对齐', () {
    late List<CapturedRemoteApiPathRequest> log;
    late RemoteContentPostReactionFacet reactions;

    setUp(() {
      log = [];
      reactions = RemoteContentPostReactionFacet(
        client: buildRemoteApiPathOperationClient(
          log,
          responseFor: _responseFor,
        ),
        invocationContext: (clientPageId, {required command}) =>
            CloudOperationInvocationContext(
              surfaceId: AppUiSurfaces.homeFeed.id,
              routeId: AppUiSurfaces.homeFeed.routeId,
              clientPageId: clientPageId,
              idempotencyKey: command ? 'content-reaction-path-contract' : null,
              actor: const CloudOperationActorContext(personaId: 'persona-1'),
            ),
      );
    });

    test('likePost → POST /content/posts/{postId}/like', () async {
      try {
        await reactions.likePost(LikeContentPostCommand(postId: 'p1'));
      } catch (_) {}
      expect(log.last.method, 'POST');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.contentContentReactionLikePost,
          pathParameters: const <String, String>{'postId': 'p1'},
        ),
      );
    });

    test('unlikePost → DELETE /content/posts/{postId}/like', () async {
      try {
        await reactions.unlikePost(UnlikeContentPostCommand(postId: 'p1'));
      } catch (_) {}
      expect(log.last.method, 'DELETE');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.contentContentReactionUnlikePost,
          pathParameters: const <String, String>{'postId': 'p1'},
        ),
      );
    });
  });
}
