import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/runtime/models/comment_remote_config.dart';
import 'package:quwoquan_app/components/comment_system/immersive_comment_split_sheet.dart';
import 'package:quwoquan_app/components/comment_system/comment_thread_view.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer_modal.dart';
import 'package:quwoquan_app/components/comment_system/inline_article_comment_section.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/providers/comment_provider.dart';

void main() {
  testWidgets('评论面板以非全屏底部面板呈现并贴底工具栏', (tester) async {
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
    // 贴底工具栏（图一）：左输入条 + 右计数；尚未展开输入态时无 TextField。
    expect(find.byKey(TestKeys.commentToolbar), findsOneWidget);
    expect(find.byKey(TestKeys.commentTextField), findsNothing);
  });

  testWidgets('点击输入条弹出统一输入浮层，@小趣 写入输入框', (tester) async {
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
    expect(find.textContaining('我帮你补充一下'), findsOneWidget);

    // 点击底部输入条弹出统一输入浮层（图二）。
    await tester.tap(find.byKey(TestKeys.commentInputBar));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.commentInputOverlay), findsOneWidget);
    // 输入框是 CupertinoTextField（无 Material 依赖，沉浸式壳下不再崩溃）。
    expect(find.byType(CupertinoTextField), findsOneWidget);
    expect(find.byKey(TestKeys.commentAtXiaoquButton), findsOneWidget);

    await tester.tap(find.byKey(TestKeys.commentAtXiaoquButton));
    await tester.pump();

    final field = tester.widget<CupertinoTextField>(
      find.byKey(TestKeys.commentTextField),
    );
    expect(field.controller?.text, startsWith('@小趣 '));
  });

  testWidgets(
    '沉浸式评论分屏：保留内容上下文、默认占据评论区且无 Material 报错',
    testImmersiveCommentSplitJourney,
  );

  testWidgets(
    '平铺文章评论区内联展示且不推入 modal 路由',
    testArticleInlineCommentJourney,
  );

  testWidgets(
    'testCommentReplyPreviewUsesConfig: reply preview 与展开配置生效',
    testCommentReplyPreviewUsesConfig,
  );

  testWidgets(
    'testCommentReactionThreeStateWidget: like / dislike / none 三态互斥',
    testCommentReactionThreeStateWidget,
  );

  test('评论轮询发现新评论后可点击刷新快照', () async {
    final repo = MockContentRepository()
      ..commentsStub = [
        CommentDto(
          id: 'comment_old',
          postId: 'polling-post-id',
          authorId: 'user_1',
          content: '旧评论',
          recommendedScore: 1,
          createdAt: DateTime.utc(2026, 6, 1),
        ),
      ];
    final container = ProviderContainer(
      overrides: [
        contentRepositoryProvider.overrideWithValue(repo),
        analyticsProvider.overrideWithValue(AnalyticsService.forTesting()),
      ],
    );
    addTearDown(container.dispose);

    final notifier = container.read(
      commentProviderFamily('polling-post-id').notifier,
    );
    await notifier.loadComments();
    expect(
      container
          .read(commentProviderFamily('polling-post-id'))
          .comments
          .first
          .id,
      'comment_old',
    );

    repo.commentsStub = [
      ...repo.commentsStub,
      CommentDto(
        id: 'comment_new',
        postId: 'polling-post-id',
        authorId: 'user_2',
        content: '新评论',
        recommendedScore: 10,
        createdAt: DateTime.utc(2026, 6, 2),
      ),
    ];
    await notifier.checkForNewComments();
    expect(
      container.read(commentProviderFamily('polling-post-id')).hasNewComments,
      isTrue,
    );

    await notifier.refreshFromNewCommentNotice();
    final state = container.read(commentProviderFamily('polling-post-id'));
    expect(state.hasNewComments, isFalse);
    expect(state.comments.first.id, 'comment_new');
  });
}

class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() {
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'test-token',
      refreshToken: 'test-refresh',
      ownerId: 'test-user',
      activeSubAccountId: 'test-sub-account',
      accountState: 'active',
      identityOrigin: 'test',
      installId: 'test-install',
    );
  }
}

class _ReplyTrackingRepository extends MockContentRepository {
  int? lastReplyLimit;

  @override
  Future<CommentPage> listCommentReplies({
    required String postId,
    required String commentId,
    String? cursor,
    int limit = 10,
  }) async {
    lastReplyLimit = limit;
    return super.listCommentReplies(
      postId: postId,
      commentId: commentId,
      cursor: cursor,
      limit: limit,
    );
  }
}

