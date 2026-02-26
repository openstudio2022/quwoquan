/// L1c Journey Test: 发现页 Feed 加载旅程
///
/// 守护：用户打开发现页 → provider 调用 MockContentRepository → feed 状态填充
/// Mock Wall：ContentRepository 接口（MockContentRepository 不发 HTTP）
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/feed_item_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';

void main() {
  group('Discovery Feed Load Journey', () {
    test('旅程 A1：用户切换到美图 Tab → MockRepo.listDiscoveryFeedPage 被调用 → 返回 PhotoPostDto 列表', () async {
      final mock = MockContentRepository();
      final container = ProviderContainer(
        overrides: [contentRepositoryProvider.overrideWithValue(mock)],
      );
      addTearDown(container.dispose);

      // 用户动作：切换到 photo tab（触发 notifier.load）
      await container.read(discoveryFeedMapProvider.notifier).load('photo');

      // 断言：feed 状态已填充
      final feedAsync = container.read(discoveryFeedMapProvider)['photo'];
      expect(feedAsync, isNotNull, reason: 'photo tab state should be present');

      final feed = feedAsync!.value!;
      expect(feed.items, isNotEmpty, reason: 'MockRepo 应返回 seeded photo 数据');
      expect(feed.items, everyElement(isA<PhotoPostDto>()),
          reason: 'contentType=image 应 dispatch 为 PhotoPostDto');
      expect(feed.error, isNull, reason: '正常加载不应有错误');
    });

    test('旅程 A2：网络失败 → feed 状态携带 error，不抛异常', () async {
      final failRepo = _ErrorContentRepository('NETWORK_TIMEOUT');
      final container = ProviderContainer(
        overrides: [contentRepositoryProvider.overrideWithValue(failRepo)],
      );
      addTearDown(container.dispose);

      await container.read(discoveryFeedMapProvider.notifier).load('photo');

      final feed = container.read(discoveryFeedMapProvider)['photo']?.value;
      expect(feed, isNotNull);
      expect(feed!.error, contains('NETWORK_TIMEOUT'),
          reason: '错误消息应传播到 feed state');
      expect(feed.items, isEmpty);
    });

    test('旅程 A3：连续加载两个 tab → 状态互相独立', () async {
      final mock = MockContentRepository();
      final container = ProviderContainer(
        overrides: [contentRepositoryProvider.overrideWithValue(mock)],
      );
      addTearDown(container.dispose);

      await container.read(discoveryFeedMapProvider.notifier).load('photo');
      await container.read(discoveryFeedMapProvider.notifier).load('video');

      final photoFeed = container.read(discoveryFeedMapProvider)['photo']?.value;
      final videoFeed = container.read(discoveryFeedMapProvider)['video']?.value;

      expect(photoFeed!.items, isNotEmpty);
      expect(videoFeed!.items, isNotEmpty);
      // 两个 tab 的内容类型不同
      expect(photoFeed.items.first, isA<PhotoPostDto>());
      expect(videoFeed.items.first, isA<VideoPostDto>());
    });
  });
}

// ── Test doubles ──────────────────────────────────────────────────────────────

class _ErrorContentRepository implements ContentRepository {
  _ErrorContentRepository(this._errorMessage);
  final String _errorMessage;

  @override
  Future<CursorPage<PostBaseDto>> listDiscoveryFeedPage({
    required String category,
    String? subCategory,
    int limit = 20,
    String? cursor,
  }) async => throw Exception(_errorMessage);

  @override
  Future<List<PostBaseDto>> listDiscoveryFeed({
    required String category,
    String? subCategory,
    int limit = 20,
    String? cursor,
  }) async => throw Exception(_errorMessage);

  @override
  Future<CursorPage<FeedItemDto>> listDiscoveryFeedPageLegacy({
    required String category,
    String? subCategory,
    int limit = 20,
    String? cursor,
  }) async => throw Exception(_errorMessage);

  @override
  Future<Map<String, dynamic>> getPost({required String postId}) async => {};
  @override
  Future<Map<String, dynamic>> createPost({required Map<String, dynamic> payload}) async => {};
  @override
  Future<void> likePost({required String postId}) async {}
  @override
  Future<void> unlikePost({required String postId}) async {}
  @override
  Future<void> favoritePost({required String postId}) async {}
  @override
  Future<void> unfavoritePost({required String postId}) async {}
  @override
  Future<Map<String, dynamic>> getReactionState({required String postId}) async => {};
  @override
  Future<List<Map<String, dynamic>>> listComments({required String postId, String? cursor, int limit = 20}) async => [];
  @override
  Future<Map<String, dynamic>> createComment({required String postId, required String content, String? replyToCommentId}) async => {};
  @override
  Future<void> deleteComment({required String postId, required String commentId}) async {}
  @override
  Future<void> reportBehaviors({required List<Map<String, dynamic>> events}) async {}
  @override
  Future<Map<String, dynamic>> getCounters({required String postId}) async => {};
}
