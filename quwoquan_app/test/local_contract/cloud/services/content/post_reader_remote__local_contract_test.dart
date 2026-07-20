import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/cloud/services/content/remote/post_reader_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('RemoteContentPostReaderAdapter local contract', () {
    test('GetPost 经 generated client 使用 workBrowser surface', () async {
      late http.Request captured;
      final adapter = RemoteContentPostReaderAdapter(
        client: _client((request) {
          captured = request;
          return <String, Object?>{
            'postId': 'post-1',
            'contentType': 'article',
            'authorDisplayName': '内容作者',
            'authorAvatarUrl': 'media/avatar/s/author/v1/avatar.png',
            'title': '正文标题',
            'body': '正文',
            'articleMarkdown': '# 正文标题',
            'status': 'published',
          };
        }),
        invocationContext: _contextFor(AppUiSurfaces.workBrowser),
      );

      final result = await adapter.getPost(postId: 'post-1');

      expect(captured.method, 'GET');
      expect(captured.url.path, '/content/posts/post-1');
      expect(captured.headers['X-Client-Page-Id'], 'content.post.get');
      expect(
        captured.headers['X-Client-Operation-Id'],
        AppCloudOperationIds.contentPostGetPost,
      );
      expect(
        captured.headers['X-Client-Surface-Id'],
        AppUiSurfaces.workBrowser.id,
      );
      expect(result.post.id, 'post-1');
      expect(result.post.displayName, '内容作者');
      expect(result.post.avatarUrl, 'media/avatar/s/author/v1/avatar.png');
      expect(result.detailWire.articleMarkdown, '# 正文标题');
    });

    test('GetPost 保留视频 canary 的播放投影字段', () async {
      final adapter = RemoteContentPostReaderAdapter(
        client: _client((_) {
          return <String, Object?>{
            'postId': 'fixture_video_001',
            'contentType': 'video',
            'contentIdentity': 'work',
            'authorId': 'fixture_user_travel',
            'authorDisplayName': '契约旅行家',
            'authorAvatarUrl':
                'media/avatar/s/archived-avatar/user/fixture_user_travel/v1/avatar.png',
            'imageUrls': <String>[
              'media/image/s/archived-image/post/fixture_video_001/v1/cover.png',
            ],
            'coverUrl':
                'media/image/s/archived-image/post/fixture_video_001/v1/cover.png',
            'thumbnailUrl':
                'media/image/s/archived-image/post/fixture_video_001/v1/cover.png',
            'videoUrl':
                'media/video/s/video-primary-0001/post/video-content-0001/source.mp4',
            'width': 1280,
            'height': 720,
            'durationMs': 45000,
            'status': 'published',
            'mediaItems': <Object?>[
              <String, Object?>{
                'kind': 'video',
                'url':
                    'media/video/s/video-primary-0001/post/video-content-0001/source.mp4',
                'coverUrl':
                    'media/image/s/archived-image/post/fixture_video_001/v1/cover.png',
                'durationMs': 45000,
                'width': 1280,
                'height': 720,
              },
            ],
          };
        }),
        invocationContext: _contextFor(AppUiSurfaces.workBrowser),
      );

      final result = await adapter.getPost(postId: 'fixture_video_001');
      final post = result.post;

      expect(post.id, 'fixture_video_001');
      expect(post.type, 'video');
      expect(post.displayName, '契约旅行家');
      expect(post.avatarUrl, isNotEmpty);
      expect(post.videoUrl, isNotEmpty);
      expect(post.thumbnailUrl, isNotEmpty);
      expect(post.durationMs, 45000);
      expect(result.mergedArticleWireMap['mediaItems'], <Object?>[
        <String, dynamic>{
          'kind': 'video',
          'url':
              'media/video/s/video-primary-0001/post/video-content-0001/source.mp4',
          'coverUrl':
              'media/image/s/archived-image/post/fixture_video_001/v1/cover.png',
          'durationMs': 45000,
          'width': 1280,
          'height': 720,
        },
      ]);
    });

    test(
      'GetEntityWishlistState 经 generated client 使用 homepageDetail surface',
      () async {
        late http.Request captured;
        final adapter = RemoteContentPostReaderAdapter(
          client: _client((request) {
            captured = request;
            return <String, Object?>{
              'objectId': 'homepage-west-lake',
              'objectKind': 'homepage',
              'wishlisted': true,
            };
          }),
          invocationContext: _contextFor(AppUiSurfaces.homepageDetail),
        );

        final result = await adapter.getEntityWishlistState(
          objectId: 'homepage-west-lake',
          objectKind: 'homepage',
        );

        expect(captured.method, 'GET');
        expect(captured.url.path, '/content/entity-wishlist-state');
        expect(captured.url.queryParameters, <String, String>{
          'objectId': 'homepage-west-lake',
          'objectKind': 'homepage',
        });
        expect(
          captured.headers['X-Client-Operation-Id'],
          AppCloudOperationIds.contentPostGetEntityWishlistState,
        );
        expect(
          captured.headers['X-Client-Surface-Id'],
          AppUiSurfaces.homepageDetail.id,
        );
        expect(result.objectId, 'homepage-west-lake');
        expect(result.objectKind, 'homepage');
        expect(result.wishlisted, isTrue);
      },
    );

    test('ListUserPosts 经 generated client 使用 userProfile surface', () async {
      late http.Request captured;
      final adapter = RemoteContentPostReaderAdapter(
        client: _client((request) {
          captured = request;
          return <String, Object?>{
            'items': <Object?>[
              <String, Object?>{
                'postId': 'post-1',
                'contentType': 'image',
                'authorId': 'author-1',
                'imageUrls': <String>['https://example.test/p.jpg'],
              },
            ],
            'nextCursor': 'cursor-2',
          };
        }),
        invocationContext: _contextFor(AppUiSurfaces.userProfile),
      );

      final result = await adapter.listUserPosts(
        userId: 'author-1',
        identity: 'work',
        type: 'image',
        visibility: 'public',
        cursor: 'cursor-1',
        limit: 10,
      );

      expect(captured.method, 'GET');
      expect(captured.url.path, '/content/sub-accounts/author-1/posts');
      expect(captured.url.queryParameters, <String, String>{
        'identity': 'work',
        'type': 'image',
        'visibility': 'public',
        'cursor': 'cursor-1',
        'limit': '10',
      });
      expect(captured.headers['X-Client-Page-Id'], 'content.user.posts');
      expect(
        captured.headers['X-Client-Operation-Id'],
        AppCloudOperationIds.contentPostListUserPosts,
      );
      expect(
        captured.headers['X-Client-Surface-Id'],
        AppUiSurfaces.userProfile.id,
      );
      expect(result.items.single.id, 'post-1');
      expect(result.items.single.imageUrls, <String>[
        'https://example.test/p.jpg',
      ]);
      expect(result.nextCursor, 'cursor-2');
    });
  });
}

