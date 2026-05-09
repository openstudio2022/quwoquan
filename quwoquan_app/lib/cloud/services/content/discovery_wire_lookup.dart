import 'package:quwoquan_app/cloud/runtime/generated/content/feed_item_dto.g.dart';
import 'package:quwoquan_app/cloud/services/content/feed_item_discovery_wire_map.dart';
import 'package:quwoquan_app/cloud/services/content/mock/content_mock_data.dart';

/// 将四类发现区 [FeedItemDto] 列表合并为单行扫描序列（与 [ContentMockData] / Feed projection 对齐）。
List<Map<String, dynamic>> aggregateDiscoveryWireSlices({
  required List<FeedItemDto> photo,
  required List<FeedItemDto> video,
  required List<FeedItemDto> article,
  required List<FeedItemDto> moment,
}) {
  return <Map<String, dynamic>>[
    ...photo.map((e) => e.toDiscoveryWireMap()),
    ...video.map((e) => e.toDiscoveryWireMap()),
    ...article.map((e) => e.toDiscoveryWireMap()),
    ...moment.map((e) => e.toDiscoveryWireMap()),
  ];
}

/// 在已聚合的 wire 行中按 postId 查找（支持 postId / _id / id）。
Map<String, dynamic>? findDiscoveryWireRowByPostId(
  String postId,
  List<Map<String, dynamic>> aggregatedRows,
) {
  if (postId.isEmpty) return null;
  for (final item in aggregatedRows) {
    final itemId =
        item['postId']?.toString() ??
        item['_id']?.toString() ??
        item['id']?.toString() ??
        '';
    if (itemId == postId) {
      return item;
    }
  }
  return null;
}

/// Canonical mock 发现区：与 [MockContentRepository] / [MockAppContentRepository] 同源。
Map<String, dynamic>? lookupCanonicalDiscoveryWireRowByPostId(String postId) {
  final row = findDiscoveryWireRowByPostId(
    postId,
    aggregateDiscoveryWireSlices(
      photo: ContentMockData.discoveryPhotoData,
      video: ContentMockData.discoveryVideoData,
      article: ContentMockData.discoveryArticleData,
      moment: ContentMockData.discoveryMomentData,
    ),
  );
  if ((row?['contentType']?.toString() ?? '') == 'article') {
    return ContentMockData.articleWireByPostId(postId) ?? row;
  }
  return row;
}

/// `true` 表示当前为 Mock 数据源：将 [FeedItemDto] 转为 wire Map；否则返回空列表。
List<Map<String, dynamic>> mockDiscoveryWireFallback(
  bool isMockDataSource,
  List<FeedItemDto> mockCanonicalRows,
) {
  if (!isMockDataSource) {
    return const <Map<String, dynamic>>[];
  }
  return mockCanonicalRows
      .map((e) => e.toDiscoveryWireMap())
      .toList(growable: false);
}

/// 分享/沉浸器等需要的 wire 扩展字段（如 circleName、tags）：仅 Mock 有线表。
Map<String, dynamic>? prototypeDiscoveryWireRowForMock(
  bool isMockDataSource,
  String postId,
) {
  if (!isMockDataSource || postId.isEmpty) return null;
  return lookupCanonicalDiscoveryWireRowByPostId(postId);
}

/// Mock 发现区 wire 回退：绑定 [ContentMockData]，避免 `lib/ui` 直接 import mock。
List<Map<String, dynamic>> mockDiscoveryVideoWireFallback(bool isMock) =>
    mockDiscoveryWireFallback(isMock, ContentMockData.discoveryVideoData);

List<Map<String, dynamic>> mockDiscoveryMomentWireFallback(bool isMock) =>
    mockDiscoveryWireFallback(isMock, ContentMockData.discoveryMomentData);

List<Map<String, dynamic>> mockDiscoveryArticleWireFallback(bool isMock) =>
    mockDiscoveryWireFallback(isMock, ContentMockData.discoveryArticleData);

List<Map<String, dynamic>> mockDiscoveryPhotoWireFallback(bool isMock) =>
    mockDiscoveryWireFallback(isMock, ContentMockData.discoveryPhotoData);
