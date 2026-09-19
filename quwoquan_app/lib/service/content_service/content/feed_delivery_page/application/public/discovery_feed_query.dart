import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show CloudOperationCancellationSignal;

const String kFeedSortRecommend = 'recommend';

typedef DiscoveryFeedRoute = ({String category, String? channelId, String? type});

/// App-owned feed route normalization registry.
///
/// Surface aliases are data, not platform or vertical control flow. Service
/// wire values remain owned by generated contracts.
abstract final class DiscoveryFeedRouteRegistry {
  static const Map<String, DiscoveryFeedRoute>
  routeBySurfaceId = <String, DiscoveryFeedRoute>{
    'following': (category: 'following', channelId: 'following', type: null),
    'photo': (category: 'photo', channelId: null, type: 'image'),
    'video': (category: 'video', channelId: null, type: 'video'),
    'article': (category: 'article', channelId: null, type: 'article'),
  };

  static DiscoveryFeedRoute? routeForSurface(String surfaceId) =>
      routeBySurfaceId[surfaceId.trim()];
}

/// Canonical App query seam owned by the Feed Delivery Page object.
abstract interface class ContentDiscoveryFeedQuery {
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
    String? type,
    String? subCategory,
    required int limit,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  });
}