GeneratedCloudOperationClient _client(
  Map<String, Object?> Function(http.Request request) responseFor,
) {
  return buildGeneratedCloudOperationClient(
    httpClient: CloudHttpClient(
      client: MockClient((request) async {
        return http.Response(
          jsonEncode(responseFor(request)),
          200,
          headers: const <String, String>{'content-type': 'application/json'},
        );
      }),
      authTokenProvider: const _TestAuthTokenProvider(),
    ),
    clientContextProvider: const _TestCloudClientContext(),
    telemetrySink: const _NoopTelemetrySink(),
    environment: CloudRuntimeEnvironment(
      environment: CloudEnvironment.gamma,
      gatewayBaseUri: Uri.parse('https://test-gateway.example.com'),
    ),
  );
}

ContentPostReaderInvocationContextFactory _contextFor(AppUiSurface surface) {
  return (clientPageId) => CloudOperationInvocationContext(
    surfaceId: surface.id,
    routeId: surface.routeId,
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(
      accountId: 'fixture-user',
      personaId: 'fixture-persona',
    ),
  );
}

final class _TestAuthTokenProvider implements CloudAuthTokenProvider {
  const _TestAuthTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'post-reader-contract-token';
}

final class _TestCloudClientContext implements CloudClientContextProvider {
  const _TestCloudClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'post-reader-contract-session',
      deviceActorId: 'post-reader-contract-device',
      platform: 'test',
      appVersion: 'test',
      locale: 'zh-CN',
    );
  }
}

final class _NoopTelemetrySink implements CloudOperationTelemetrySink {
  const _NoopTelemetrySink();

  @override
  void record(CloudOperationTelemetryEvent event) {}
}
