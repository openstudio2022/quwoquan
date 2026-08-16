import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('generated report method encodes only typed business command', () async {
    final executor = _RecordingExecutor(
      response: <String, Object?>{
        'id': 'report-1',
        'version': 1,
        'status': 'pending',
        'replayed': false,
      },
    );
    final client = GeneratedCloudOperationClient(executor);

    await client.contentReportCreateReport(
      CreateContentReportCommand(
        targetId: 'post-1',
        targetType: ReportTargetType.post,
        reason: ReportReason.spam,
      ),
      context: const CloudOperationInvocationContext(
        surfaceId: 'contentDetail',
        clientPageId: 'content.report',
        actor: CloudOperationActorContext(personaId: 'persona-1'),
      ),
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.contentReportCreateReport,
    );
    expect(executor.body, <String, Object?>{
      'targetId': 'post-1',
      'targetType': 'post',
      'reason': 'spam',
    });
  });

  test('generated my reports method uses private typed query ABI', () async {
    final executor = _RecordingExecutor(
      response: <String, Object?>{
        'items': <Object?>[
          <String, Object?>{
            'id': 'report-1',
            'targetType': 'post',
            'targetId': 'post-1',
            'reason': 'spam',
            'status': 'pending',
            'createdAt': '2026-07-20T00:00:00Z',
            'updatedAt': '2026-07-20T00:00:00Z',
          },
        ],
      },
    );
    final client = GeneratedCloudOperationClient(executor);

    final page = await client.contentReportListMyReports(
      ContentMyReportsQuery(limit: 10),
      context: const CloudOperationInvocationContext(
        surfaceId: 'myReports',
        clientPageId: 'content.list.my.reports',
        actor: CloudOperationActorContext(personaId: 'persona-1'),
      ),
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.contentReportListMyReports,
    );
    expect(executor.queryParameters, <String, String>{'limit': '10'});
    expect(page.items.single.status, ReportStatus.pending);
  });

  test(
    'generated location method returns typed Slice without adapter cast',
    () async {
      final executor = _RecordingExecutor(
        response: <String, Object?>{
          'items': <Object?>[
            <String, Object?>{
              'id': 'poi-1',
              'name': '咖啡馆',
              'latitude': 31.2,
              'longitude': 121.5,
            },
          ],
        },
      );
      final client = GeneratedCloudOperationClient(executor);

      final result = await client.integrationLocationSearchLocations(
        const LocationSearchQueryParams(query: '咖啡', limit: 10),
        context: const CloudOperationInvocationContext(
          surfaceId: 'createWorkspace',
          clientPageId: 'location.search',
          actor: CloudOperationActorContext(),
        ),
      );

      expect(result.items.single.id, 'poi-1');
      expect(executor.queryParameters, <String, String>{
        'q': '咖啡',
        'limit': '10',
      });
    },
  );

  test(
    'generated canonical search method encodes typed query and decodes view',
    () async {
      final executor = _RecordingExecutor(
        response: <String, Object?>{
          'interpretedQuery': <String, Object?>{
            'normalized': '西湖',
            'tokens': <String>['西湖'],
            'variants': <String>[],
            'detectedEntities': <String>[],
            'detectedTags': <String>[],
            'selectedObjectTypes': <String>['article'],
          },
          'hits': <Object?>[
            <String, Object?>{
              'target': 'article',
              'objectType': 'content.post',
              'objectId': 'post-1',
              'title': '西湖摄影',
              'score': 1,
              'matchedTerms': <String>['西湖'],
              'matchedTags': <String>[],
              'evidence': <Object?>[],
              'rankReasons': <Object?>[],
              'content': <String, Object?>{
                'postId': 'post-1',
                'contentType': 'article',
                'contentIdentity': 'work',
                'title': '西湖摄影',
                'likeCount': 3,
              },
            },
          ],
          'citations': <Object?>[],
          'facets': <Object?>[],
          'requestId': 'search-request-1',
          'relatedTerms': <Object?>[],
          'degradeSignals': <Object?>[],
          'provenance': <String, Object?>{
            'provider': 'elasticsearch',
            'generatedAt': '2026-07-31T00:00:00Z',
          },
        },
      );
      final client = GeneratedCloudOperationClient(executor);

      final result = await client.searchSearchIndexViewSearch(
        CanonicalSearchQuery(
          query: '西湖',
          objectTypes: const <String>['article'],
          limit: 10,
        ),
        context: const CloudOperationInvocationContext(
          surfaceId: 'globalSearchNetworkResults',
          clientPageId: 'search.query',
          actor: CloudOperationActorContext(personaId: 'persona-1'),
        ),
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.searchSearchIndexViewSearch,
      );
      expect(executor.body, <String, Object?>{
        'query': '西湖',
        'mode': 'result',
        'objectTypes': <String>['article'],
        'limit': 10,
      });
      expect(result.hits.single.objectId, 'post-1');
      expect(result.hits.single.content?.title, '西湖摄影');
    },
  );

  test('generated feed method preserves typed attribution context', () async {
    final policyDigest = _fixtureSha256('content-feed-policy');
    final executor = _RecordingExecutor(
      response: <String, Object?>{
        'items': <Object?>[
          <String, Object?>{
            'postId': 'post-1',
            'contentType': 'article',
            'title': '西湖行记',
            'likeCount': 0,
            'commentCount': 0,
            'shareCount': 0,
          },
        ],
        'objectCards': <Object?>[
          <String, Object?>{
            'objectKind': 'entity',
            'objectId': 'west-lake',
            'title': '西湖',
            'tagRefs': <String>[],
            'anchorIndex': 0,
          },
        ],
        'nextCursor': 'cursor-2',
        'previousCursor': 'cursor-0',
        'paginationExpiresAt': '2026-07-29T12:00:00Z',
        'feedRequestId': 'feed-request-1',
        'policyDigest': policyDigest,
        'outcome': 'content',
      },
    );
    final client = GeneratedCloudOperationClient(executor);

    final result = await client.contentPostGetFeed(
      ContentDiscoveryFeedQuery(
        channelId: 'travel',
        feedRequestId: 'feed-request-1',
        blockedKeywords: const <String>['广告'],
      ),
      context: const CloudOperationInvocationContext(
        surfaceId: 'homeFeed',
        clientPageId: 'content.feed.list',
        actor: CloudOperationActorContext(),
      ),
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.contentPostGetFeed,
    );
    expect(executor.queryParameters, <String, String>{
      'channelId': 'travel',
      'feedRequestId': 'feed-request-1',
      'limit': '20',
    });
    expect(executor.headers['X-Blocked-Keywords'], '%E5%B9%BF%E5%91%8A');
    expect(result.items.single.postId, 'post-1');
    expect(result.objectCards, hasLength(1));
    expect(result.nextCursor, 'cursor-2');
    expect(result.previousCursor, 'cursor-0');
    expect(result.paginationExpiresAt, DateTime.utc(2026, 7, 29, 12));
    expect(result.feedRequestId, 'feed-request-1');
    expect(result.policyDigest, policyDigest);
    expect(result.outcome, ContentFeedOutcome.content);
  });

  test('generated footprint method decodes typed private page', () async {
    final executor = _RecordingExecutor(
      response: <String, Object?>{
        'items': <Object?>[
          <String, Object?>{
            'postId': 'post-1',
            'action': 'click',
            'occurredAt': '2026-07-13T09:00:00Z',
            'post': <String, Object?>{
              'postId': 'post-1',
              'contentType': 'image',
              'title': '足迹内容',
              'authorDisplayName': '作者',
              'likeCount': 0,
              'commentCount': 0,
              'shareCount': 0,
            },
          },
        ],
        'nextCursor': '2026-07-13T08:00:00Z',
      },
    );
    final client = GeneratedCloudOperationClient(executor);

    final result = await client.contentPostGetMyFootprint(
      ContentFootprintQuery(type: 'viewed', limit: 10),
      context: const CloudOperationInvocationContext(
        surfaceId: 'myFootprint',
        clientPageId: 'content.post.footprint',
        actor: CloudOperationActorContext(personaId: 'persona-1'),
      ),
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.contentPostGetMyFootprint,
    );
    expect(executor.queryParameters, <String, String>{
      'type': 'viewed',
      'limit': '10',
    });
    expect(result.items.single.post?.title, '足迹内容');
    expect(result.nextCursor, '2026-07-13T08:00:00Z');
  });

  test(
    'generated getPost method encodes path and decodes typed detail slice',
    () async {
      final executor = _RecordingExecutor(
        response: <String, Object?>{
          'postId': 'post-1',
          'contentType': 'article',
          'title': '西湖摄影',
          'body': '正文',
          'authorId': 'author-1',
          'authorDisplayName': '作者',
          'status': 'published',
          'visibility': 'public',
          'likeCount': 0,
          'commentCount': 0,
          'shareCount': 0,
          'viewCount': 0,
          'createdAt': '2026-07-31T00:00:00Z',
          'updatedAt': '2026-07-31T00:00:00Z',
          'articleMarkdown': '# 西湖摄影',
          'articleAssetManifest': <String, Object?>{
            'schema': 'article-asset-manifest',
            'articleMarkdownDigest': _fixtureSha256('# 西湖摄影'),
            'documentSha256': _fixtureSha256('article-document'),
            'assetManifestSha256': _fixtureSha256('article-assets'),
            'documentVersionSha256': _fixtureSha256('article-version'),
            'assets': <Object?>[],
          },
        },
      );
      final client = GeneratedCloudOperationClient(executor);

      final result = await client.contentPostGetPost(
        ContentPostDetailQuery(postId: 'post-1'),
        context: const CloudOperationInvocationContext(
          surfaceId: 'workBrowser',
          clientPageId: 'content.post.get',
          actor: CloudOperationActorContext(),
        ),
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.contentPostGetPost,
      );
      expect(executor.pathParameters, <String, String>{'postId': 'post-1'});
      expect(result.postId, 'post-1');
      expect(result.articleMarkdown, '# 西湖摄影');
      expect(result.articleAssetManifest, isA<PostArticleAssetManifest>());
    },
  );

  test('generated ListUserPosts method decodes typed author page', () async {
    final executor = _RecordingExecutor(
      response: <String, Object?>{
        'items': <Object?>[
          <String, Object?>{
            'postId': 'post-1',
            'contentType': 'image',
            'authorId': 'author-1',
            'mediaUrls': <String>['https://example.test/p.jpg'],
            'likeCount': 0,
            'commentCount': 0,
            'shareCount': 0,
          },
        ],
        'nextCursor': 'cursor-2',
        'hasMore': true,
      },
    );
    final client = GeneratedCloudOperationClient(executor);

    final result = await client.contentPostListUserPosts(
      ContentAuthorPostsQuery(
        personaId: 'author-1',
        identity: 'work',
        type: 'image',
        visibility: 'public',
        limit: 10,
      ),
      context: const CloudOperationInvocationContext(
        surfaceId: 'userProfile',
        clientPageId: 'content.user.posts',
        actor: CloudOperationActorContext(),
      ),
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.contentPostListUserPosts,
    );
    expect(executor.pathParameters, <String, String>{'personaId': 'author-1'});
    expect(executor.queryParameters, <String, String>{
      'identity': 'work',
      'type': 'image',
      'visibility': 'public',
      'limit': '10',
    });
    expect(result.items.single.postId, 'post-1');
    expect(result.nextCursor, 'cursor-2');
    expect(result.hasMore, isTrue);
  });

  test('generated SubmitPostPublication is one typed atomic command', () async {
    final executor = _RecordingExecutor(
      response: <String, Object?>{
        'publishIntentId': 'publish-draft-1',
        'localDraftId': 'draft-1',
        'postId': 'post-created',
        'state': 'published',
        'committedVersion': 1,
        'acceptedAt': '2026-07-13T10:00:00Z',
      },
    );
    final client = GeneratedCloudOperationClient(executor);

    final result = await client.contentPostSubmitPostPublication(
      SubmitContentPostPublicationCommand(
        publishIntentId: 'publish-draft-1',
        localDraftId: 'draft-1',
        contentType: ContentType.article,
        contentIdentity: ContentIdentity.work,
        title: '对象闭环',
        articleMarkdown: '# 对象闭环',
        articleAssetManifest: PostArticleAssetManifestInput(
          schema: 'article-asset-manifest',
          assets: const <PostArticleAssetInput>[],
        ),
        mediaAssetIds: const <String>['asset-1'],
        visibility: Visibility.public,
      ),
      context: const CloudOperationInvocationContext(
        surfaceId: 'createWorkspace',
        clientPageId: 'content.post.publish',
        actor: CloudOperationActorContext(personaId: 'persona-1'),
        idempotencyKey: 'publish-draft-1',
      ),
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.contentPostSubmitPostPublication,
    );
    expect(executor.pathParameters, isEmpty);
    expect(executor.body, <String, Object?>{
      'publishIntentId': 'publish-draft-1',
      'localDraftId': 'draft-1',
      'contentType': 'article',
      'contentIdentity': 'work',
      'title': '对象闭环',
      'mediaAssetIds': <String>['asset-1'],
      'articleMarkdown': '# 对象闭环',
      'articleAssetManifest': <String, Object?>{
        'schema': 'article-asset-manifest',
        'assets': <Object?>[],
      },
      'captureDisclosure': <String>[],
      'visibility': 'public',
    });
    expect(result.postId, 'post-created');
    expect(result.acceptedAt, DateTime.utc(2026, 7, 13, 10));
  });

  test(
    'generated OutboundShare appends only confirmed immutable fact',
    () async {
      final executor = _RecordingExecutor(
        response: <String, Object?>{
          'eventId': 'share-event-1',
          'postId': 'post-1',
          'channel': 'system_share',
          'referralId': 'referral-1',
          'occurredAt': '2026-07-14T10:00:00Z',
          'replayed': false,
        },
      );
      final client = GeneratedCloudOperationClient(executor);

      final result = await client
          .contentOutboundShareFactAppendOutboundShareFact(
            CreateContentOutboundShareCommand(
              postId: 'post-1',
              channel: OutboundShareChannel.systemShare,
              destinationKind: OutboundShareDestinationKind.externalApp,
              destination: 'wechat',
              referralId: 'referral-1',
              providerReceiptId: 'provider-receipt-1',
              clientConfirmedAt: DateTime.utc(2026, 7, 14, 10),
            ),
            context: const CloudOperationInvocationContext(
              surfaceId: 'homeFeed',
              clientPageId: 'content.create.outbound.share',
              actor: CloudOperationActorContext(personaId: 'persona-1'),
              idempotencyKey: 'outbound-share-referral-1',
            ),
          );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.contentOutboundShareFactAppendOutboundShareFact,
      );
      expect(executor.pathParameters, <String, String>{'postId': 'post-1'});
      expect(executor.body, <String, Object?>{
        'channel': 'system_share',
        'destinationKind': 'external_app',
        'destination': 'wechat',
        'referralId': 'referral-1',
        'deliverySucceeded': true,
        'providerReceiptId': 'provider-receipt-1',
        'clientConfirmedAt': '2026-07-14T10:00:00.000Z',
      });
      expect(result.eventId, 'share-event-1');
    },
  );

  test('generated Circle placement does not mutate Post ownership', () async {
    final executor = _RecordingExecutor(
      response: <String, Object?>{
        'placementId': 'placement-1',
        'version': 1,
        'state': 'active',
        'idempotentReplay': false,
      },
    );
    final client = GeneratedCloudOperationClient(executor);

    await client.circleCirclePostPlacementPlacePostInCircle(
      PlaceCirclePostCommand(
        circleId: 'circle-1',
        postId: 'post-1',
        groupId: 'group-1',
      ),
      context: const CloudOperationInvocationContext(
        surfaceId: 'homeFeed',
        clientPageId: 'circle.place.post.in.circle',
        actor: CloudOperationActorContext(personaId: 'persona-1'),
        idempotencyKey: 'circle-placement-1',
      ),
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.circleCirclePostPlacementPlacePostInCircle,
    );
    expect(executor.pathParameters, <String, String>{'circleId': 'circle-1'});
    expect(executor.body, <String, Object?>{
      'postId': 'post-1',
      'groupId': 'group-1',
    });
  });

  test('generated Notification client encodes typed inbox query', () async {
    final executor = _RecordingExecutor(
      response: <String, Object?>{
        'items': <Object?>[_appMessageResponse()],
        'nextCursor': 'cursor-2',
      },
    );
    final client = GeneratedCloudOperationClient(executor);

    final result = await client.notificationNotificationListAppMessages(
      ListAppMessagesQuery(messageType: 'assistant', read: false, limit: 10),
      context: const CloudOperationInvocationContext(
        surfaceId: 'personalAssistantDialog',
        clientPageId: 'notification.list.app.messages',
        actor: CloudOperationActorContext(accountId: 'account-1'),
      ),
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.notificationNotificationListAppMessages,
    );
    expect(executor.queryParameters, <String, String>{
      'type': 'assistant',
      'read': 'false',
      'limit': '10',
    });
    expect(result.items.single.messageId, 'msg-1');
    expect(result.nextCursor, 'cursor-2');
  });

  test('Notification decoder rejects aliases and unknown fields', () {
    final aliased = _appMessageResponse()
      ..remove('messageId')
      ..['id'] = 'msg-1';
    expect(() => decodeAppMessage(aliased), throwsA(isA<FormatException>()));

    final unknown = _appMessageResponse()
      ..['unsupportedActionUrl'] = '/unsupported';
    expect(() => decodeAppMessage(unknown), throwsA(isA<FormatException>()));

    final invalidType = _appMessageResponse()..['messageType'] = 'entity';
    expect(
      () => decodeAppMessage(invalidType),
      throwsA(isA<FormatException>()),
    );
  });
}

