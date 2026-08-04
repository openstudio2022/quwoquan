import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/content/content/feed_delivery_page/domain/discovery_feed_page.dart';
import 'package:quwoquan_app/content/content/post/application/content_repository_contract.dart'
    as app;
import 'package:quwoquan_app/cloud/services/content/remote/content_post_projection_mapper.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;

typedef ContentDiscoveryFeedInvocationContextFactory =
    contracts.CloudOperationInvocationContext Function(String clientPageId);

/// 首页发现流的正式远端 Query。
///
/// 请求编码、响应解码与 transport 仅由 GeneratedCloudOperationClient 负责；本层
/// 只保留频道语义归一化和 App DTO 投影。
final class RemoteContentDiscoveryFeedQuery
    implements app.ContentDiscoveryFeedQuery {
  const RemoteContentDiscoveryFeedQuery({
    required this.client,
    required this.invocationContext,
    required this.blockedKeywordsLoader,
    this.projectionMapper = const ContentPostProjectionMapper(),
  });

  final contracts.GeneratedCloudOperationClient client;
  final ContentDiscoveryFeedInvocationContextFactory invocationContext;
  final Future<List<String>> Function() blockedKeywordsLoader;
  final ContentPostProjectionMapper projectionMapper;

  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
    String sort = app.kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
    contracts.CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final baseInvocation = invocationContext(ContentRequestPageIds.getFeed);
    final effectiveCancellation = cancellation ?? baseInvocation.cancellation;
    final effectiveDeadlineAt = deadlineAt ?? baseInvocation.deadlineAt;
    contracts.throwIfCloudOperationInterrupted(
      cancellation: effectiveCancellation,
      deadlineAt: effectiveDeadlineAt,
    );
    final resolvedChannelId = channelId?.trim() ?? '';
    final channelRouted = resolvedChannelId.isNotEmpty;
    final resolvedIdentity = channelRouted
        ? null
        : (identity ?? _mapCategoryToIdentity(category));
    final resolvedType = channelRouted
        ? null
        : _normalizeFeedType(
            type ??
                GeneratedPostRuntimeMetadata
                    .feedCategoryToRequestType[category],
          );
    final blockedKeywords =
        (await contracts.runCloudOperationPrerequisite(
              blockedKeywordsLoader,
              cancellation: effectiveCancellation,
              deadlineAt: effectiveDeadlineAt,
            ))
            .map((keyword) => keyword.trim())
            .where((keyword) => keyword.isNotEmpty)
            .toSet()
            .toList(growable: false);
    contracts.throwIfCloudOperationInterrupted(
      cancellation: effectiveCancellation,
      deadlineAt: effectiveDeadlineAt,
    );
    final normalizedFeedRequestId = feedRequestId?.trim();
    final response = await client.contentPostGetFeed(
      contracts.ContentDiscoveryFeedQuery(
        identity: resolvedIdentity,
        type: resolvedIdentity == 'moment' && (type == null || type.isEmpty)
            ? null
            : resolvedType,
        sort: sort,
        cursor: cursor,
        subCategory: subCategory,
        channelId: channelRouted ? resolvedChannelId : null,
        sessionId: sessionId,
        feedRequestId: normalizedFeedRequestId,
        limit: limit,
        blockedKeywords: blockedKeywords,
      ),
      context: contracts.CloudOperationInvocationContext(
        surfaceId: baseInvocation.surfaceId,
        clientPageId: baseInvocation.clientPageId,
        actor: baseInvocation.actor,
        routeId: baseInvocation.routeId,
        referralSource: baseInvocation.referralSource,
        feedRequestId: normalizedFeedRequestId?.isNotEmpty == true
            ? normalizedFeedRequestId
            : baseInvocation.feedRequestId,
        shareId: baseInvocation.shareId,
        modelId: baseInvocation.modelId,
        experimentBucket: baseInvocation.experimentBucket,
        idempotencyKey: baseInvocation.idempotencyKey,
        deadlineAt: effectiveDeadlineAt,
        cancellation: effectiveCancellation,
      ),
    );
    return DiscoveryFeedPage(
      items: response.items.map(projectionMapper.toDto).toList(growable: false),
      outcome: response.outcome,
      emptyReason: response.emptyReason,
      objectCards: response.objectCards,
      nextCursor: response.nextCursor,
      previousCursor: response.previousCursor,
      paginationExpiresAt: response.paginationExpiresAt,
      feedRequestId: response.feedRequestId,
      policyDigest: response.policyDigest,
    );
  }

  String? _mapCategoryToIdentity(String category) {
    switch (category.trim()) {
      case 'moment':
      case 'recommended':
      case 'following':
        return 'moment';
      case 'work':
      case 'works':
      case 'photo':
      case 'images':
      case 'video':
      case 'article':
        return 'work';
      default:
        return null;
    }
  }

  String? _normalizeFeedType(String? type) {
    final normalized = (type ?? '').trim().toLowerCase();
    switch (normalized) {
      case '':
        return null;
      case 'photo':
        return 'image';
      case 'note':
        return 'article';
      default:
        return normalized;
    }
  }
}
