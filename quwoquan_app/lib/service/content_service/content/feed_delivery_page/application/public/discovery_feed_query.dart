import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show CloudOperationCancellationSignal;

const String kFeedSortRecommend = 'recommend';

typedef DiscoveryFeedRoute = ({
  String category,
  String? channelId,
  String? identity,
  String? type,
});

/// App-owned feed route normalization registry.
///
/// Surface aliases and category identity fallbacks are data, not platform or
/// vertical control flow. Service wire values remain owned by generated
/// contracts.
abstract final class DiscoveryFeedRouteRegistry {
  static const Map<String, DiscoveryFeedRoute>
  routeBySurfaceId = <String, DiscoveryFeedRoute>{
    'following': (
      category: 'following',
      channelId: 'following',
      identity: null,
      type: null,
    ),
    'moment': (
      category: 'moment',
      channelId: null,
      identity: 'moment',
      type: null,
    ),
    'work': (category: 'work', channelId: null, identity: 'work', type: null),
    'works': (category: 'work', channelId: null, identity: 'work', type: null),
    'photo': (
      category: 'photo',
      channelId: null,
      identity: 'work',
      type: 'image',
    ),
    'video': (
      category: 'video',
      channelId: null,
      identity: 'work',
      type: 'video',
    ),
    'article': (
      category: 'article',
      channelId: null,
      identity: 'work',
      type: 'article',
    ),
  };

  static const Map<String, String> identityByCategory = <String, String>{
    'moment': 'moment',
    'recommended': 'moment',
    'following': 'moment',
    'work': 'work',
    'works': 'work',
    'photo': 'work',
    'images': 'work',
    'video': 'work',
    'article': 'work',
  };

  static DiscoveryFeedRoute? routeForSurface(String surfaceId) =>
      routeBySurfaceId[surfaceId.trim()];

  static String? identityForCategory(String category) =>
      identityByCategory[category.trim()];
}

/// Canonical App query seam owned by the Feed Delivery Page object.
abstract interface class ContentDiscoveryFeedQuery {
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
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  });
}
