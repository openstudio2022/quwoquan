// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-005

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/domain/works_viewer_state_budget.dart';

void main() {
  test('生产默认预算固定为 16 个作品、current±2 与 48 条派生投影', () {
    final window = WorksViewerPostStateWindow((_) {});
    final cache = WorksViewerLruCache<String, String>();

    expect(window.capacity, 16);
    expect(window.protectedViewportRadius, 2);
    expect(cache.capacity, 48);
  });

  test('viewer 将全部按 post 累积的局部集合接入同一淘汰回调', () {
    final source = File(
      'lib/service/content_service/media/media_asset/presentation/works_immersive_viewer.dart',
    ).readAsStringSync();
    final presentationSource = File(
      'lib/service/content_service/media/media_asset/presentation/works_immersive_viewer_presentation.dart',
    ).readAsStringSync();
    final engagementSource = File(
      'lib/service/content_service/media/media_asset/presentation/works_immersive_viewer_engagement_actions.dart',
    ).readAsStringSync();
    final lifecycleSource = File(
      'lib/service/content_service/media/media_asset/presentation/works_immersive_viewer_lifecycle.dart',
    ).readAsStringSync();
    final hydrationSource = lifecycleSource
        .split('Future<void> _maybeHydrateArticleDetail(')
        .last
        .split('bool _shouldShowArticleHydrationError(')
        .first;
    for (final collection in const <String>[
      '_photoInnerIndex',
      '_articleInnerIndex',
      '_resolvedArticlePageCount',
      '_articlePaperThemeOverrides',
      '_videoInnerIndex',
      '_videoInnerIdentity',
      '_expandedCaptionPostIds',
      '_originalImageUrlsByPostId',
      '_hydratedRawPostsById',
      '_failedArticleHydrationIds',
      '_failedArticleHydrationErrorsById',
      '_workItemCache',
    ]) {
      expect(
        source,
        contains('$collection.remove(postId);'),
        reason: '$collection 必须跟随 resident post 淘汰',
      );
    }
    expect(source, contains('void didHaveMemoryPressure()'));
    expect(source, contains('_postStateWindow.handleMemoryPressure('));
    expect(
      source,
      contains('posts[_currentPage.clamp(0, posts.length - 1)].id'),
    );
    expect(source, contains('_maxOriginalImageAccessEntriesPerPost = 12'));
    expect(presentationSource, contains('isUsableAt(now)'));
    expect(engagementSource, contains('expiresAt: grant.expiresAt'));
    expect(
      hydrationSource.indexOf(
        "if (!mounted || !_postStateWindow.contains(post.id))",
      ),
      lessThan(
        hydrationSource.indexOf(
          'applyConfirmedInteractionPost(ref, detail.post);',
        ),
      ),
    );
  });

  test('连续浏览只保留固定容量并保护当前项与有界回滑邻居', () {
    final evicted = <String>[];
    final window = WorksViewerPostStateWindow(
      evicted.add,
      capacity: 5,
      protectedViewportRadius: 1,
    );
    final posts = List<String>.generate(20, (index) => 'post-$index');

    for (var current = 0; current <= 12; current += 1) {
      window.updateViewport(
        itemCount: posts.length,
        currentIndex: current,
        postIdAt: (index) => posts[index],
      );
    }

    expect(window.residentPostIds, hasLength(5));
    expect(window.contains('post-11'), isTrue);
    expect(window.contains('post-12'), isTrue);
    expect(window.contains('post-13'), isTrue);
    expect(window.contains('post-10'), isTrue);
    expect(window.contains('post-0'), isFalse);
    expect(evicted, contains('post-0'));
  });

  test('内存压力只保留当前作品并同步发出其他状态淘汰', () {
    final evicted = <String>[];
    final window = WorksViewerPostStateWindow(
      evicted.add,
      capacity: 6,
      protectedViewportRadius: 1,
    );
    const posts = <String>['post-0', 'post-1', 'post-2', 'post-3'];
    window.updateViewport(
      itemCount: posts.length,
      currentIndex: 2,
      postIdAt: (index) => posts[index],
    );
    window.touch('post-history');

    window.handleMemoryPressure(currentPostId: 'post-2');

    expect(window.residentPostIds, const <String>['post-2']);
    expect(evicted, containsAll(<String>['post-1', 'post-3', 'post-history']));
  });

  test('派生投影缓存按真实访问顺序执行固定容量 LRU', () {
    final cache = WorksViewerLruCache<String, String>(capacity: 2);
    cache.write('post-a', 'a');
    cache.write('post-b', 'b');

    expect(cache.read('post-a'), 'a');
    cache.write('post-c', 'c');

    expect(cache.keys, const <String>['post-a', 'post-c']);
    expect(cache.read('post-b'), isNull);
    expect(cache.count, 2);
  });

  test('原图授权按服务端 expiresAt 与安全窗口失效', () {
    final access = WorksViewerOriginalImageAccess(
      url: 'https://media.example/original.jpg?signature=opaque',
      expiresAt: DateTime.utc(2026, 7, 29, 10, 0, 10),
    );

    expect(access.isUsableAt(DateTime.utc(2026, 7, 29, 10)), isTrue);
    expect(access.isUsableAt(DateTime.utc(2026, 7, 29, 10, 0, 6)), isFalse);
    expect(
      access.isUsableAt(
        DateTime.utc(2026, 7, 29, 10, 0, 9),
        safetyWindow: Duration.zero,
      ),
      isTrue,
    );
    expect(
      access.isUsableAt(
        DateTime.utc(2026, 7, 29, 10, 0, 10),
        safetyWindow: Duration.zero,
      ),
      isFalse,
    );
  });
}
