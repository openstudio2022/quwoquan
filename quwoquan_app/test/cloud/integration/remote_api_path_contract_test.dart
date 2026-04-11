/// L1a+ 端云集成契约测试：Remote Repository URL 路径与 metadata service.yaml 对齐
///
/// 通过注入 mock HTTP client 捕获实际请求的 URL，验证：
/// 1. HTTP 方法正确（GET/POST/PATCH/DELETE）
/// 2. URL 路径与 service.yaml 定义一致
/// 3. CloudRequestHeaders 正确注入
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/content/report_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/cloud/services/integration/integration_repository.dart';
import 'package:quwoquan_app/cloud/services/user/block_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_repository.dart';

const _baseUrl = 'https://test-gateway.example.com';

typedef _CapturedRequest = ({
  String method,
  String path,
  Map<String, String> query,
  Map<String, String> headers,
});

MockClient _captureClient(List<_CapturedRequest> log) {
  return MockClient((request) async {
    log.add((
      method: request.method,
      path: request.url.path,
      query: request.url.queryParameters,
      headers: Map<String, String>.from(request.headers),
    ));

    final path = request.url.path;
    final isWrite =
        request.method == 'POST' ||
        request.method == 'PATCH' ||
        request.method == 'DELETE';
    final isVoid =
        isWrite &&
        !path.endsWith('/posts') &&
        !path.endsWith('/circles') &&
        !path.endsWith('/comments') &&
        !path.endsWith('/files');

    if (isVoid) {
      return http.Response(
        '{}',
        200,
        headers: {'content-type': 'application/json'},
      );
    }

    final body = json.encode({
      'items': <dynamic>[],
      'data': <String, dynamic>{'id': 'mock_id', 'type': 'mock'},
      'cursor': null,
    });
    return http.Response(
      body,
      200,
      headers: {'content-type': 'application/json'},
    );
  });
}

void _expectPageHeaders(Map<String, String> headers, {required String pageId}) {
  expect(headers['X-Client-Page-Id'], pageId);
  expect(headers['X-Trace-Id'], contains(pageId));
  expect(headers['X-Request-Id'], contains(pageId));
}

void _expectSurfaceOperationHeaders(
  Map<String, String> headers, {
  required String clientPageId,
  required String surfaceId,
  required String operationId,
}) {
  expect(headers['X-Client-Page-Id'], clientPageId);
  expect(headers['X-Client-Surface-Id'], surfaceId);
  expect(headers['X-Client-Operation-Id'], operationId);
  expect(headers['X-Trace-Id'], contains(surfaceId));
  expect(headers['X-Trace-Id'], contains(operationId));
  expect(headers['X-Request-Id'], contains(surfaceId));
  expect(headers['X-Request-Id'], contains(operationId));
}

