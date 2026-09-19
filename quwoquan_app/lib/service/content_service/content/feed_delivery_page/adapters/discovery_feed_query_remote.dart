import 'package:quwoquan_app/runtime/transport/generated/client_content_presentation_contract.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/content_activation_identity.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_page.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_query.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/generated/content_feed_delivery_category_policy.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_list_item_decoder.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_list_item_skew_observer.dart';
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
    this.listItemDecoder = const ContentListItemDecoder(),
    this.skewObserver = const ContentListItemSkewObserver(),
  });

  final contracts.GeneratedCloudOperationClient client;
  final ContentDiscoveryFeedInvocationContextFactory invocationContext;
  final Future<List<String>> Function() blockedKeywordsLoader;
  final ContentListItemDecoder listItemDecoder;
  final ContentListItemSkewObserver skewObserver;

  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
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
        // 能力闭集与端侧编译期真实支持同源生成；不手写数组或摘要。
        clientPresentationContract: compiledContentPresentationContract,
        type: resolvedType,
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
    // 逐项解码：未知或不支持项就地隔离并留观测，已知项保持交付序位继续渲染。
    final decoding = listItemDecoder.decode(response.items);
    skewObserver.record(
      decoding.isolated,
      operationId: contracts.AppCloudOperationIds.contentPostGetFeed,
    );
    return DiscoveryFeedPage(
      items: decoding.posts,
      outcome: response.outcome,
      emptyReason: response.emptyReason,
      objectCards: decoding.objectCards,
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
      default:
        return normalized;
    }
  }
}
