import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/article_post_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/cloud/runtime/models/circle_detail_payload.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_creations.dart';

Widget _buildApp(Widget child, {CircleRepository? repository}) {
  return ProviderScope(
    overrides: [
      circleRepositoryProvider.overrideWithValue(
        repository ?? MockCircleRepository(),
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
  testWidgets('圈子创作容器先展示全部/点滴/作品，再进入作品格式筛选', (tester) async {
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

    expect(find.text('全部'), findsOneWidget);
    expect(find.text('点滴'), findsOneWidget);
    expect(find.text('作品'), findsAtLeastNWidgets(1));
    expect(find.text('微趣'), findsNothing);
    expect(find.text('文章'), findsNothing);

    await tester.tap(find.text('作品').first);
    await tester.pumpAndSettle();

    expect(find.text('图片'), findsAtLeastNWidgets(1));
    expect(find.text('视频'), findsAtLeastNWidgets(1));
    expect(find.text('文章'), findsAtLeastNWidgets(1));
  });

  testWidgets('圈子作品切到文章后，列表标签与筛选口径保持一致', (tester) async {
    final repository = _ArticleFixtureCircleRepository();
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
        repository: repository,
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('作品').first);
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('列表视图'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('文章').first);
    await tester.pumpAndSettle();

    expect(find.text('文章'), findsAtLeastNWidgets(1));
    expect(
      find.byKey(
        const ValueKey<String>('circle-article-list-fixture_article_with_cover'),
      ),
      findsOneWidget,
    );
    expect(find.textContaining('讨论推荐'), findsWidgets);
    expect(find.textContaining('赞 '), findsWidgets);
  });
}

class _ArticleFixtureCircleRepository extends MockCircleRepository {
  @override
  Future<CircleDetailPayload> getCircle(String circleId) async {
    return CircleDetailPayload.fromWire(<String, dynamic>{
      'id': circleId,
      'name': '契约摄影社',
      'ownerId': 'fixture_user_owner',
      'categoryId': 'photography',
      'visibility': 'public',
      'joinPolicy': 'approval',
      'createdAt': '2026-05-06T00:00:00Z',
      'updatedAt': '2026-05-06T00:00:00Z',
      'sectionConfig': const <Map<String, dynamic>>[],
    });
  }

  @override
  Future<List<PostBaseDto>> getCircleFeed(
    String circleId, {
    String? identity,
    String? type,
    String? cursor,
    int limit = 20,
    String sort = 'latest',
  }) async {
    final rows = <Map<String, dynamic>>[
      {
        'postId': 'fixture_article_with_cover',
        'id': 'fixture_article_with_cover',
        'contentType': 'article',
        'type': 'article',
        'contentIdentity': 'work',
        'identity': 'work',
        'authorId': 'fixture_user_photo',
        'authorNickname': '契约摄影师',
        'authorAvatarUrl': 'media/avatar/fixture_user_photo.png',
        'title': '山路晨雾手账',
        'summary': '把徒步笔记做成可翻页的旅途册。',
        'body': '把徒步笔记做成可翻页的旅途册。',
        'coverUrl': 'media/image/fixture_article_with_cover.jpg',
        'articleTemplate': 'journal',
        'articleFontPreset': 'handwritten',
        'likeCount': 164,
        'commentCount': 12,
        'shareCount': 11,
        'circleId': circleId,
        'createdAt': '2026-05-13T00:00:00Z',
      },
      {
        'postId': 'fixture_article_text_only',
        'id': 'fixture_article_text_only',
        'contentType': 'article',
        'type': 'article',
        'contentIdentity': 'work',
        'identity': 'work',
        'authorId': 'fixture_user_owner',
        'authorNickname': '纸上居',
        'authorAvatarUrl': 'media/avatar/fixture_user_owner.png',
        'title': '',
        'summary': '没有标题也没封面，只保留真正想被圈友读到的正文。',
        'body': '没有标题也没封面，只保留真正想被圈友读到的正文。',
        'coverUrl': '',
        'articleTemplate': 'gentle',
        'articleFontPreset': 'clean',
        'likeCount': 88,
        'commentCount': 6,
        'shareCount': 4,
        'circleId': circleId,
        'createdAt': '2026-05-13T01:00:00Z',
      },
    ];
    return rows.map(ArticlePostDto.fromMap).toList(growable: false);
  }
}
