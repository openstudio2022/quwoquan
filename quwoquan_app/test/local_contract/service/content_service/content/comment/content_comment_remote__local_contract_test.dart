// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-004.t2
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-007
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-009
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-012
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-021
// readiness_case: comment_create_comment_app_local
// readiness_case: comment_delete_comment_app_local
// readiness_case: comment_list_comment_replies_app_local
// readiness_case: comment_list_comments_app_local
// readiness_case: comment_list_comments_by_author_app_local
// readiness_case: comment_list_comments_for_post_author_app_local
// readiness_case: comment_pin_comment_app_local
// readiness_case: comment_unpin_comment_app_local

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/service/content_service/content/comment/adapters/comment_facets_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('RemoteContentCommentFacet generated HTTP contract', () {
    test('ListComments uses the canonical sorted page query', () async {
      late http.Request captured;
      final adapter = RemoteContentCommentFacet(
        client: _client((request) {
          captured = request;
          return _pageResponse(
            _wireItem(
              id: 'comment-list-1',
              replyCount: 2,
              replyPreview: <Object?>[
                _wireItem(
                  id: 'reply-preview-1',
                  replyToCommentId: 'comment-list-1',
                  parentCommentId: 'comment-list-1',
                ),
              ],
              replyNextCursor: 'reply-preview-next',
            ),
            nextCursor: 'comments-next',
          );
        }),
        invocationContext: _context,
      );

      final page = await adapter.listComments(
        postId: 'post-1',
        cursor: 'comments-cursor',
        limit: 25,
        sort: CommentSort.latest,
      );

      _expectQueryRequest(
        captured,
        method: 'GET',
        path: '/content/posts/post-1/comments',
        operationId: AppCloudOperationIds.contentCommentListComments,
        query: const <String, String>{
          'cursor': 'comments-cursor',
          'limit': '25',
          'sort': 'latest',
        },
      );
      expect(page.items.single.id, 'comment-list-1');
      expect(page.items.single.viewerReaction, CommentReactionType.like);
      expect(page.items.single.replyCount, 2);
      expect(page.items.single.replyPreview.single.id, 'reply-preview-1');
      expect(page.items.single.replyNextCursor, 'reply-preview-next');
      expect(page.nextCursor, 'comments-next');
      expect(page.total, 1);
    });

    test('ListCommentReplies uses the canonical bounded reply page', () async {
      late http.Request captured;
      final adapter = RemoteContentCommentFacet(
        client: _client((request) {
          captured = request;
          return _pageResponse(
            _wireItem(
              id: 'reply-1',
              replyToCommentId: 'comment-root',
              parentCommentId: 'comment-root',
            ),
            nextCursor: 'replies-next',
          );
        }),
        invocationContext: _context,
      );

      final page = await adapter.listReplies(
        postId: 'post-1',
        commentId: 'comment-root',
        cursor: 'replies-cursor',
        limit: 7,
      );

      _expectQueryRequest(
        captured,
        method: 'GET',
        path: '/content/posts/post-1/comments/comment-root/replies',
        operationId: AppCloudOperationIds.contentCommentListCommentReplies,
        query: const <String, String>{'cursor': 'replies-cursor', 'limit': '7'},
      );
      expect(page.items.single.id, 'reply-1');
      expect(page.items.single.parentCommentId, 'comment-root');
      expect(page.nextCursor, 'replies-next');
    });

    test(
      'personal comment readers keep their distinct generated paths',
      () async {
        final captured = <http.Request>[];
        final adapter = RemoteContentCommentFacet(
          client: _client((request) {
            captured.add(request);
            final operationId = request.headers['X-Client-Operation-Id'];
            return _pageResponse(
              _wireItem(
                id:
                    operationId ==
                        AppCloudOperationIds.contentCommentListCommentsByAuthor
                    ? 'authored-comment-1'
                    : 'received-comment-1',
              ),
            );
          }),
          invocationContext: _context,
        );

        final authored = await adapter.listByAuthor(
          cursor: 'authored-cursor',
          limit: 9,
        );
        final received = await adapter.listReceived(
          cursor: 'received-cursor',
          limit: 11,
        );

        _expectQueryRequest(
          captured[0],
          method: 'GET',
          path: '/content/users/me/comments',
          operationId: AppCloudOperationIds.contentCommentListCommentsByAuthor,
          query: const <String, String>{
            'cursor': 'authored-cursor',
            'limit': '9',
          },
        );
        _expectQueryRequest(
          captured[1],
          method: 'GET',
          path: '/content/users/me/received-comments',
          operationId:
              AppCloudOperationIds.contentCommentListCommentsForPostAuthor,
          query: const <String, String>{
            'cursor': 'received-cursor',
            'limit': '11',
          },
        );
        expect(authored.items.single.id, 'authored-comment-1');
        expect(received.items.single.id, 'received-comment-1');
      },
    );

    test(
      'CreateComment preserves typed reply, attachment and replay receipt',
      () async {
        final captured = <http.Request>[];
        final adapter = RemoteContentCommentFacet(
          client: _client((request) {
            captured.add(request);
            return _commandResponse(
              id: 'comment-created-1',
              version: 3,
              status: 'active',
              replayed: captured.length > 1,
            );
          }),
          invocationContext: _context,
        );
        final command = CreateContentCommentCommand(
          postId: 'post-1',
          content: 'typed comment',
          replyToCommentId: 'comment-root',
          attachmentMediaIds: const <String>['media-1'],
          mentions: <CommentMention>[
            CommentMention(
              subjectType: 'user',
              subjectId: 'persona-2',
              displayName: 'mentioned persona',
            ),
          ],
          personaContextVersion: 7,
        );

        final first = await adapter.createComment(command);
        final replay = await adapter.createComment(command);

        for (final request in captured) {
          _expectCommandRequest(
            request,
            method: 'POST',
            path: '/content/posts/post-1/comments',
            operationId: AppCloudOperationIds.contentCommentCreateComment,
            body: <String, Object?>{
              'content': 'typed comment',
              'replyToCommentId': 'comment-root',
              'attachmentMediaIds': <Object?>['media-1'],
              'mentions': <Object?>[
                <String, Object?>{
                  'subjectType': 'user',
                  'subjectId': 'persona-2',
                  'displayName': 'mentioned persona',
                },
              ],
              'personaContextVersion': 7,
            },
          );
        }
        expect(first.id, 'comment-created-1');
        expect(first.replayed, isFalse);
        expect(replay.id, first.id);
        expect(replay.version, first.version);
        expect(replay.replayed, isTrue);
      },
    );

    test('pin, unpin and delete remain distinct named commands', () async {
      final captured = <http.Request>[];
      var pinCalls = 0;
      final adapter = RemoteContentCommentFacet(
        client: _client((request) {
          captured.add(request);
          final operationId = request.headers['X-Client-Operation-Id'];
          if (operationId == AppCloudOperationIds.contentCommentPinComment) {
            pinCalls += 1;
          }
          return _commandResponse(
            id: 'comment-command-1',
            version: switch (operationId) {
              AppCloudOperationIds.contentCommentPinComment => 1,
              AppCloudOperationIds.contentCommentUnpinComment => 2,
              _ => 3,
            },
            status:
                operationId == AppCloudOperationIds.contentCommentDeleteComment
                ? 'deleted'
                : 'active',
            replayed:
                operationId == AppCloudOperationIds.contentCommentPinComment &&
                pinCalls > 1,
          );
        }),
        invocationContext: _context,
      );
      final pinCommand = ChangeContentCommentPinCommand(
        postId: 'post-1',
        commentId: 'comment-command-1',
      );

      final pinned = await adapter.pinComment(pinCommand);
      final pinReplay = await adapter.pinComment(pinCommand);
      final unpinned = await adapter.unpinComment(pinCommand);
      final deleted = await adapter.deleteComment(
        DeleteContentCommentCommand(
          postId: 'post-1',
          commentId: 'comment-command-1',
        ),
      );

      _expectCommandRequest(
        captured[0],
        method: 'POST',
        path: '/content/posts/post-1/comments/comment-command-1/pin',
        operationId: AppCloudOperationIds.contentCommentPinComment,
      );
      _expectCommandRequest(
        captured[1],
        method: 'POST',
        path: '/content/posts/post-1/comments/comment-command-1/pin',
        operationId: AppCloudOperationIds.contentCommentPinComment,
      );
      _expectCommandRequest(
        captured[2],
        method: 'DELETE',
        path: '/content/posts/post-1/comments/comment-command-1/pin',
        operationId: AppCloudOperationIds.contentCommentUnpinComment,
      );
      _expectCommandRequest(
        captured[3],
        method: 'DELETE',
        path: '/content/posts/post-1/comments/comment-command-1',
        operationId: AppCloudOperationIds.contentCommentDeleteComment,
      );
      expect(pinned.id, 'comment-command-1');
      expect(pinReplay.id, pinned.id);
      expect(pinReplay.version, pinned.version);
      expect(pinReplay.replayed, isTrue);
      expect(unpinned.id, 'comment-command-1');
      expect(deleted.id, 'comment-command-1');
      expect(deleted.status, CommentStatus.deleted);
    });

    test(
      'generated decoder fails closed on an incomplete command receipt',
      () async {
        final adapter = RemoteContentCommentFacet(
          client: _client(
            (_) => <String, Object?>{
              'id': 'comment-invalid',
              'status': 'active',
              'replayed': false,
            },
          ),
          invocationContext: _context,
        );

        await expectLater(
          adapter.createComment(
            CreateContentCommentCommand(postId: 'post-1', content: 'invalid'),
          ),
          throwsA(isA<CloudException>()),
        );
      },
    );
  });
}

