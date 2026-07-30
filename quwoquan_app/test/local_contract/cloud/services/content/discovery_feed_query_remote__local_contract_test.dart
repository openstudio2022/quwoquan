// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-014
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/services/content/remote/discovery_feed_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('RemoteContentDiscoveryFeedQuery', () {
    test('请求级取消、期限和 feed 归因覆盖基底且保留页面身份', () async {
      final executor = _RecordingExecutor();
      final requestCancellation = CloudOperationCancellationSignal();
      final baseCancellation = CloudOperationCancellationSignal();
      final now = DateTime.now();
      final requestDeadline = now.add(const Duration(seconds: 6));
      final baseDeadline = now.add(const Duration(seconds: 30));
      final actor = const CloudOperationActorContext(
        accountId: 'account-1',
        personaId: 'persona-1',
      );
      String? requestedClientPageId;
      final query = RemoteContentDiscoveryFeedQuery(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId) {
          requestedClientPageId = clientPageId;
          return CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.homeFeed.id,
            routeId: AppUiSurfaces.homeFeed.routeId,
            clientPageId: clientPageId,
            actor: actor,
            referralSource: 'homeRecommend',
            feedRequestId: 'base-feed-request',
            shareId: 'share-1',
            modelId: 'model-1',
            experimentBucket: 'bucket-1',
            idempotencyKey: 'base-idempotency',
            deadlineAt: baseDeadline,
            cancellation: baseCancellation,
          );
        },
        blockedKeywordsLoader: () async => const <String>[
          ' blocked-one ',
          '',
          'blocked-one',
          'blocked-two',
        ],
      );

      final page = await query.listDiscoveryFeedPage(
        category: 'recommend',
        channelId: ' recommend ',
        subCategory: 'local',
        sessionId: 'session-1',
        feedRequestId: ' feed-request-1 ',
        cancellation: requestCancellation,
        deadlineAt: requestDeadline,
      );

      expect(requestedClientPageId, ContentRequestPageIds.getFeed);
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.contentPostGetFeed,
      );
      expect(executor.context?.surfaceId, AppUiSurfaces.homeFeed.id);
      expect(executor.context?.routeId, AppUiSurfaces.homeFeed.routeId);
      expect(executor.context?.clientPageId, ContentRequestPageIds.getFeed);
      expect(executor.context?.actor, same(actor));
      expect(executor.context?.referralSource, 'homeRecommend');
      expect(executor.context?.feedRequestId, 'feed-request-1');
      expect(executor.context?.shareId, 'share-1');
      expect(executor.context?.modelId, 'model-1');
      expect(executor.context?.experimentBucket, 'bucket-1');
      expect(executor.context?.idempotencyKey, 'base-idempotency');
      expect(executor.context?.deadlineAt, same(requestDeadline));
      expect(executor.context?.cancellation, same(requestCancellation));
      expect(executor.queryParameters, <String, String>{
        'sort': 'recommend',
        'subCategory': 'local',
        'channelId': 'recommend',
        'sessionId': 'session-1',
        'feedRequestId': 'feed-request-1',
        'limit': '20',
      });
      expect(executor.headers['X-Blocked-Keywords'], 'blocked-one,blocked-two');
      expect(page.feedRequestId, 'server-feed-request');
      expect(page.nextCursor, 'cursor-2');
      expect(page.previousCursor, 'cursor-0');
      expect(page.paginationExpiresAt, DateTime.utc(2026, 7, 29, 12));
    });

    test('调用方未覆盖时保留基底 cancellation、deadline 与 feed 归因', () async {
      final executor = _RecordingExecutor();
      final baseCancellation = CloudOperationCancellationSignal();
      final baseDeadline = DateTime.now().add(const Duration(minutes: 1));
      final query = RemoteContentDiscoveryFeedQuery(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.homeFeed.id,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(),
          feedRequestId: 'base-feed-request',
          deadlineAt: baseDeadline,
          cancellation: baseCancellation,
        ),
        blockedKeywordsLoader: () async => const <String>[],
      );

      await query.listDiscoveryFeedPage(category: 'photo');

      expect(executor.context?.feedRequestId, 'base-feed-request');
      expect(executor.context?.deadlineAt, same(baseDeadline));
      expect(executor.context?.cancellation, same(baseCancellation));
    });

    test('发送前取消会终止异步配置读取且不进入 generated executor', () async {
      final executor = _RecordingExecutor();
      final cancellation = CloudOperationCancellationSignal();
      final keywords = Completer<List<String>>();
      final query = RemoteContentDiscoveryFeedQuery(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.homeFeed.id,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(),
        ),
        blockedKeywordsLoader: () => keywords.future,
      );

      final pending = query.listDiscoveryFeedPage(
        category: 'recommend',
        cancellation: cancellation,
      );
      cancellation.cancel();

      await expectLater(
        pending.timeout(const Duration(seconds: 1)),
        throwsA(isA<CloudOperationCancelledException>()),
      );
      expect(executor.sendCount, 0);

      keywords.complete(const <String>[]);
      await Future<void>.delayed(Duration.zero);
      expect(executor.sendCount, 0);
    });

    test('异步配置读取永久阻塞时由请求期限终止且不发送', () async {
      final executor = _RecordingExecutor();
      final keywords = Completer<List<String>>();
      final query = RemoteContentDiscoveryFeedQuery(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.homeFeed.id,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(),
        ),
        blockedKeywordsLoader: () => keywords.future,
      );

      final pending = query.listDiscoveryFeedPage(
        category: 'recommend',
        deadlineAt: DateTime.now().add(const Duration(milliseconds: 20)),
      );

      await expectLater(
        pending.timeout(const Duration(seconds: 1)),
        throwsA(isA<TimeoutException>()),
      );
      expect(executor.sendCount, 0);
    });

    test('开始前已取消时不读取配置也不进入 generated executor', () async {
      final executor = _RecordingExecutor();
      final cancellation = CloudOperationCancellationSignal()..cancel();
      var loaderCallCount = 0;
      final query = RemoteContentDiscoveryFeedQuery(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.homeFeed.id,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(),
        ),
        blockedKeywordsLoader: () async {
          loaderCallCount += 1;
          return const <String>[];
        },
      );

      await expectLater(
        query.listDiscoveryFeedPage(
          category: 'recommend',
          cancellation: cancellation,
        ),
        throwsA(isA<CloudOperationCancelledException>()),
      );
      expect(loaderCallCount, 0);
      expect(executor.sendCount, 0);
    });
  });
}

final class _RecordingExecutor implements CloudOperationExecutor {
  int sendCount = 0;
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Map<String, String> queryParameters = const <String, String>{};
  Map<String, String> headers = const <String, String>{};

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    sendCount += 1;
    this.operation = operation;
    this.context = context;
    final payload = requestEncoder();
    queryParameters = payload.queryParameters;
    headers = payload.headers;
    return responseDecoder(<String, Object?>{
      'items': const <Object?>[
        <String, Object?>{'postId': 'post-1'},
      ],
      'outcome': 'content',
      'objectCards': const <Object?>[],
      'nextCursor': 'cursor-2',
      'previousCursor': 'cursor-0',
      'paginationExpiresAt': '2026-07-29T12:00:00Z',
      'feedRequestId': 'server-feed-request',
      'policyDigest':
          'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'hasMore': true,
    });
  }
}