Widget _threadTestApp({
  required MockContentRepository repo,
  required Widget child,
  CommentRemoteConfig commentConfig = const CommentRemoteConfig(),
  bool authenticated = false,
}) {
  return ProviderScope(
    overrides: [
      contentRepositoryProvider.overrideWithValue(repo),
      analyticsProvider.overrideWithValue(AnalyticsService.forTesting()),
      commentRemoteConfigProvider.overrideWithValue(commentConfig),
      if (authenticated)
        authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
    ],
    child: CupertinoApp(
      locale: const Locale('zh'),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: CupertinoPageScaffold(child: child),
    ),
  );
}

CommentDto _comment({
  required String id,
  required String postId,
  required String authorId,
  required String content,
  String? displayName,
  String? avatarUrl,
  String? replyToCommentId,
  String? parentCommentId,
  int replyCount = 0,
  List<CommentDto> replyPreview = const <CommentDto>[],
  String? replyNextCursor,
  int likeCount = 0,
  int dislikeCount = 0,
  String viewerReaction = 'none',
  bool canReply = true,
  bool canDelete = false,
  bool canReport = false,
  DateTime? createdAt,
}) {
  return CommentDto(
    id: id,
    postId: postId,
    authorId: authorId,
    displayName: displayName,
    avatarUrl: avatarUrl,
    content: content,
    replyToCommentId: replyToCommentId,
    parentCommentId: parentCommentId,
    replyCount: replyCount,
    replyPreview: replyPreview,
    replyNextCursor: replyNextCursor,
    likeCount: likeCount,
    dislikeCount: dislikeCount,
    viewerReaction: viewerReaction,
    canReply: canReply,
    canDelete: canDelete,
    canReport: canReport,
    createdAt: createdAt ?? DateTime.utc(2026, 1, 1),
  );
}

Future<void> testCommentReplyPreviewUsesConfig(WidgetTester tester) async {
  final repo = _ReplyTrackingRepository();
  const postId = 'comment_reply_preview_post';
  final replyOne = _comment(
    id: 'comment_reply_1',
    postId: postId,
    authorId: 'user_reply_1',
    displayName: '第一位回复者',
    content: '第一条回复',
    parentCommentId: 'comment_parent',
    replyToCommentId: 'comment_parent',
    createdAt: DateTime.utc(2026, 1, 2),
  );
  final replyTwo = _comment(
    id: 'comment_reply_2',
    postId: postId,
    authorId: 'user_reply_2',
    displayName: '第二位回复者',
    content: '第二条回复',
    parentCommentId: 'comment_parent',
    replyToCommentId: 'comment_parent',
    createdAt: DateTime.utc(2026, 1, 3),
  );
  final parent = _comment(
    id: 'comment_parent',
    postId: postId,
    authorId: 'user_parent',
    displayName: '一级评论者',
    content: '一级评论',
    replyCount: 2,
    replyPreview: <CommentDto>[replyOne],
    replyNextCursor: '1',
    createdAt: DateTime.utc(2026, 1, 1),
  );
  repo.commentsStub = <CommentDto>[parent, replyOne, replyTwo];

  await tester.pumpWidget(
    _threadTestApp(
      repo: repo,
      commentConfig: const CommentRemoteConfig(
        replyPreviewCount: 1,
        replyExpandPageSize: 2,
      ),
      child: const CommentThreadView(
        postId: postId,
        showHeader: false,
        shrinkWrap: true,
      ),
    ),
  );
  await tester.pumpAndSettle();

  final container = ProviderScope.containerOf(
    tester.element(find.byType(CupertinoPageScaffold)),
  );
  final state = container.read(commentProviderFamily(postId));
  expect(state.replyPreviewCount, equals(1));
  expect(state.replyExpandPageSize, equals(2));
  expect(find.text('一级评论'), findsOneWidget);
  expect(find.text('第一位回复者：第一条回复'), findsOneWidget);
  expect(find.text('第二位回复者：第二条回复'), findsNothing);
  expect(find.text('展开 1 条回复'), findsOneWidget);

  await tester.tap(find.text('展开 1 条回复'));
  await tester.pumpAndSettle();

  expect(repo.lastReplyLimit, equals(2));
  expect(find.text('第二位回复者：第二条回复'), findsOneWidget);
  expect(find.text('展开 1 条回复'), findsNothing);
}