void _expectQueryRequest(
  http.Request request, {
  required String method,
  required String path,
  required String operationId,
  required Map<String, String> query,
}) {
  expect(request.method, method);
  expect(request.url.path, path);
  expect(request.url.queryParameters, query);
  expect(request.headers['X-Client-Operation-Id'], operationId);
  expect(request.headers['authorization'], 'Bearer comment-contract-token');
  expect(request.headers.containsKey('Idempotency-Key'), isFalse);
  expect(request.body, isEmpty);
}

void _expectCommandRequest(
  http.Request request, {
  required String method,
  required String path,
  required String operationId,
  Map<String, Object?> body = const <String, Object?>{},
}) {
  expect(request.method, method);
  expect(request.url.path, path);
  expect(request.url.queryParameters, isEmpty);
  expect(request.headers['X-Client-Operation-Id'], operationId);
  expect(request.headers['authorization'], 'Bearer comment-contract-token');
  expect(request.headers['Idempotency-Key'], 'comment-command-contract');
  expect(
    request.body.isEmpty
        ? const <String, Object?>{}
        : jsonDecode(request.body) as Map<String, dynamic>,
    body,
  );
}

Map<String, Object?> _pageResponse(
  Map<String, Object?> item, {
  String? nextCursor,
}) => <String, Object?>{
  'items': <Object?>[item],
  'nextCursor': nextCursor,
  'total': 1,
};

