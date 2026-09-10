import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/config/offline_content_failure.dart';
import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_page.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_query.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_projection_mapper.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;

/// 消费 producer 封存的频道选择；不模拟在线推荐、登录或服务 activation。
final class BundledContentDiscoveryFeedQuery
    implements ContentDiscoveryFeedQuery {
  BundledContentDiscoveryFeedQuery({required this.loadBundle});
  final Future<OfflineContentBundle> Function() loadBundle;
  Future<OfflineContentBundle>? _bundle;

  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    required int limit,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
    contracts.CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final readBudgetDeadline = DateTime.now().add(const Duration(seconds: 6));
    final effectiveDeadline =
        deadlineAt == null || deadlineAt.isAfter(readBudgetDeadline)
        ? readBudgetDeadline
        : deadlineAt;
    contracts.throwIfCloudOperationInterrupted(
      cancellation: cancellation,
      deadlineAt: effectiveDeadline,
    );
    if (limit < 1 || limit > 100) {
      throw const OfflineContentFailure('bundle_query_limit_invalid');
    }
    if (channelId == 'following' ||
        category == 'following' ||
        sort != kFeedSortRecommend) {
      throw contentCapabilityUnavailable('personalized_feed');
    }
    final bundle = await contracts.runCloudOperationPrerequisite(
      () => _bundle ??= loadBundle().catchError((Object error) {
        _bundle = null;
        throw error;
      }),
      cancellation: cancellation,
      deadlineAt: effectiveDeadline,
    );
    final posts = {
      for (final row in bundle.rows('posts'))
        (row['projection']! as Map<String, Object?>)['postId']!
            as String: contracts.ContentPostProjection.fromWire(
          row['projection']! as Map<String, Object?>,
        ),
    };
    final channel = (channelId ?? '').trim();
    final selectedIdentity = channel.isNotEmpty
        ? null
        : identity ?? DiscoveryFeedRouteRegistry.identityForCategory(category);
    final selectedType = channel.isNotEmpty
        ? null
        : type ?? DiscoveryFeedRouteRegistry.routeForSurface(category)?.type;
    Iterable<contracts.ContentPostProjection> selected = posts.values;
    if (channel.isNotEmpty) {
      final channels = bundle
          .rows('channels')
          .where((row) => row['channelId'] == channel);
      selected = channels.isEmpty
          ? const []
          : (channels.single['orderedPostIds']! as List).map(
              (id) =>
                  posts[id] ??
                  (throw const OfflineContentFailure(
                    'bundle_post_reference_invalid',
                  )),
            );
    } else {
      selected = selected.where(
        (post) =>
            (selectedIdentity == null ||
                post.contentIdentity == selectedIdentity) &&
            (selectedType == null || post.contentType == selectedType),
      );
    }
    if (subCategory != null && subCategory.isNotEmpty) {
      throw contentCapabilityUnavailable('feed_subcategory');
    }
    final rows = selected.toList(growable: false);
    final queryDigest = sha256
        .convert(
          utf8.encode(
            jsonEncode([
              bundle.digest,
              channel,
              selectedIdentity,
              selectedType,
              subCategory,
              sort,
              limit,
            ]),
          ),
        )
        .toString();
    var offset = 0;
    if (cursor != null && cursor.isNotEmpty) {
      final parts = cursor.split(':');
      if (parts.length != 2 ||
          parts.first != queryDigest ||
          int.tryParse(parts.last) == null ||
          '${int.parse(parts.last)}' != parts.last) {
        throw const OfflineContentFailure('bundle_query_cursor_invalid');
      }
      offset = int.parse(parts.last);
      if (offset < 0 || offset > rows.length) {
        throw const OfflineContentFailure('bundle_query_cursor_invalid');
      }
    }
    final page = rows.skip(offset).take(limit).toList(growable: false);
    contracts.throwIfCloudOperationInterrupted(
      cancellation: cancellation,
      deadlineAt: effectiveDeadline,
    );
    return DiscoveryFeedPage(
      items: page
          .map(const ContentPostProjectionMapper().toDto)
          .toList(growable: false),
      outcome: page.isEmpty
          ? contracts.ContentFeedOutcome.empty
          : contracts.ContentFeedOutcome.content,
      emptyReason: page.isNotEmpty
          ? null
          : offset > 0
          ? contracts.ContentFeedEmptyReason.continuationEnd
          : contracts.ContentFeedEmptyReason.noEligibleContent,
      nextCursor: offset + page.length < rows.length
          ? '$queryDigest:${offset + page.length}'
          : null,
    );
  }
}