String _fixtureSha256(String payload) =>
    'sha256:${sha256.convert(utf8.encode(payload))}';

Map<String, Object?> _appMessageResponse() {
  return <String, Object?>{
    'messageId': 'msg-1',
    'userId': 'account-1',
    'messageType': 'assistant',
    'source': 'assistant_turn',
    'sourceId': 'turn-1',
    'destination': <String, Object?>{'type': 'user', 'id': 'account-1'},
    'title': '提醒',
    'summary': '有一条新消息',
    'target': <String, Object?>{
      'targetType': 'assistant_turn',
      'targetId': 'turn-1',
      'routeId': 'assistantPersonal',
      'routePath': '/assistant/personal',
      'query': <String, Object?>{},
    },
    'read': false,
    'createdAt': '2026-07-13T10:00:00Z',
  };
}

final class _RecordingExecutor implements CloudOperationExecutor {
  _RecordingExecutor({this.response});

  final Object? response;
  CloudOperationContract? operation;
  Map<String, String> pathParameters = const <String, String>{};
  Map<String, String> queryParameters = const <String, String>{};
  Map<String, String> headers = const <String, String>{};
  Object? body;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    final payload = requestEncoder();
    pathParameters = payload.pathParameters;
    queryParameters = payload.queryParameters;
    headers = payload.headers;
    body = payload.body;
    return responseDecoder(response);
  }
}