void main() {
  group('CircleRepository Remote — service.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteCircleRepository repo;

    setUp(() {
      log = [];
      repo = RemoteCircleRepository(
        client: _captureClient(log),
        baseUrl: _baseUrl,
      );
    });

    test('listCircles → GET /v1/circles', () async {
      try {
        await repo.listCircles();
      } catch (_) {}
      expect(log.last.method, 'GET');
      expect(log.last.path, CircleApiMetadata.listCirclesPath);
    });

    test('searchCircles → GET /v1/circles/search', () async {
      await repo.searchCircles(
        query: '摄影',
        categoryId: 'art',
        subCategory: 'photo',
        limit: 6,
      );
      expect(log.last.method, 'GET');
      expect(log.last.path, CircleApiMetadata.searchCirclesPath);
      expect(log.last.query['query'], '摄影');
      expect(log.last.query['categoryId'], 'art');
      expect(log.last.query['subCategory'], 'photo');
      expect(log.last.query['limit'], '6');
      _expectPageHeaders(
        log.last.headers,
        pageId: CircleRequestPageIds.searchCircles,
      );
    });

    test('getCircle → GET /v1/circles/{circleId}', () async {
      try {
        await repo.getCircle('c1');
      } catch (_) {}
      expect(log.last.method, 'GET');
      expect(log.last.path, CircleApiMetadata.getCirclePath(circleId: 'c1'));
    });

    test('createCircle → POST /v1/circles', () async {
      await repo.createCircle(CircleCreateWireDto.fromMap({'name': 'test'}));
      expect(log.last.method, 'POST');
      expect(log.last.path, CircleApiMetadata.createCirclePath);
    });

    test('updateCircle → PATCH /v1/circles/{circleId}', () async {
      await repo.updateCircle(
        'c1',
        CircleUpdateWireDto.fromMap({'name': 'updated'}),
      );
      expect(log.last.method, 'PATCH');
      expect(log.last.path, CircleApiMetadata.updateCirclePath(circleId: 'c1'));
    });

    test('archiveCircle → DELETE /v1/circles/{circleId}', () async {
      await repo.archiveCircle('c1');
      expect(log.last.method, 'DELETE');
      expect(
        log.last.path,
        CircleApiMetadata.archiveCirclePath(circleId: 'c1'),
      );
    });

    test('joinCircle → POST /v1/circles/{circleId}/join', () async {
      await repo.joinCircle('c1');
      expect(log.last.method, 'POST');
      expect(log.last.path, CircleApiMetadata.joinCirclePath(circleId: 'c1'));
    });

    test('leaveCircle → POST /v1/circles/{circleId}/leave', () async {
      await repo.leaveCircle('c1');
      expect(log.last.method, 'POST');
      expect(log.last.path, CircleApiMetadata.leaveCirclePath(circleId: 'c1'));
    });

    test('listMembers → GET /v1/circles/{circleId}/members', () async {
      try {
        await repo.listMembers('c1');
      } catch (_) {}
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        CircleApiMetadata.listCircleMembersPath(circleId: 'c1'),
      );
    });

    test(
      'updateMemberRole → PATCH /v1/circles/{id}/members/{uid}/role',
      () async {
        await repo.updateMemberRole('c1', 'u1', 'admin');
        expect(log.last.method, 'PATCH');
        expect(
          log.last.path,
          CircleApiMetadata.updateMemberRolePath(circleId: 'c1', userId: 'u1'),
        );
      },
    );

    test(
      'searchCircleGroups → GET /v1/circles/{circleId}/groups/search',
      () async {
        try {
          await repo.searchCircleGroups(
            'c1',
            query: '摄影',
            visibility: 'private',
            groupType: 'discussion',
            limit: 5,
          );
        } catch (_) {}
        expect(log.last.method, 'GET');
        expect(
          log.last.path,
          CircleApiMetadata.searchCircleGroupsPath(circleId: 'c1'),
        );
        expect(log.last.query['query'], '摄影');
        expect(log.last.query['visibility'], 'private');
        expect(log.last.query['groupType'], 'discussion');
        expect(log.last.query['limit'], '5');
        _expectPageHeaders(
          log.last.headers,
          pageId: CircleRequestPageIds.searchCircleGroups,
        );
      },
    );

    test('getCircleFeed → GET /v1/circles/{circleId}/feed', () async {
      try {
        await repo.getCircleFeed('c1');
      } catch (_) {}
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        CircleApiMetadata.getCircleFeedPath(circleId: 'c1'),
      );
    });

    test('getCircleFeed 透传 identity/type query', () async {
      try {
        await repo.getCircleFeed('c1', identity: 'work', type: 'article');
      } catch (_) {}
      expect(log.last.query['identity'], 'work');
      expect(log.last.query['type'], 'article');
    });

    test('pinPost → PATCH /v1/circles/{id}/feed/{postId}/pin', () async {
      await repo.pinPost('c1', 'p1', pinned: true);
      expect(log.last.method, 'PATCH');
      expect(
        log.last.path,
        CircleApiMetadata.pinCirclePostPath(circleId: 'c1', postId: 'p1'),
      );
    });

    test(
      'featurePost → PATCH /v1/circles/{id}/feed/{postId}/feature',
      () async {
        await repo.featurePost('c1', 'p1', featured: true);
        expect(log.last.method, 'PATCH');
        expect(
          log.last.path,
          CircleApiMetadata.featureCirclePostPath(circleId: 'c1', postId: 'p1'),
        );
      },
    );

    test('getCircleStats → GET /v1/circles/{circleId}/stats', () async {
      await repo.getCircleStats('c1');
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        CircleApiMetadata.getCircleStatsPath(circleId: 'c1'),
      );
    });

    test('listFiles → GET /v1/circles/{circleId}/files', () async {
      try {
        await repo.listFiles('c1');
      } catch (_) {}
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        CircleApiMetadata.listCircleFilesPath(circleId: 'c1'),
      );
    });

    test('createFile → POST /v1/circles/{circleId}/files', () async {
      await repo.createFile(
        'c1',
        CircleFileCreateWireDto.fromMap({
          'name': 'doc.pdf',
          'fileType': 'file',
        }),
      );
      expect(log.last.method, 'POST');
      expect(
        log.last.path,
        CircleApiMetadata.createCircleFilePath(circleId: 'c1'),
      );
    });

    test('getFile → GET /v1/circles/{circleId}/files/{fileId}', () async {
      await repo.getFile('c1', 'f1');
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        CircleApiMetadata.getCircleFilePath(circleId: 'c1', fileId: 'f1'),
      );
    });

    test('updateFile → PATCH /v1/circles/{id}/files/{fileId}', () async {
      await repo.updateFile(
        'c1',
        'f1',
        CircleFileUpdateWireDto.fromMap({'name': 'updated'}),
      );
      expect(log.last.method, 'PATCH');
      expect(
        log.last.path,
        CircleApiMetadata.updateCircleFilePath(circleId: 'c1', fileId: 'f1'),
      );
    });

    test('deleteFile → DELETE /v1/circles/{id}/files/{fileId}', () async {
      await repo.deleteFile('c1', 'f1');
      expect(log.last.method, 'DELETE');
      expect(
        log.last.path,
        CircleApiMetadata.deleteCircleFilePath(circleId: 'c1', fileId: 'f1'),
      );
    });

    test('updateSections → PATCH /v1/circles/{circleId}/sections', () async {
      await repo.updateSections('c1', []);
      expect(log.last.method, 'PATCH');
      expect(
        log.last.path,
        CircleApiMetadata.updateCircleSectionsPath(circleId: 'c1'),
      );
    });

    test('reportBehavior → POST /v1/circles/behaviors', () async {
      await repo.reportBehavior(
        CircleBehaviorReportWireDto.fromMap({'type': 'view'}),
      );
      expect(log.last.method, 'POST');
      expect(log.last.path, CircleApiMetadata.reportCircleBehaviorPath);
    });
  });

  group('ContentRepository Remote — service.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteContentRepository repo;

    setUp(() {
      log = [];
      repo = RemoteContentRepository(client: _captureClient(log));
    });

    test('listDiscoveryFeed → GET /v1/content/feed', () async {
      await repo.listDiscoveryFeed(category: 'all');
      expect(log.last.method, 'GET');
      expect(log.last.path, ContentApiMetadata.getFeedPath);
    });

    test('searchPosts → GET /v1/content/posts/search', () async {
      await repo.searchPosts(
        query: '摄影',
        identity: 'work',
        type: 'article',
        categoryId: 'art',
        subCategory: 'photo',
        limit: 9,
      );
      expect(log.last.method, 'GET');
      expect(log.last.path, ContentApiMetadata.searchPostsPath);
      expect(log.last.query['query'], '摄影');
      expect(log.last.query['identity'], 'work');
      expect(log.last.query['type'], 'article');
      expect(log.last.query['categoryId'], 'art');
      expect(log.last.query['subCategory'], 'photo');
      expect(log.last.query['limit'], '9');
      _expectPageHeaders(
        log.last.headers,
        pageId: ContentRequestPageIds.searchPosts,
      );
    });

    test('listDiscoveryFeed 透传 identity/type query', () async {
      await repo.listDiscoveryFeed(
        category: 'work',
        identity: 'work',
        type: 'article',
      );
      expect(log.last.query['identity'], 'work');
      expect(log.last.query['type'], 'article');
    });

    test('getPost → GET /v1/content/posts/{postId}', () async {
      try {
        await repo.getPost(postId: 'p1');
      } catch (_) {}
      expect(log.last.method, 'GET');
      expect(log.last.path, ContentApiMetadata.getPostPath(postId: 'p1'));
    });

    test('createPost → POST /v1/content/posts', () async {
      try {
        await repo.createPost(
          body: CreatePostRequestWire.fromMap({'type': 'moment'}),
        );
      } catch (_) {}
      expect(log.last.method, 'POST');
      expect(log.last.path, ContentApiMetadata.createPostPath);
    });

    test('publishPost → POST /v1/content/posts/{postId}/publish', () async {
      try {
        await repo.publishPost(
          postId: 'p1',
          body: PublishPostRequestWire.fromMap({'visibility': 'public'}),
        );
      } catch (_) {}
      expect(log.last.method, 'POST');
      expect(log.last.path, ContentApiMetadata.publishPostPath(postId: 'p1'));
    });

    test(
      'updatePostSettings → PATCH /v1/content/posts/{postId}/settings',
      () async {
        try {
          await repo.updatePostSettings(
            postId: 'p1',
            body: UpdatePostSettingsRequestWire.fromMap({
              'assistantUsePolicy': 'exclude',
            }),
          );
        } catch (_) {}
        expect(log.last.method, 'PATCH');
        expect(
          log.last.path,
          ContentApiMetadata.updatePostSettingsPath(postId: 'p1'),
        );
      },
    );

    test(
      'promotePostToWork → POST /v1/content/posts/{postId}:promoteToWork',
      () async {
        try {
          await repo.promotePostToWork(
            postId: 'p1',
            body: PromotePostToWorkRequestWire.fromMap({
              'contentType': 'image',
            }),
          );
        } catch (_) {}
        expect(log.last.method, 'POST');
        expect(
          log.last.path,
          ContentApiMetadata.promotePostToWorkPath(postId: 'p1'),
        );
      },
    );

    test('likePost → POST /v1/content/posts/{postId}/like', () async {
      await repo.likePost(postId: 'p1');
      expect(log.last.method, 'POST');
      expect(log.last.path, ContentApiMetadata.likePostPath(postId: 'p1'));
    });

    test('unlikePost → DELETE /v1/content/posts/{postId}/like', () async {
      await repo.unlikePost(postId: 'p1');
      expect(log.last.method, 'DELETE');
      expect(log.last.path, ContentApiMetadata.unlikePostPath(postId: 'p1'));
    });

    test('favoritePost → POST /v1/content/posts/{postId}/favorite', () async {
      await repo.favoritePost(postId: 'p1');
      expect(log.last.method, 'POST');
      expect(log.last.path, ContentApiMetadata.favoritePostPath(postId: 'p1'));
    });

    test(
      'unfavoritePost → DELETE /v1/content/posts/{postId}/favorite',
      () async {
        await repo.unfavoritePost(postId: 'p1');
        expect(log.last.method, 'DELETE');
        expect(
          log.last.path,
          ContentApiMetadata.unfavoritePostPath(postId: 'p1'),
        );
      },
    );

    test('listComments → GET /v1/content/posts/{postId}/comments', () async {
      await repo.listComments(postId: 'p1');
      expect(log.last.method, 'GET');
      expect(log.last.path, ContentApiMetadata.listCommentsPath(postId: 'p1'));
    });

    test('createComment → POST /v1/content/posts/{postId}/comments', () async {
      await repo.createComment(postId: 'p1', content: 'hi');
      expect(log.last.method, 'POST');
      expect(log.last.path, ContentApiMetadata.createCommentPath(postId: 'p1'));
    });

    test(
      'deleteComment → DELETE /v1/content/posts/{postId}/comments/{commentId}',
      () async {
        await repo.deleteComment(postId: 'p1', commentId: 'c1');
        expect(log.last.method, 'DELETE');
        expect(
          log.last.path,
          ContentApiMetadata.deleteCommentPath(postId: 'p1', commentId: 'c1'),
        );
      },
    );

    test('reportBehaviors → POST /v1/content/behaviors', () async {
      await repo.reportBehaviors(events: []);
      expect(log.last.method, 'POST');
      expect(log.last.path, ContentApiMetadata.reportBehaviorsPath);
    });

    test('getCounters → GET /v1/content/posts/{postId}/counters', () async {
      await repo.getCounters(postId: 'p1');
      expect(log.last.method, 'GET');
      expect(log.last.path, ContentApiMetadata.getCountersPath(postId: 'p1'));
    });

    test(
      'getReactionState → GET /v1/content/posts/{postId}/reactions',
      () async {
        await repo.getReactionState(postId: 'p1');
        expect(log.last.method, 'GET');
        expect(
          log.last.path,
          ContentApiMetadata.getReactionStatePath(postId: 'p1'),
        );
      },
    );
  });

  group('ReportRepository Remote — service.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteReportRepository repo;

    setUp(() {
      log = [];
      repo = RemoteReportRepository(
        client: _captureClient(log),
        baseUrl: _baseUrl,
      );
    });

    test('createReport → POST /v1/content/reports', () async {
      await repo.createReport(
        targetId: 'p1',
        targetType: 'post',
        reason: 'spam',
      );
      expect(log.last.method, 'POST');
      expect(log.last.path, ContentApiMetadata.createReportPath);
    });
  });

  group('UserRepository Remote — service.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteUserRepository repo;

    setUp(() {
      log = [];
      repo = RemoteUserRepository(
        client: _captureClient(log),
        baseUrl: _baseUrl,
      );
    });

    test('listSubAccounts → GET /v1/owner/sub-accounts', () async {
      await repo.listSubAccounts();
      expect(log.last.method, 'GET');
      expect(log.last.path, UserApiMetadata.listSubAccountsPath);
    });

    test(
      'getActivePersonaContext → GET /v1/owner/sub-accounts/active',
      () async {
        await repo.getActivePersonaContext();
        expect(log.last.method, 'GET');
        expect(log.last.path, UserApiMetadata.getActivePersonaContextPath);
      },
    );

    test('createSubAccount → POST /v1/owner/sub-accounts', () async {
      await repo.createSubAccount(displayName: '摄影分身');
      expect(log.last.method, 'POST');
      expect(log.last.path, UserApiMetadata.createSubAccountPath);
    });

    test(
      'activateSubAccount → POST /v1/owner/sub-accounts/{id}/activate',
      () async {
        await repo.activateSubAccount('persona_1');
        expect(log.last.method, 'POST');
        expect(
          log.last.path,
          UserApiMetadata.activateSubAccountPath(subAccountId: 'persona_1'),
        );
      },
    );

    test(
      'deleteEmptySubAccount → DELETE /v1/owner/sub-accounts/{id}:delete-empty',
      () async {
        await repo.deleteEmptySubAccount('persona_1');
        expect(log.last.method, 'DELETE');
        expect(
          log.last.path,
          UserApiMetadata.deleteEmptySubAccountPath(subAccountId: 'persona_1'),
        );
      },
    );

    test(
      'getNotificationSettings → GET /v1/user/settings/notifications',
      () async {
        await repo.getNotificationSettings();
        expect(log.last.method, 'GET');
        expect(log.last.path, UserApiMetadata.getNotificationSettingsPath);
      },
    );

    test('getPrivacySettings → GET /v1/user/settings/privacy', () async {
      await repo.getPrivacySettings();
      expect(log.last.method, 'GET');
      expect(log.last.path, UserApiMetadata.getPrivacySettingsPath);
    });
  });

  group('BlockRepository Remote — service.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteBlockRepository repo;

    setUp(() {
      log = [];
      repo = RemoteBlockRepository(
        client: _captureClient(log),
        baseUrl: _baseUrl,
      );
    });

    test(
      'blockUser → POST /v1/user/profile-subjects/{targetProfileSubjectId}/block',
      () async {
        await repo.blockUser('u1');
        expect(log.last.method, 'POST');
        expect(
          log.last.path,
          UserApiMetadata.blockUserPath(targetProfileSubjectId: 'u1'),
        );
      },
    );

    test(
      'unblockUser → DELETE /v1/user/profile-subjects/{targetProfileSubjectId}/block',
      () async {
        await repo.unblockUser('u1');
        expect(log.last.method, 'DELETE');
        expect(
          log.last.path,
          UserApiMetadata.unblockUserPath(targetProfileSubjectId: 'u1'),
        );
      },
    );
  });

  group('UserProfileRepository Remote — service.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteUserProfileRepository repo;

    setUp(() {
      log = [];
      repo = RemoteUserProfileRepository(client: _captureClient(log));
    });

    test('getUserStats → GET /v1/user/profile/{userId}/stats', () async {
      try {
        await repo.getUserStats('u1');
      } catch (_) {}
      expect(log.isNotEmpty, isTrue);
      expect(log.last.method, 'GET');
    });
  });

  group('HomepageRepository Remote — service.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteHomepageRepository repo;

    setUp(() {
      log = [];
      repo = RemoteHomepageRepository(
        httpClient: CloudHttpClient(client: _captureClient(log)),
        baseUrl: _baseUrl,
      );
    });

    test('searchHomepages → GET /v1/homepages/search', () async {
      await repo.searchHomepages(
        query: '书店',
        homepageType: 'storefront',
        city: '深圳',
        status: 'published',
        limit: 7,
      );
      expect(log.last.method, 'GET');
      expect(log.last.path, EntityApiMetadata.searchHomepagesPath);
      expect(log.last.query['query'], '书店');
      expect(log.last.query['homepageType'], 'storefront');
      expect(log.last.query['city'], '深圳');
      expect(log.last.query['status'], 'published');
      expect(log.last.query['limit'], '7');
      _expectSurfaceOperationHeaders(
        log.last.headers,
        clientPageId: EntityRequestPageIds.searchHomepages,
        surfaceId: AppUiSurfaces.homepagePicker.id,
        operationId: EntityApiMetadata.searchHomepagesOperation,
      );
    });

    test('getHomepageShell → GET /v1/homepages/{homepageId}/shell', () async {
      await repo.getHomepageShell('hp1');
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        EntityApiMetadata.getHomepageShellPath(homepageId: 'hp1'),
      );
      _expectSurfaceOperationHeaders(
        log.last.headers,
        clientPageId: EntityRequestPageIds.getHomepageShell,
        surfaceId: AppUiSurfaces.homepageDetail.id,
        operationId: EntityApiMetadata.getHomepageShellOperation,
      );
    });

    test(
      'getHomepageReviewSummary → GET /v1/homepages/{homepageId}/review-summary',
      () async {
        await repo.getHomepageReviewSummary('hp1');
        expect(log.last.method, 'GET');
        expect(
          log.last.path,
          EntityApiMetadata.getHomepageReviewSummaryPath(homepageId: 'hp1'),
        );
        _expectSurfaceOperationHeaders(
          log.last.headers,
          clientPageId: EntityRequestPageIds.getHomepageReviewSummary,
          surfaceId: AppUiSurfaces.homepageDetail.id,
          operationId: EntityApiMetadata.getHomepageReviewSummaryOperation,
        );
      },
    );

    test(
      'getHomepageRelatedGroups → GET /v1/homepages/{homepageId}/related-groups',
      () async {
        await repo.getHomepageRelatedGroups('hp1');
        expect(log.last.method, 'GET');
        expect(
          log.last.path,
          EntityApiMetadata.getHomepageRelatedGroupsPath(homepageId: 'hp1'),
        );
        _expectSurfaceOperationHeaders(
          log.last.headers,
          clientPageId: EntityRequestPageIds.getHomepageRelatedGroups,
          surfaceId: AppUiSurfaces.homepageDetail.id,
          operationId: EntityApiMetadata.getHomepageRelatedGroupsOperation,
        );
      },
    );
  });

  group('IntegrationRepository Remote — service.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteIntegrationRepository repo;

    setUp(() {
      log = [];
      repo = RemoteIntegrationRepository(
        httpClient: CloudHttpClient(client: _captureClient(log)),
        baseUrl: _baseUrl,
      );
    });

    test('getNearbyLocations → GET /v1/integration/location/nearby', () async {
      await repo.getNearbyLocations(
        latitude: 30.2431,
        longitude: 120.1500,
        radiusMeters: 2000,
        limit: 8,
      );
      expect(log.last.method, 'GET');
      expect(log.last.path, IntegrationApiMetadata.getNearbyLocationsPath);
      expect(log.last.query['lat'], '30.2431');
      expect(log.last.query['lng'], '120.15');
      expect(log.last.query['radiusMeters'], '2000');
      expect(log.last.query['limit'], '8');
      _expectSurfaceOperationHeaders(
        log.last.headers,
        clientPageId: IntegrationRequestPageIds.getNearbyLocations,
        surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
        operationId: IntegrationApiMetadata.getNearbyLocationsOperation,
      );
    });

    test('searchLocations → GET /v1/integration/location/search', () async {
      await repo.searchLocations(
        query: '西湖',
        cityCode: '330100',
        latitude: 30.2431,
        longitude: 120.1500,
        limit: 12,
      );
      expect(log.last.method, 'GET');
      expect(log.last.path, IntegrationApiMetadata.searchLocationsPath);
      expect(log.last.query['q'], '西湖');
      expect(log.last.query['cityCode'], '330100');
      expect(log.last.query['lat'], '30.2431');
      expect(log.last.query['lng'], '120.15');
      expect(log.last.query['limit'], '12');
      _expectSurfaceOperationHeaders(
        log.last.headers,
        clientPageId: IntegrationRequestPageIds.searchLocations,
        surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
        operationId: IntegrationApiMetadata.searchLocationsOperation,
      );
    });
  });
}
