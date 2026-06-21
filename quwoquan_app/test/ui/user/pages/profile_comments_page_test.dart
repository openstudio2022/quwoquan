import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/user/pages/profile_comments_page.dart';

void main() {
  testWidgets('「查看原评论」深链使用统一方言并携带 profile-comments 入口来源', (tester) async {
    final router = GoRouter(
      initialLocation: '/me/comments',
      routes: [
        GoRoute(
          path: '/me/comments',
          builder: (context, state) => const ProfileCommentsPage(),
        ),
        GoRoute(
          path: AppRoutePaths.workBrowserPathTemplate.replaceAll(
            '{workId}',
            ':workId',
          ),
          builder: (context, state) {
            final q = state.uri.queryParameters;
            return Text(
              '作品页:${state.pathParameters['workId'] ?? ''};'
              'openComments:${q[MediaViewerCommentContext.queryOpenComments] ?? ''};'
              'entrySource:${q[MediaViewerCommentContext.queryEntrySource] ?? ''};'
              'targetCommentId:${q[MediaViewerCommentContext.queryTargetCommentId] ?? ''};'
              'targetParentCommentId:${q[MediaViewerCommentContext.queryTargetParentCommentId] ?? ''};'
              'targetReplyId:${q[MediaViewerCommentContext.queryTargetReplyId] ?? ''}',
            );
          },
        ),
      ],
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          contentRepositoryProvider.overrideWithValue(
            _SeededAuthoredCommentRepository(),
          ),
        ],
        child: MaterialApp.router(
          locale: const Locale('zh'),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          routerConfig: router,
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    await tester.tap(find.text(UITextConstants.profileCommentViewOriginal));
    await tester.pumpAndSettle();

    expect(
      find.text(
        '作品页:post_pc_1;openComments:true;entrySource:profile-comments;'
        'targetCommentId:my_top_comment_1;targetParentCommentId:;targetReplyId:',
      ),
      findsOneWidget,
    );
  });

  testWidgets('评论页加载失败时展示统一页态', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          contentRepositoryProvider.overrideWithValue(
            _FailingCommentsRepository(),
          ),
        ],
        child: const MaterialApp(home: ProfileCommentsPage()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.byType(AppPageErrorState), findsOneWidget);
    expect(find.text(UITextConstants.contentNotLoadedYet), findsOneWidget);
    expect(find.text(UITextConstants.tryAgain), findsOneWidget);
  });
}

class _SeededAuthoredCommentRepository extends MockContentRepository {
  @override
  Future<CommentPage> listCommentsByAuthor({
    String? cursor,
    int limit = 20,
  }) async {
    return CommentPage(
      items: <CommentDto>[
        CommentDto(
          id: 'my_top_comment_1',
          postId: 'post_pc_1',
          authorId: 'me',
          displayName: '我',
          content: '我发出的一级评论',
          createdAt: DateTime.utc(2026, 1, 1),
        ),
      ],
      nextCursor: null,
      totalCount: 1,
    );
  }

  @override
  Future<CommentPage> listCommentsForPostAuthor({
    String? cursor,
    int limit = 20,
  }) async {
    return CommentPage(items: const <CommentDto>[], nextCursor: null);
  }
}

class _FailingCommentsRepository extends MockContentRepository {
  @override
  Future<CommentPage> listCommentsByAuthor({
    String? cursor,
    int limit = 20,
  }) async {
    throw StateError('comments unavailable');
  }

  @override
  Future<CommentPage> listCommentsForPostAuthor({
    String? cursor,
    int limit = 20,
  }) async {
    throw StateError('comments unavailable');
  }
}
