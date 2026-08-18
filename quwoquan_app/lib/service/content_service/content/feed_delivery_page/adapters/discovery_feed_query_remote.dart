import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/content_activation_identity.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_page.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_query.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/generated/content_feed_delivery_category_policy.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_projection_mapper.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;

typedef ContentDiscoveryFeedInvocationContextFactory =
    contracts.CloudOperationInvocationContext Function(String clientPageId);

/// 首页发现流的正式远端 Query。
///
/// 请求编码、响应解码与 transport 仅由 GeneratedCloudOperationClient 负责；本层
/// 只保留频道语义归一化和 App DTO 投影。
final class RemoteContentDiscoveryFeedQuery
    implements ContentDiscoveryFeedQuery {
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
    int limit = contracts.ContentDiscoveryFeedQuery.defaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
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
        : (identity ??
              DiscoveryFeedRouteRegistry.identityForCategory(category));
    final resolvedType = channelRouted
        ? null
        : _normalizeFeedType(
            type ??
                ContentFeedDeliveryCategoryPolicy
                    .requestTypeByCategory[category],
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
    // malformed 身份（半身份 / 非 canonical digest / no_active_release 却携带
    // 身份）与解码失败同路径向上抛：这是 Remote 协议失败，不得编码为空态。
    final activationIdentity = resolveContentActivationIdentity(
      releaseId: response.releaseId,
      manifestDigest: response.manifestDigest,
      emptyReason: response.emptyReason,
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
      activationIdentity: activationIdentity,
    );
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