Future<void> testCommentReactionThreeStateWidget(
  WidgetTester tester,
) async {
  final repo = _ReplyTrackingRepository();
  const postId = 'comment_reaction_post';
  repo.commentsStub = <CommentDto>[
    _comment(
      id: 'comment_reaction_1',
      postId: postId,
      authorId: 'user_reaction',
      displayName: '反应评论者',
      content: '三态评论',
      likeCount: 3,
      dislikeCount: 1,
      viewerReaction: 'like',
      canReply: false,
      canDelete: false,
      canReport: false,
      createdAt: DateTime.utc(2026, 1, 1),
    ),
  ];

  await tester.pumpWidget(
    _threadTestApp(
      repo: repo,
      authenticated: true,
      child: const CommentThreadView(
        postId: postId,
        showHeader: false,
        shrinkWrap: true,
      ),
    ),
  );
  await tester.pumpAndSettle();

  expect(find.byIcon(CupertinoIcons.heart_fill), findsOneWidget);
  expect(find.byIcon(CupertinoIcons.hand_thumbsdown), findsOneWidget);

  await tester.tap(find.byIcon(CupertinoIcons.hand_thumbsdown));
  await tester.pumpAndSettle();
  expect(repo.commentsStub.single.viewerReaction, equals('dislike'));
  expect(find.byIcon(CupertinoIcons.heart), findsOneWidget);
  expect(find.byIcon(CupertinoIcons.hand_thumbsdown_fill), findsOneWidget);

  await tester.tap(find.byIcon(CupertinoIcons.hand_thumbsdown_fill));
  await tester.pumpAndSettle();
  expect(repo.commentsStub.single.viewerReaction, equals('none'));
  expect(find.byIcon(CupertinoIcons.heart), findsOneWidget);
  expect(find.byIcon(CupertinoIcons.hand_thumbsdown), findsOneWidget);
  expect(find.byIcon(CupertinoIcons.heart_fill), findsNothing);
  expect(find.byIcon(CupertinoIcons.hand_thumbsdown_fill), findsNothing);

  await tester.tap(find.byIcon(CupertinoIcons.heart));
  await tester.pumpAndSettle();
  expect(repo.commentsStub.single.viewerReaction, equals('like'));
  expect(find.byIcon(CupertinoIcons.heart_fill), findsOneWidget);
}

Future<void> testImmersiveCommentSplitJourney(WidgetTester tester) async {
  final repo = MockContentRepository()
    ..commentsStub = [
      CommentDto(
        id: 'comment_1',
        postId: 'immersive-post-id',
        authorId: 'user_1',
        displayName: '旅行者',
        content: '这条路线很适合下午出发。',
        createdAt: DateTime.utc(2026, 6, 1),
      ),
    ];

  await tester.pumpWidget(
    ProviderScope(
      overrides: [contentRepositoryProvider.overrideWithValue(repo)],
      child: CupertinoApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: const CupertinoPageScaffold(
          child: ImmersiveCommentSplitSheet(
            postId: 'immersive-post-id',
            content: Text('immersive-content'),
          ),
        ),
      ),
    ),
  );

  await tester.pump();
  await tester.pump();

  expect(find.byKey(TestKeys.immersiveCommentSplitSheet), findsOneWidget);
  expect(find.text('immersive-content'), findsOneWidget);
  expect(find.byKey(TestKeys.commentThreadView), findsOneWidget);
  expect(find.byKey(TestKeys.commentToolbar), findsOneWidget);

  // 点击输入条弹出统一输入浮层（CupertinoTextField），验证沉浸式壳下不再抛
  // “No Material widget found”。
  await tester.tap(find.byKey(TestKeys.commentInputBar));
  await tester.pumpAndSettle();
  expect(find.byKey(TestKeys.commentInputOverlay), findsOneWidget);
  expect(find.byType(CupertinoTextField), findsOneWidget);
  expect(tester.takeException(), isNull);
}

Future<void> testArticleInlineCommentJourney(WidgetTester tester) async {
  final repo = MockContentRepository()
    ..commentsStub = [
      CommentDto(
        id: 'comment_inline_1',
        postId: 'post_article_inline_001',
        authorId: 'user_1',
        displayName: '读者甲',
        content: '文章结构很清晰。',
        createdAt: DateTime.utc(2026, 6, 1),
      ),
    ];
  final routeObserver = _RoutePushCountObserver();

  await tester.pumpWidget(
    ProviderScope(
      overrides: [contentRepositoryProvider.overrideWithValue(repo)],
      child: CupertinoApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        navigatorObservers: [routeObserver],
        home: const CupertinoPageScaffold(
          child: CustomScrollView(
            slivers: [
              SliverToBoxAdapter(child: Text('article-flat-body')),
              SliverToBoxAdapter(
                child: InlineArticleCommentSection(
                  postId: 'post_article_inline_001',
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );

  await tester.pump();
  await tester.pump();
  final pushesAfterFirstFrame = routeObserver.pushCount;

  // 评论区平铺在正文之后，与正文同处一条滚动流。
  expect(find.byKey(TestKeys.inlineArticleCommentSection), findsOneWidget);
  expect(find.text('article-flat-body'), findsOneWidget);
  expect(find.byKey(TestKeys.commentThreadView), findsOneWidget);

  // 内联展示评论不推入任何 modal 路由。
  expect(routeObserver.pushCount, pushesAfterFirstFrame);
  expect(tester.takeException(), isNull);
}

class _RoutePushCountObserver extends NavigatorObserver {
  int pushCount = 0;

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    if (previousRoute != null) {
      pushCount += 1;
    }
    super.didPush(route, previousRoute);
  }
}
