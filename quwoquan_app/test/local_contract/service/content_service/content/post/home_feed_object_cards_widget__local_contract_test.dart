/// N2-4 契约：首页混合对象卡（entity_homepage）的 Widget 混排语义。
///
/// 断言 B4 插卡模式在真实 paint 路径生效：
///  1. objectCards 按 anchorIndex 编织进内容流并渲染（key home-object-card-*）；
///  2. 卡片标题/副标题可见（运营可核对展示装配）；
///  3. 无 objectCards 时不渲染任何对象卡（零成本关闭语义）。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/adapters/media_download_cache.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/discovery_feed_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_multi_form_feed.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentPostProjection, FeedObjectCard;

import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/post/mock_content_repository.dart';

ContentPostViewData _post(int index) {
  return ContentPostViewData.fromWire(
    ContentPostProjection(
      postId: 'post_object_card_widget_$index',
      contentType: 'micro',
      contentIdentity: 'moment',
      authorId: 'user_demo',
      authorDisplayName: '小趣用户',
      authorAvatarUrl: '',
      authorBackgroundUrl: null,
      authorRoleLabel: '旅行创作者',
      authorIdentityTags: const <String>['摄影'],
      authorVerified: false,
      assistantUsePolicy: 'allow',
      likeCount: 0,
      commentCount: 0,
      shareCount: 0,
      createdAt: DateTime(2026),
      updatedAt: null,
      publishedAt: null,
      body: '对象卡混排锚点内容 $index',
      mediaUrls: const <String>[],
      intersectionReasons: const [],
    ),
  );
}

class _ObjectCardsFeedMapNotifier extends DiscoveryFeedMapNotifier {
  _ObjectCardsFeedMapNotifier(this.posts, this.cards);

  final List<ContentPostViewData> posts;
  final List<FeedObjectCard> cards;

  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'recommend': AsyncData(
        DiscoveryFeedState(items: posts, objectCards: cards),
      ),
    };
  }

  @override
  Future<DiscoveryFeedLoadResult> load(
    String channelId, {
    bool force = false,
  }) async => DiscoveryFeedLoadResult(
    terminal: DiscoveryFeedLoadTerminal.content,
    generation: 0,
  );
}

class _NoopMediaDownloadCache extends MediaDownloadCache {
  @override
  Future<String?> getCachedFilePath(String url) async => null;
}

Widget _buildFeed(List<ContentPostViewData> posts, List<FeedObjectCard> cards) {
  return ProviderScope(
    overrides: [
      ...mockContentFacetOverrides(MockContentRepository()),
      discoveryFeedMapProvider.overrideWith(
        () => _ObjectCardsFeedMapNotifier(posts, cards),
      ),
      mediaDownloadCacheProvider.overrideWithValue(_NoopMediaDownloadCache()),
    ],
    child: CupertinoApp(
      home: ScreenUtilInit(
        designSize: const Size(390, 844),
        child: MediaQuery(
          data: const MediaQueryData(size: Size(390, 844)),
          child: HomeMultiFormFeed(
            isDark: false,
            channelId: 'recommend',
            template: 'single_column_multiform',
            onUserTap: (_, {avatarUrl, backgroundUrl, displayName}) {},
          ),
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('objectCards 按 anchorIndex 编织进内容流并渲染实体卡', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final posts = List<ContentPostViewData>.generate(3, _post);
    final cards = <FeedObjectCard>[
      FeedObjectCard(
        objectKind: 'entity_homepage',
        objectId: 'homepage_sight_west_lake',
        title: '西湖',
        subtitle: '杭州 · 风景名胜',
        tagRefs: const <String>['Topic/旅行/杭州'],
        reasonText: 'affinity',
        recallPath: 'entity_affinity_card',
        anchorIndex: 2,
      ),
    ];

    await tester.pumpWidget(_buildFeed(posts, cards));
    await tester.pump();

    final cardFinder = find.byKey(
      const ValueKey<String>('home-object-card-homepage_sight_west_lake'),
    );
    expect(cardFinder, findsOneWidget, reason: '对象卡必须按锚点渲染进内容流');
    expect(find.text('西湖'), findsOneWidget);
  });

  testWidgets('无 objectCards 时不渲染任何对象卡（零成本关闭）', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final posts = List<ContentPostViewData>.generate(2, _post);
    await tester.pumpWidget(_buildFeed(posts, const <FeedObjectCard>[]));
    await tester.pump();

    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget.key is ValueKey<String> &&
            (widget.key as ValueKey<String>).value.startsWith(
              'home-object-card-',
            ),
      ),
      findsNothing,
    );
  });

  testWidgets('Gathering 对象卡保留 canonical reference 并进入同一混排组件', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final posts = List<ContentPostViewData>.generate(3, _post);
    final cards = <FeedObjectCard>[
      FeedObjectCard(
        objectKind: 'gathering',
        objectId: 'gathering-001',
        title: '周末山野徒步',
        subtitle: '公开摘要',
        tagRefs: const <String>['Topic/徒步'],
        reasonText: 'public_gathering',
        recallPath: 'gathering_candidate_index',
        anchorIndex: 2,
      ),
    ];

    await tester.pumpWidget(_buildFeed(posts, cards));
    await tester.pump();

    expect(
      find.byKey(const ValueKey<String>('home-object-card-gathering-001')),
      findsOneWidget,
    );
    expect(find.text('周末山野徒步'), findsOneWidget);
  });
}
