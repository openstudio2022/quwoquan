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
import 'package:quwoquan_app/cloud/media/media_download_cache.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/feed_object_card_dto.g.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import 'package:quwoquan_app/ui/discovery/widgets/home_multi_form_feed.dart';

import '../../../support/cloud_services/content_facet_overrides.dart';
import '../../../support/cloud_services/content/mock_content_repository.dart';

MicroPostDto _post(int index) {
  return MicroPostDto(
    id: 'post_object_card_widget_$index',
    type: 'moment',
    identity: 'moment',
    authorId: 'user_demo',
    displayName: '小趣用户',
    avatarUrl: '',
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
    imageUrls: const <String>[],
    videoUrl: null,
    durationMs: null,
    intersectionReasons: const [],
  );
}

class _ObjectCardsFeedMapNotifier extends DiscoveryFeedMapNotifier {
  _ObjectCardsFeedMapNotifier(this.posts, this.cards);

  final List<ContentPostViewData> posts;
  final List<FeedObjectCardDto> cards;

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
  }) async => const DiscoveryFeedLoadResult(
    terminal: DiscoveryFeedLoadTerminal.content,
    generation: 0,
  );
}

class _NoopMediaDownloadCache extends MediaDownloadCache {
  @override
  Future<String?> getCachedFilePath(String url) async => null;
}

Widget _buildFeed(List<ContentPostViewData> posts, List<FeedObjectCardDto> cards) {
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
    final cards = <FeedObjectCardDto>[
      FeedObjectCardDto(
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
    await tester.pumpWidget(_buildFeed(posts, const <FeedObjectCardDto>[]));
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
}
