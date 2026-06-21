import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/cloud/runtime/models/comment_remote_config.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/components/comment_system/comment_sort_menu.dart';
import 'package:quwoquan_app/components/comment_system/comment_thread_view.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/providers/comment_provider.dart';

void main() {
  group('resolveCommentSortMenuPlacement 自适应翻转', () {
    test('下方空间充足时默认向下弹出', () {
      final placement = resolveCommentSortMenuPlacement(
        triggerTop: 100,
        triggerBottom: 132,
        menuHeight: 140,
        viewportTop: 44,
        // 视口底部已扣除底部工具栏，仍有足够空间放下菜单。
        viewportBottom: 700,
      );
      expect(placement, CommentSortMenuPlacement.below);
    });

    test('下方不足以避让底部工具栏、上方充足时翻转向上', () {
      final placement = resolveCommentSortMenuPlacement(
        triggerTop: 560,
        triggerBottom: 592,
        menuHeight: 140,
        viewportTop: 44,
        // 触发器靠近底部工具栏：下方放不下，上方足够。
        viewportBottom: 640,
      );
      expect(placement, CommentSortMenuPlacement.above);
    });

    test('两侧都放不下时选择更大的一侧', () {
      final placement = resolveCommentSortMenuPlacement(
        triggerTop: 120,
        triggerBottom: 160,
        menuHeight: 400,
        viewportTop: 44,
        viewportBottom: 360,
      );
      // 上方可用 120-44=76 > 下方可用 360-(160+4)=196? 这里下方更大 → below。
      expect(placement, CommentSortMenuPlacement.below);
    });
  });

  testWidgets('排序锚定菜单：默认综合、弹出三项、切换后回写并关闭', (tester) async {
    var current = CommentSortMode.recommended;
    final captured = <CommentSortMode>[];

    await tester.pumpWidget(
      CupertinoApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: CupertinoPageScaffold(
          child: StatefulBuilder(
            builder: (context, setState) {
              return Align(
                alignment: Alignment.topRight,
                child: CommentSortMenuButton(
                  isDark: false,
                  sortMode: current,
                  onChanged: (mode) {
                    captured.add(mode);
                    setState(() => current = mode);
                  },
                ),
              );
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // 默认显示「综合」，且未展开菜单。
    expect(find.byKey(TestKeys.commentSortMenuButton), findsOneWidget);
    expect(find.text(UITextConstants.commentSortRecommended), findsOneWidget);
    expect(find.byKey(TestKeys.commentSortMenuOverlay), findsNothing);

    // 点击触发器弹出锚定菜单，三项齐全。
    await tester.tap(find.byKey(TestKeys.commentSortMenuButton));
    await tester.pumpAndSettle();
    expect(find.byKey(TestKeys.commentSortMenuOverlay), findsOneWidget);
    expect(find.byKey(TestKeys.commentSortMenuItemRecommended), findsOneWidget);
    expect(find.byKey(TestKeys.commentSortMenuItemLatest), findsOneWidget);
    expect(find.byKey(TestKeys.commentSortMenuItemMostLiked), findsOneWidget);

    // 选择「最多赞」回写并关闭菜单，按钮文案更新。
    await tester.tap(find.byKey(TestKeys.commentSortMenuItemMostLiked));
    await tester.pumpAndSettle();
    expect(captured, [CommentSortMode.mostLiked]);
    expect(find.byKey(TestKeys.commentSortMenuOverlay), findsNothing);
    expect(find.text(UITextConstants.commentSortMostLiked), findsOneWidget);
  });

  testWidgets('排序锚定菜单：点击遮罩空白处关闭且不改排序', (tester) async {
    final captured = <CommentSortMode>[];
    await tester.pumpWidget(
      CupertinoApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: CupertinoPageScaffold(
          child: Align(
            alignment: Alignment.topRight,
            child: CommentSortMenuButton(
              isDark: false,
              sortMode: CommentSortMode.recommended,
              onChanged: captured.add,
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.commentSortMenuButton));
    await tester.pumpAndSettle();
    expect(find.byKey(TestKeys.commentSortMenuOverlay), findsOneWidget);

    // 点击左上角空白遮罩处关闭，不触发排序变更。
    await tester.tapAt(const Offset(8, 8));
    await tester.pumpAndSettle();
    expect(find.byKey(TestKeys.commentSortMenuOverlay), findsNothing);
    expect(captured, isEmpty);
  });

  testWidgets('排序锚定菜单：Overlay 文本包裹完整且不出现黄色下划线', (tester) async {
    await tester.pumpWidget(
      CupertinoApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: CupertinoPageScaffold(
          child: Align(
            alignment: Alignment.topRight,
            child: CommentSortMenuButton(
              isDark: false,
              sortMode: CommentSortMode.recommended,
              onChanged: (_) {},
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byIcon(CupertinoIcons.chevron_down), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.slider_horizontal_3), findsNothing);
    expect(find.byIcon(CupertinoIcons.line_horizontal_3), findsNothing);

    await tester.tap(find.byKey(TestKeys.commentSortMenuButton));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.commentSortMenuOverlay), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.check_mark), findsOneWidget);

    final menuTexts = tester.widgetList<Text>(
      find.descendant(
        of: find.byKey(TestKeys.commentSortMenuOverlay),
        matching: find.byType(Text),
      ),
    );
    expect(menuTexts, isNotEmpty);
    for (final text in menuTexts) {
      expect(text.style?.decoration, isNot(TextDecoration.underline));
      expect(text.style?.color, isNotNull);
    }
  });

  testWidgets('二级回复展开梯度：默认 1 → 首次最多 5 → 后续最多 10，标签随之切换', (tester) async {
    final repo = _PagingReplyRepository(totalReplies: 20);
    const postId = 'comment_reply_gradient_post';

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          contentRepositoryProvider.overrideWithValue(repo),
          analyticsProvider.overrideWithValue(AnalyticsService.forTesting()),
          // 默认梯度：预览 1、首展 5、续展 10。
          commentRemoteConfigProvider.overrideWithValue(
            const CommentRemoteConfig(),
          ),
        ],
        child: CupertinoApp(
          locale: const Locale('zh'),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: const CupertinoPageScaffold(
            child: SingleChildScrollView(
              child: CommentThreadView(
                postId: postId,
                shrinkWrap: true,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // 预览态：仅 1 条回复（引用昵称富文本），首展标签为「展开 N 条回复」。
    expect(find.text('回复者0：回复 #0', findRichText: true), findsOneWidget);
    expect(find.text('回复者1：回复 #1', findRichText: true), findsNothing);
    expect(find.text('展开 19 条回复'), findsOneWidget);

    // 首次展开：limit=5（首屏梯度）。
    await tester.tap(find.byKey(TestKeys.commentReplyExpand));
    await tester.pumpAndSettle();
    expect(repo.requestedLimits, [5]);
    expect(find.text('回复者5：回复 #5', findRichText: true), findsOneWidget);
    // 仍有剩余回复：标签切换为「展开更多回复」。
    expect(find.text(UITextConstants.commentExpandMoreReplies), findsOneWidget);

    // 后续展开：limit=10（续展梯度）。
    await tester.tap(find.byKey(TestKeys.commentReplyExpand));
    await tester.pumpAndSettle();
    expect(repo.requestedLimits, [5, 10]);
    expect(find.text('回复者15：回复 #15', findRichText: true), findsOneWidget);
  });
}

/// 受控分页回复仓储：父评论携带 [totalReplies] 条真实子回复，
/// 复用 Mock 的预览/分页语义（预览 1 条、按 limit 游标分页），
/// 仅记录每次展开请求的 limit，便于断言展开梯度（首展 5 / 续展 10）。
class _PagingReplyRepository extends MockContentRepository {
  _PagingReplyRepository({required this.totalReplies}) {
    commentsStub = <CommentDto>[
      CommentDto(
        id: 'parent',
        postId: 'comment_reply_gradient_post',
        authorId: 'author_parent',
        displayName: '一级评论者',
        content: '一级评论',
        createdAt: DateTime.utc(2026, 1, 1),
      ),
      for (var i = 0; i < totalReplies; i++)
        CommentDto(
          id: 'reply_$i',
          postId: 'comment_reply_gradient_post',
          authorId: 'author_$i',
          displayName: '回复者$i',
          content: '回复 #$i',
          parentCommentId: 'parent',
          replyToCommentId: 'parent',
          createdAt: DateTime.utc(2026, 1, 2).add(Duration(minutes: i)),
        ),
    ];
  }

  final int totalReplies;
  final List<int> requestedLimits = <int>[];

  @override
  Future<CommentPage> listCommentReplies({
    required String postId,
    required String commentId,
    String? cursor,
    int limit = 10,
  }) async {
    requestedLimits.add(limit);
    return super.listCommentReplies(
      postId: postId,
      commentId: commentId,
      cursor: cursor,
      limit: limit,
    );
  }
}
