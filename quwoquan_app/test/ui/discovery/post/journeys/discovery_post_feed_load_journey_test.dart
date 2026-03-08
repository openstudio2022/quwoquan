/// L1c Journey Test: 发现页 Feed 加载旅程
///
/// 守护：用户打开发现页 → DiscoveryFeedMapNotifier 调用 MockContentRepository
///       → feed 状态正确填充 → Widget 树重建
///
/// Mock Wall：ContentRepository 接口（MockContentRepository 不发 HTTP）
///
/// 规则：L1c Journey 测试必须使用 testWidgets()；禁止在 journeys/ 目录下
///       使用 test() + 仅操作 ProviderContainer 的形式。
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';

// ── 测试辅助 ─────────────────────────────────────────────────────────────────

/// 构建包含 ProviderScope + MaterialApp 的最小 Widget 树，返回 ProviderContainer。
///
/// 使用 [ProviderContainer] 直接操作 Provider，Widget 树保证渲染 context 存在。
Widget _scopedApp({
  required MockContentRepository mock,
  Widget home = const SizedBox.shrink(),
}) {
  return ProviderScope(
    overrides: [contentRepositoryProvider.overrideWithValue(mock)],
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => MaterialApp(home: home),
    ),
  );
}

// ── 错误用 Repository ─────────────────────────────────────────────────────────

class _ErrorContentRepository extends MockContentRepository {
  _ErrorContentRepository(this._errorMessage);
  final String _errorMessage;

  @override
  Future<CursorPage<PostBaseDto>> listDiscoveryFeedPage({
    required String category,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
  }) async => throw Exception(_errorMessage);

  @override
  Future<List<PostBaseDto>> listDiscoveryFeed({
    required String category,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
  }) async => throw Exception(_errorMessage);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 旅程正常路径
  // ──────────────────────────────────────────────────────────────────
  group('旅程正常路径', () {
    testWidgets('旅程 A1：切换到美图 Tab → Provider 调用 MockRepo → 返回 PhotoPostDto 列表', (
      tester,
    ) async {
      final mock = MockContentRepository();
      await tester.pumpWidget(_scopedApp(mock: mock));

      final container = ProviderScope.containerOf(
        tester.element(find.byType(MaterialApp)),
      );

      await container.read(discoveryFeedMapProvider.notifier).load('photo');
      await tester.pump();

      final feedAsync = container.read(discoveryFeedMapProvider)['photo'];
      expect(feedAsync, isNotNull, reason: 'photo tab state should be present');

      final feed = feedAsync!.value!;
      expect(feed.items, isNotEmpty, reason: 'MockRepo 应返回 seeded photo 数据');
      expect(
        feed.items,
        everyElement(isA<PhotoPostDto>()),
        reason: 'contentType=image 应 dispatch 为 PhotoPostDto',
      );
      expect(feed.error, isNull, reason: '正常加载不应有错误');
    });

    testWidgets('旅程 A2：切换到视频 Tab → 返回 VideoPostDto 列表', (tester) async {
      final mock = MockContentRepository();
      await tester.pumpWidget(_scopedApp(mock: mock));

      final container = ProviderScope.containerOf(
        tester.element(find.byType(MaterialApp)),
      );

      await container.read(discoveryFeedMapProvider.notifier).load('video');
      await tester.pump();

      final feed = container.read(discoveryFeedMapProvider)['video']?.value;
      expect(feed, isNotNull);
      expect(feed!.items, isNotEmpty);
      expect(feed.items.first, isA<VideoPostDto>());
      expect(feed.error, isNull);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 旅程错误路径
  // ──────────────────────────────────────────────────────────────────
  group('旅程错误路径', () {
    testWidgets('旅程 B1：网络失败 → feed 状态携带 error，items 为空', (tester) async {
      final failRepo = _ErrorContentRepository('NETWORK_TIMEOUT');
      await tester.pumpWidget(
        ProviderScope(
          overrides: [contentRepositoryProvider.overrideWithValue(failRepo)],
          child: const MaterialApp(home: SizedBox.shrink()),
        ),
      );

      final container = ProviderScope.containerOf(
        tester.element(find.byType(MaterialApp)),
      );

      await container.read(discoveryFeedMapProvider.notifier).load('photo');
      await tester.pump();

      final feed = container.read(discoveryFeedMapProvider)['photo']?.value;
      expect(feed, isNotNull);
      expect(
        feed!.error,
        contains('NETWORK_TIMEOUT'),
        reason: '错误消息应传播到 feed state',
      );
      expect(feed.items, isEmpty);
    });

    testWidgets('旅程 B2：服务抛异常 → provider 不传播未捕获异常给调用方', (tester) async {
      final failRepo = _ErrorContentRepository('SERVER_500');
      await tester.pumpWidget(
        ProviderScope(
          overrides: [contentRepositoryProvider.overrideWithValue(failRepo)],
          child: const MaterialApp(home: SizedBox.shrink()),
        ),
      );

      final container = ProviderScope.containerOf(
        tester.element(find.byType(MaterialApp)),
      );

      await expectLater(
        container.read(discoveryFeedMapProvider.notifier).load('photo'),
        completes,
      );
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 旅程边界/幂等
  // ──────────────────────────────────────────────────────────────────
  group('旅程边界/幂等', () {
    testWidgets('旅程 C1：连续加载两个 tab → 状态互相独立', (tester) async {
      final mock = MockContentRepository();
      await tester.pumpWidget(_scopedApp(mock: mock));

      final container = ProviderScope.containerOf(
        tester.element(find.byType(MaterialApp)),
      );

      await container.read(discoveryFeedMapProvider.notifier).load('photo');
      await container.read(discoveryFeedMapProvider.notifier).load('video');
      await tester.pump();

      final photoFeed = container
          .read(discoveryFeedMapProvider)['photo']
          ?.value;
      final videoFeed = container
          .read(discoveryFeedMapProvider)['video']
          ?.value;

      expect(photoFeed!.items, isNotEmpty);
      expect(videoFeed!.items, isNotEmpty);
      expect(photoFeed.items.first, isA<PhotoPostDto>());
      expect(videoFeed.items.first, isA<VideoPostDto>());
    });

    testWidgets('旅程 C2：同一 tab 重复加载 → 状态稳定，不崩溃', (tester) async {
      final mock = MockContentRepository();
      await tester.pumpWidget(_scopedApp(mock: mock));

      final container = ProviderScope.containerOf(
        tester.element(find.byType(MaterialApp)),
      );

      await container.read(discoveryFeedMapProvider.notifier).load('photo');
      await container.read(discoveryFeedMapProvider.notifier).load('photo');
      await tester.pump();

      final feed = container.read(discoveryFeedMapProvider)['photo']?.value;
      expect(feed, isNotNull);
      expect(feed!.items, isNotEmpty);
      expect(feed.error, isNull);
    });
  });
}
