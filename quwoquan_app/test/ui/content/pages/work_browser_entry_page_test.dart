import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/pages/work_browser_entry_page.dart';

void main() {
  Future<String> firstReadablePostId(MockContentRepository repo) async {
    for (final category in <String>['article', 'photo', 'video', 'moment']) {
      final posts = await repo.listDiscoveryFeed(category: category, limit: 8);
      for (final post in posts) {
        try {
          await repo.getPost(postId: post.id);
          return post.id;
        } catch (_) {
          // skip unreadable seed rows
        }
      }
    }
    fail('seed feed 中应至少有一个 getPost 可读的帖');
  }

  testWidgets('直达入口：workId 在详情不可读时呈现显式错误态而非无关内容', (tester) async {
    final repo = MockContentRepository();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [contentRepositoryProvider.overrideWithValue(repo)],
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, _) => MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: const WorkBrowserEntryPage(
              workId: 'definitely-missing-post-id',
              source: 'deep-link-test',
            ),
          ),
        ),
      ),
    );

    // 初始为加载态。
    expect(
      find.byKey(const ValueKey('work-browser-entry-loading')),
      findsOneWidget,
    );

    await tester.pumpAndSettle();

    // 详情拉取失败 → 显式错误态，绝不回退渲染发现页推荐流（先前断点）。
    expect(
      find.byKey(const ValueKey('work-browser-entry-error')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('work-browser-entry-loading')),
      findsNothing,
    );
  });

  testWidgets('直达入口：空 workId 直接进入错误态', (tester) async {
    final repo = MockContentRepository();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [contentRepositoryProvider.overrideWithValue(repo)],
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, _) => MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: const WorkBrowserEntryPage(workId: '   '),
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('work-browser-entry-error')),
      findsOneWidget,
    );
  });

  testWidgets('直达入口：评论原文跳转会消费 openComments 上下文', (tester) async {
    final repo = MockContentRepository();
    final postId = await firstReadablePostId(repo);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [contentRepositoryProvider.overrideWithValue(repo)],
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, _) => MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: WorkBrowserEntryPage(
              workId: postId,
              source: 'profile-comments',
              commentContext: const MediaViewerCommentContext(
                openComments: true,
              ),
            ),
          ),
        ),
      ),
    );

    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.immersiveCommentSplitSheet), findsOneWidget);
    expect(
      find.byKey(const ValueKey('work-browser-entry-error')),
      findsNothing,
    );
  });
}
