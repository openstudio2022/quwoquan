library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/cloud/runtime/models/comment_remote_config.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/ui/content/comments/widgets/comment_detail_surface.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';

class _EntryCountRepository extends MockContentRepository {
  _EntryCountRepository({required this.postId, required this.totalCount}) {
    _seedComments(totalCount);
  }

  final String postId;
  int totalCount;

  void updateTotalCount(int next) {
    totalCount = next;
    _seedComments(next);
  }

  void _seedComments(int count) {
    commentsStub = List<CommentDto>.generate(
      count,
      (index) => CommentDto(
        id: 'comment_$index',
        postId: postId,
        authorId: 'user_$index',
        displayName: '用户$index',
        content: '评论 $index',
        createdAt: DateTime.utc(2026, 6, 1).add(Duration(minutes: index)),
      ),
      growable: false,
    );
  }

  @override
  Future<CommentPage> listComments({
    required String postId,
    String? cursor,
    String sort = 'recommended',
    int limit = 20,
  }) async {
    return CommentPage(
      items: commentsStub.take(3).toList(growable: false),
      nextCursor: null,
      totalCount: totalCount,
    );
  }
}

Widget _app(
  _EntryCountRepository repo, {
  required String postId,
  int? entryObservedCommentCount,
}) {
  return ProviderScope(
    overrides: [
      contentRepositoryProvider.overrideWithValue(repo),
      analyticsProvider.overrideWithValue(AnalyticsService.forTesting()),
      commentRemoteConfigProvider.overrideWithValue(
        const CommentRemoteConfig(),
      ),
    ],
    child: CupertinoApp(
      locale: const Locale('zh'),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: CupertinoPageScaffold(
        child: CommentDetailSurface(
          postId: postId,
          mode: CommentDetailSurfaceMode.cardModal,
          entryObservedCommentCount: entryObservedCommentCount,
        ),
      ),
    ),
  );
}

Future<void> _settle(WidgetTester tester, {int frames = 10}) async {
  for (var i = 0; i < frames; i++) {
    await tester.pump(const Duration(milliseconds: 20));
  }
}

void main() {
  testWidgets('打开前 10 条、首刷 12 条时只展示一次性新增说明', (tester) async {
    const postId = 'entry-count-created';
    final repo = _EntryCountRepository(postId: postId, totalCount: 12);

    await tester.pumpWidget(
      _app(repo, postId: postId, entryObservedCommentCount: 10),
    );
    await _settle(tester);

    final notice = find.byKey(TestKeys.commentEntryConsistencyNotice);
    expect(notice, findsOneWidget);
    expect(find.text('较打开前新增 2 条评论'), findsOneWidget);
    expect(find.textContaining('点击刷新'), findsNothing);
  });

  testWidgets('打开前 10 条、首刷 8 条时只展示一次性删除说明', (tester) async {
    const postId = 'entry-count-deleted';
    final repo = _EntryCountRepository(postId: postId, totalCount: 8);

    await tester.pumpWidget(
      _app(repo, postId: postId, entryObservedCommentCount: 10),
    );
    await _settle(tester);

    final notice = find.byKey(TestKeys.commentEntryConsistencyNotice);
    expect(notice, findsOneWidget);
    expect(find.text('较打开前删除 2 条评论'), findsOneWidget);
    expect(find.textContaining('点击刷新'), findsNothing);
  });

  testWidgets('详情停留期间不再出现页内轮询提示', (tester) async {
    const postId = 'entry-count-static-session';
    final repo = _EntryCountRepository(postId: postId, totalCount: 10);

    await tester.pumpWidget(
      _app(repo, postId: postId, entryObservedCommentCount: 10),
    );
    await _settle(tester);

    expect(find.byKey(TestKeys.commentEntryConsistencyNotice), findsNothing);

    repo.updateTotalCount(12);
    await tester.pump(const Duration(seconds: 35));
    await _settle(tester, frames: 4);

    expect(find.byKey(TestKeys.commentEntryConsistencyNotice), findsNothing);
  });
}
