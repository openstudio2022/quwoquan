import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_creations.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'typed_circle_query_test_double.dart';
import '../../../support/cloud_services/object_doubles/circle/circle_contract_test_builders.dart';

Widget _buildApp(
  Widget child, {
  CircleQueryReader? circleQuery,
  CircleFeedQueryReader? feedQuery,
}) {
  return ProviderScope(
    overrides: [
      circleDetailQueryProvider.overrideWithValue(
        circleQuery ?? CircleQueryReaderTestDouble(),
      ),
      circlesListQueryProvider.overrideWithValue(
        circleQuery ?? CircleQueryReaderTestDouble(),
      ),
      circleDetailFeedQueryProvider.overrideWithValue(
        feedQuery ??
            CircleFeedQueryTestDouble(
              (query) => CircleFeedPageSlice(
                items: const <CircleFeedItemView>[],
              ),
            ),
      ),
    ],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/',
        routes: [
          GoRoute(
            path: '/',
            builder: (_, _) => Scaffold(body: child),
          ),
          GoRoute(
            path: '/works/browser/:workId',
            builder: (_, _) => const SizedBox(),
          ),
          GoRoute(path: '/chat/:id', builder: (_, _) => const SizedBox()),
        ],
      ),
    ),
  );
}

void main() {
  testWidgets('圈子作品二级筛选仅展示全部/图片/视频/长文', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        const SizedBox(
          height: 800,
          child: SectionCreations(
            circleId: 'fixture_circle_photo',
            isDark: false,
            role: CircleRole.owner,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // 二级过滤改回横向胶囊条：全部子页签直接平铺可见（默认「全部」选中）。
    expect(find.text('全部'), findsAtLeastNWidgets(1));
    expect(find.text('图片'), findsAtLeastNWidgets(1));
    expect(find.text('视频'), findsAtLeastNWidgets(1));
    // 「长文」是与用户主页同源的 metadata 子页签 creation_sub_text 文案
    // （UserProfileUIConfig.creationSubTabs），与作者主页保持一致。
    expect(find.text('长文'), findsAtLeastNWidgets(1));
    expect(find.text('点滴'), findsNothing);
    expect(find.text('微趣'), findsNothing);
    expect(find.text('文章'), findsNothing);
  });

  testWidgets('圈子作品切到长文后，列表标签与筛选口径保持一致', (tester) async {
    final circleQuery = _ArticleFixtureCircleQuery();
    await tester.pumpWidget(
      _buildApp(
        const SizedBox(
          height: 800,
          child: SectionCreations(
            circleId: 'fixture_circle_photo',
            isDark: false,
            role: CircleRole.owner,
          ),
        ),
        circleQuery: circleQuery,
        feedQuery: CircleFeedQueryTestDouble(_articleFeedFixture),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('列表视图'));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(
        const ValueKey<String>('circle-creations-filter-option-article'),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('长文'), findsAtLeastNWidgets(1));
    expect(
      find.byKey(
        const ValueKey<String>(
          'circle-article-list-fixture_article_with_cover',
        ),
      ),
      findsOneWidget,
    );
    expect(find.textContaining('讨论推荐'), findsWidgets);
    expect(find.textContaining('赞 '), findsWidgets);
  });
}

CircleFeedPageSlice _articleFeedFixture(CircleFeedQuery query) {
  return CircleFeedPageSlice(
    items: <CircleFeedItemView>[
      buildCircleFeedItemContract(
        circleId: query.circleId,
        placementId: 'fixture-placement-article-cover',
        postId: 'fixture_article_with_cover',
        contentType: 'article',
        contentIdentity: 'work',
        authorId: 'fixture_user_photo',
        authorDisplayName: '契约摄影师',
        authorAvatarUrl: 'media/avatar/fixture_user_photo.png',
        title: '山路晨雾手账',
        summary: '把徒步笔记做成可翻页的旅途册。',
        body: '把徒步笔记做成可翻页的旅途册。',
        coverUrl: 'media/image/fixture_article_with_cover.jpg',
        likeCount: 164,
        commentCount: 12,
        shareCount: 11,
        createdAt: DateTime.utc(2026, 5, 13),
      ),
      buildCircleFeedItemContract(
        circleId: query.circleId,
        placementId: 'fixture-placement-article-text',
        postId: 'fixture_article_text_only',
        contentType: 'article',
        contentIdentity: 'work',
        authorId: 'fixture_user_owner',
        authorDisplayName: '纸上居',
        authorAvatarUrl: 'media/avatar/fixture_user_owner.png',
        summary: '没有标题也没封面，只保留真正想被圈友读到的正文。',
        body: '没有标题也没封面，只保留真正想被圈友读到的正文。',
        likeCount: 88,
        commentCount: 6,
        shareCount: 4,
        createdAt: DateTime.utc(2026, 5, 13, 1),
      ),
    ],
  );
}

class _ArticleFixtureCircleQuery extends CircleQueryReaderTestDouble {
  @override
  Future<Circle> get(CircleDetailQuery query) async =>
      buildCircleContract(
        circleId: query.circleId,
        name: '契约摄影社',
        ownerId: 'fixture_user_owner',
        category: 'photography',
        visibility: CircleVisibility.public,
        joinPolicy: CircleJoinPolicy.approval,
        createdAt: DateTime.utc(2026, 5, 6),
        updatedAt: DateTime.utc(2026, 5, 6),
      );
}
