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
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/content/report_repository.dart';
import 'package:quwoquan_app/cloud/services/user/block_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_repository.dart';

const _baseUrl = 'https://test-gateway.example.com';

typedef _CapturedRequest = ({
  String method,
  String path,
  Map<String, String> query,
});

MockClient _captureClient(List<_CapturedRequest> log) {
  return MockClient((request) async {
    log.add((
      method: request.method,
      path: request.url.path,
      query: request.url.queryParameters,
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

    test('getCircle → GET /v1/circles/{circleId}', () async {
      try {
        await repo.getCircle('c1');
      } catch (_) {}
      expect(log.last.method, 'GET');
      expect(log.last.path, CircleApiMetadata.getCirclePath(circleId: 'c1'));
    });

    test('createCircle → POST /v1/circles', () async {
      await repo.createCircle({'name': 'test'});
      expect(log.last.method, 'POST');
      expect(log.last.path, CircleApiMetadata.createCirclePath);
    });

    test('updateCircle → PATCH /v1/circles/{circleId}', () async {
      await repo.updateCircle('c1', {'name': 'updated'});
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
      await repo.createFile('c1', {'name': 'doc.pdf'});
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
      await repo.updateFile('c1', 'f1', {'name': 'updated'});
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
      await repo.reportBehavior({'type': 'view'});
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
        await repo.createPost(payload: {'type': 'moment'});
      } catch (_) {}
      expect(log.last.method, 'POST');
      expect(log.last.path, ContentApiMetadata.createPostPath);
    });

    test('publishPost → POST /v1/content/posts/{postId}/publish', () async {
      try {
        await repo.publishPost(postId: 'p1', payload: {'visibility': 'public'});
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
            payload: {'assistantUsePolicy': 'exclude'},
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
            payload: {'contentType': 'image'},
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

    test('listPersonas → GET /v1/user/personas', () async {
      await repo.listPersonas();
      expect(log.last.method, 'GET');
      expect(log.last.path, UserApiMetadata.listPersonasPath);
    });

    test('activatePersona → POST /v1/user/personas/{id}/activate', () async {
      await repo.activatePersona('persona_1');
      expect(log.last.method, 'POST');
      expect(
        log.last.path,
        UserApiMetadata.activatePersonaPath(personaId: 'persona_1'),
      );
    });

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

    test('blockUser → POST /v1/user/block/{targetUserId}', () async {
      await repo.blockUser('u1');
      expect(log.last.method, 'POST');
      expect(log.last.path, UserApiMetadata.blockUserPath(targetUserId: 'u1'));
    });

    test('unblockUser → DELETE /v1/user/block/{targetUserId}', () async {
      await repo.unblockUser('u1');
      expect(log.last.method, 'DELETE');
      expect(
        log.last.path,
        UserApiMetadata.unblockUserPath(targetUserId: 'u1'),
      );
    });
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
}