Map<String, Object?> _commandResponse({
  required String id,
  required int version,
  required String status,
  required bool replayed,
}) => <String, Object?>{
  'id': id,
  'version': version,
  'status': status,
  'replayed': replayed,
};

Map<String, Object?> _wireItem({
  required String id,
  String? replyToCommentId,
  String? parentCommentId,
  int replyCount = 0,
  List<Object?> replyPreview = const <Object?>[],
  String? replyNextCursor,
}) => <String, Object?>{
  'id': id,
  'version': 3,
  'postId': 'post-1',
  'authorId': 'persona-1',
  'authorDisplayNameSnapshot': 'comment author',
  'authorAvatarUrlSnapshot': 'https://cdn.example.com/avatar.jpg',
  'personaContextVersion': 7,
  'content': 'typed comment projection',
  'replyToCommentId': replyToCommentId,
  'replyToUserId': replyToCommentId == null ? null : 'persona-root',
  'parentCommentId': parentCommentId,
  'attachmentMediaIds': <String>['media-1'],
  'attachments': <Object?>[
    <String, Object?>{
      'mediaId': 'media-1',
      'mediaType': 'image',
      'url': 'https://cdn.example.com/media-1.jpg',
      'width': 1200,
      'height': 800,
      'available': true,
    },
  ],
  'mentions': <Object?>[],
  'assistantMentioned': false,
  'assistantReplySource': null,
  'assistantCorrectionStatus': null,
  'status': 'active',
  'isPinned': false,
  'pinnedAt': null,
  'createdAt': '2026-08-08T08:00:00Z',
  'updatedAt': '2026-08-08T08:01:00Z',
  'deletedAt': null,
  'replyCount': replyCount,
  'replyPreview': replyPreview,
  'replyNextCursor': replyNextCursor,
  'likeCount': 3,
  'dislikeCount': 1,
  'viewerReaction': 'like',
  'authorLiked': true,
  'viewerRelation': 'following',
  'isAuthor': true,
  'canDelete': true,
  'canReply': true,
  'canReport': false,
  'canPin': true,
};

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
      authTokenProvider: const _CommentTokenProvider(),
    ),
    clientContextProvider: const _CommentClientContext(),
    telemetrySink: const _NoopTelemetrySink(),
    environment: CloudRuntimeEnvironment(
      environment: CloudEnvironment.gamma,
      gatewayBaseUri: Uri.parse('https://test-gateway.example.com'),
    ),
  );
}

CloudOperationInvocationContext _context(
  String clientPageId, {
  required bool command,
}) {
  final profileReader =
      clientPageId == ContentRequestPageIds.listCommentsByAuthor ||
      clientPageId == ContentRequestPageIds.listCommentsForPostAuthor;
  return CloudOperationInvocationContext(
    surfaceId: profileReader ? 'profileHome' : 'workBrowser',
    routeId: profileReader ? 'profileHome' : 'workBrowser',
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(personaId: 'persona-1'),
    idempotencyKey: command ? 'comment-command-contract' : null,
  );
}

final class _CommentClientContext implements CloudClientContextProvider {
  const _CommentClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'comment-contract-session',
      deviceActorId: 'comment-contract-device',
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

final class _CommentTokenProvider implements CloudAuthTokenProvider {
  const _CommentTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'comment-contract-token';
}
