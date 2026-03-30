import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/pages/article_detail_page.dart';

class _ArticleGetPostRepo extends MockContentRepository {
  _ArticleGetPostRepo(this._item);

  final Map<String, dynamic> _item;

  @override
  Future<Map<String, dynamic>> getPost({required String postId}) async =>
      _item;
}

void main() {
  testWidgets('ArticleDetailPage 渲染连续图文阅读布局', (tester) async {
    final article = <String, dynamic>{
      'postId': 'art_continuous',
      'contentType': 'article',
      'authorId': 'writer1',
      'displayName': '连续阅读作者',
      'authorAvatarUrl': 'https://example.com/avatar.jpg',
      'title': '连续阅读标题',
      'body': '这里是摘要',
      'coverUrl': 'https://example.com/cover.jpg',
      'likeCount': 12,
      'commentCount': 4,
      'favoriteCount': 6,
      'shareCount': 3,
      'publishedAt': '2026-03-21T08:00:00Z',
      'articleBlocks': <Map<String, dynamic>>[
        {'id': 'p1', 'type': 'paragraph', 'text': '第一段内容', 'imagePath': ''},
        {'id': 'o1', 'type': 'orderedItem', 'text': '第二条清单', 'imagePath': ''},
        {
          'id': 'i1',
          'type': 'image',
          'text': '',
          'imagePath': 'https://example.com/inline.jpg',
        },
      ],
    };

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          contentRepositoryProvider.overrideWithValue(
            _ArticleGetPostRepo(article),
          ),
          behaviorRepositoryProvider.overrideWithValue(
            MockBehaviorRepository(),
          ),
        ],
        child: MaterialApp(
          locale: const Locale('zh'),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: const ArticleDetailPage(articleId: 'art_continuous'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('连续阅读标题'), findsWidgets);
    expect(find.text('连续阅读作者'), findsOneWidget);
    expect(find.text('文章内容'), findsOneWidget);
    expect(find.textContaining('第一段内容'), findsWidgets);
    expect(find.textContaining('1. 第二条清单'), findsWidgets);
    expect(find.byType(CachedNetworkImage), findsNWidgets(3));
    expect(find.text('分享'), findsOneWidget);
  });
}
