import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer_modal.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';

void main() {
  testWidgets('评论面板以非全屏底部面板呈现', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: Builder(
              builder: (context) => CupertinoButton(
                onPressed: () => CommentViewer.showModal(
                  context: context,
                  postId: 'mock-post-id',
                ),
                child: const Text('open-comments'),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open-comments'));
    await tester.pumpAndSettle();

    final panel = find.byKey(TestKeys.modalBottomSheetPanel);
    expect(panel, findsOneWidget);
    expect(tester.getTopLeft(panel).dy, greaterThan(0));
  });

  testWidgets('评论区支持 @小趣 快捷入口与小趣回复卡', (tester) async {
    final repo = MockContentRepository()
      ..commentsStub = [
        CommentDto(
          id: 'assistant_comment_1',
          postId: 'mock-post-id',
          authorId: 'assistant',
          displayName: '小趣',
          content: '我帮你补充一下：这张作品适合继续说明拍摄地点和时间。',
          createdAt: DateTime.utc(2026, 5, 1),
        ),
      ];
    await tester.pumpWidget(
      ProviderScope(
        overrides: [contentRepositoryProvider.overrideWithValue(repo)],
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: Builder(
              builder: (context) => CupertinoButton(
                onPressed: () => CommentViewer.showModal(
                  context: context,
                  postId: 'mock-post-id',
                ),
                child: const Text('open-comments'),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open-comments'));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.commentAtXiaoquButton), findsOneWidget);
    expect(find.byKey(TestKeys.commentXiaoquReplyCard), findsOneWidget);

    await tester.tap(find.byKey(TestKeys.commentAtXiaoquButton));
    await tester.pump();

    final field = tester.widget<TextField>(
      find.byKey(TestKeys.commentTextField),
    );
    expect(field.controller?.text, startsWith('@小趣 '));
  });
}
