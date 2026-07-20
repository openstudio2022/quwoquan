import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction_asset.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction_section.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction_timeline_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_source.g.dart';
import 'package:quwoquan_app/components/media/app_media_image.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_route_models.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_tab.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_introduction_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show CloudOperationCancellationSignal;

class _IntroRepository implements HomepageIntroductionRepository {
  _IntroRepository(this.introduction, {this.shouldThrow = false});

  final HomepageIntroduction? introduction;
  final bool shouldThrow;

  @override
  Future<HomepageIntroduction?> getHomepageIntroduction(
    String homepageId, {
    CloudOperationCancellationSignal? cancellation,
  }) async {
    cancellation?.throwIfCancelled();
    if (shouldThrow) {
      throw StateError('intro failed');
    }
    return introduction;
  }
}

Widget _host(HomepageIntroduction? introduction, {bool shouldThrow = false}) {
  return ProviderScope(
    overrides: [
      homepageIntroductionRepositoryProvider.overrideWithValue(
        _IntroRepository(introduction, shouldThrow: shouldThrow),
      ),
    ],
    child: const CupertinoApp(
      home: HomepageIntroductionPage(homepageId: 'homepage_sight_west_lake'),
    ),
  );
}

void main() {
  testWidgets('完整介绍页渲染分节与时间线', (tester) async {
    await tester.pumpWidget(
      _host(
        HomepageIntroduction(
          homepageId: 'homepage_sight_west_lake',
          displayName: '西湖景区',
          homepageType: 'sight',
          summary: '西湖景区摘要',
          sections: <HomepageIntroductionSection>[
            HomepageIntroductionSection(
              kind: 'overview',
              title: '概况',
              bodyMarkdown: '西湖景区位于杭州。',
            ),
            HomepageIntroductionSection(
              kind: 'timeline',
              title: '时间线',
              timelineItems: <HomepageIntroductionTimelineItem>[
                HomepageIntroductionTimelineItem(
                  dateLabel: '今天',
                  text: '围绕西湖的内容和讨论持续沉淀。',
                ),
              ],
            ),
          ],
          primarySource: HomepageSource(
            sourceKind: 'wikipedia',
            sourceUrl: 'https://zh.wikipedia.org/wiki/西湖',
            title: '西湖',
            policyRevision: 'encyclopedia-primary',
          ),
          sourceUrls: const <String>['https://zh.wikipedia.org/wiki/西湖'],
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('认识西湖景区'), findsOneWidget);
    expect(find.text('西湖景区摘要'), findsOneWidget);
    expect(find.text('概况'), findsOneWidget);
    expect(find.textContaining('位于杭州'), findsOneWidget);
    expect(find.text('时间线'), findsOneWidget);
    expect(find.text('今天'), findsOneWidget);
    expect(find.textContaining('持续沉淀'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('西湖'),
      AppSpacing.twoHundredTwenty,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.textContaining('Wikipedia · zh.wikipedia.org'), findsOneWidget);
    expect(find.textContaining('fixture:'), findsNothing);
    expect(find.textContaining('sourceRefs'), findsNothing);
    expect(find.textContaining('/Users/'), findsNothing);
    final sourceButton = tester.widget<CupertinoButton>(
      find.ancestor(
        of: find.text('西湖'),
        matching: find.byType(CupertinoButton),
      ),
    );
    expect(sourceButton.onPressed, isNotNull);
  });

  testWidgets('三段结构：正文块级内嵌图与页尾相关图片按 role 渲染', (tester) async {
    await tester.pumpWidget(
      _host(
        HomepageIntroduction(
          homepageId: 'homepage_sight_dujiangyan',
          displayName: '都江堰',
          homepageType: 'sight',
          coverUrl: 'https://cdn.example.com/cover.jpg',
          summary: '战国修建的大型水利工程',
          sections: <HomepageIntroductionSection>[
            HomepageIntroductionSection(
              kind: 'body',
              title: '历史沿革',
              bodyMarkdown:
                  '李冰父子主持修建。\n\n'
                  ':::figure id="fig_01" layout="fullWidth" caption="鱼嘴分水堤"\n'
                  'asset://inline_asset_1\n'
                  ':::\n\n'
                  '两千余年持续灌溉成都平原。',
              assets: <HomepageIntroductionAsset>[
                HomepageIntroductionAsset(
                  assetId: 'inline_asset_1',
                  url: 'https://cdn.example.com/inline1.jpg',
                  caption: '鱼嘴分水堤',
                  role: 'inline',
                ),
              ],
            ),
            HomepageIntroductionSection(
              kind: 'relatedImages',
              title: '相关图片',
              assets: <HomepageIntroductionAsset>[
                HomepageIntroductionAsset(
                  assetId: 'related_asset_1',
                  url: 'https://cdn.example.com/rel1.jpg',
                  role: 'related',
                ),
                HomepageIntroductionAsset(
                  assetId: 'related_asset_2',
                  url: 'https://cdn.example.com/rel2.jpg',
                  role: 'related',
                ),
              ],
            ),
          ],
        ),
      ),
    );
    await tester.pumpAndSettle();

    // 正文章节：figure 指令不得以原文文本泄漏，必须渲染成块级图 + 单行图注。
    expect(find.textContaining(':::figure'), findsNothing);
    expect(find.textContaining('asset://'), findsNothing);
    expect(find.textContaining('主持修建'), findsOneWidget);
    expect(find.textContaining('灌溉成都平原'), findsOneWidget);
    expect(find.text('鱼嘴分水堤'), findsOneWidget);

    // 页尾相关图片小节标题可见。
    await tester.scrollUntilVisible(
      find.text('相关图片'),
      AppSpacing.twoHundredTwenty,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('相关图片'), findsOneWidget);

    // 封面 hero + 正文 1 张内嵌图 + 相关图片 2 张 = 至少 4 个媒体图。
    expect(
      find.byType(AppMediaImage, skipOffstage: false),
      findsAtLeastNWidgets(4),
    );
  });

  testWidgets('介绍为空时展示空态', (tester) async {
    await tester.pumpWidget(
      _host(
        HomepageIntroduction(
          homepageId: 'homepage_empty',
          displayName: '空主页',
          homepageType: 'place',
          summary: '',
          sections: const <HomepageIntroductionSection>[],
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('介绍正在整理'), findsOneWidget);
  });

  testWidgets('介绍加载失败时展示可重试错误态', (tester) async {
    await tester.pumpWidget(_host(null, shouldThrow: true));
    await tester.pumpAndSettle();

    expect(find.byType(AppPageErrorState), findsOneWidget);
  });

  testWidgets('页尾三个入口分别直达详情指定 tab', (tester) async {
    final introduction = HomepageIntroduction(
      homepageId: 'homepage_sight_west_lake',
      displayName: '西湖景区',
      homepageType: 'sight',
      summary: '西湖景区摘要',
      sections: <HomepageIntroductionSection>[
        HomepageIntroductionSection(
          kind: 'overview',
          title: '概况',
          bodyMarkdown: '西湖景区位于杭州。',
        ),
      ],
    );
    final cases = <(String, HomepageDetailTabTarget)>[
      (UITextConstants.objectIntroReturnRecord, HomepageDetailTabTarget.record),
      (
        UITextConstants.objectIntroReturnDiscussion,
        HomepageDetailTabTarget.discussion,
      ),
      (
        UITextConstants.objectIntroReturnCircles,
        HomepageDetailTabTarget.relatedCircles,
      ),
    ];

    for (final testCase in cases) {
      final router = GoRouter(
        initialLocation: AppRoutePaths.homepageIntroduction(
          id: 'homepage_sight_west_lake',
        ),
        routes: <RouteBase>[
          GoRoute(
            path: AppRoutePaths.homepageIntroductionPathTemplate.replaceAll(
              '{id}',
              ':id',
            ),
            builder: (_, _) => const HomepageIntroductionPage(
              homepageId: 'homepage_sight_west_lake',
            ),
          ),
          GoRoute(
            path: AppRoutePaths.homepageDetailPathTemplate.replaceAll(
              '{id}',
              ':id',
            ),
            builder: (_, state) {
              final extra = state.extra as HomepageDetailPageRouteExtra?;
              return Text('DETAIL_TARGET:${extra?.initialTabTarget?.name}');
            },
          ),
        ],
      );
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            homepageIntroductionRepositoryProvider.overrideWithValue(
              _IntroRepository(introduction),
            ),
          ],
          child: CupertinoApp.router(routerConfig: router),
        ),
      );
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text(testCase.$1),
        AppSpacing.twoHundredTwenty,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text(testCase.$1));
      await tester.pumpAndSettle();

      expect(find.text('DETAIL_TARGET:${testCase.$2.name}'), findsOneWidget);
      router.dispose();
      await tester.pumpWidget(const SizedBox.shrink());
    }
  });
}
