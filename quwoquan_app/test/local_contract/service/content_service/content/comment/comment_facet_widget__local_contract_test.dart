// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-001
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/comment/application/public/comment_remote_config.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/service/content_service/content/comment/application/comment_provider.dart';
import 'package:quwoquan_app/service/content_service/content/comment/presentation/comment_thread_view.dart';
import 'package:quwoquan_app/service/content_service/content/comment/presentation/comment_viewer_modal.dart';

import '../../../../../support/service/content_service/content/comment/in_memory_content_comment_facet.dart';

void main() {
  testWidgets('Comment modal 只消费 typed Facet 投影', (tester) async {
    final comments = InMemoryContentCommentFacet(
      items: <CommentListItem>[
        testCommentItem(
          id: 'comment-1',
          postId: 'post-1',
          authorDisplayNameSnapshot: '端云用户',
          content: '强类型评论投影',
          likeCount: 2,
        ),
      ],
    );

    await tester.pumpWidget(
      _app(
        comments,
        Builder(
          builder: (context) => CupertinoButton(
            onPressed: () =>
                CommentViewer.showModal(context: context, postId: 'post-1'),
            child: const Text('open-comments'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open-comments'));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.modalBottomSheetPanel), findsOneWidget);
    expect(find.text('端云用户'), findsOneWidget);
    expect(find.text('强类型评论投影'), findsOneWidget);
    expect(comments.queryCalls, greaterThan(0));
  });

  testWidgets('评论首屏失败使用无卡片外框的区块错误态并可重试', (tester) async {
    final comments = InMemoryContentCommentFacet()
      ..failure = StateError('comment load failed');

    await tester.pumpWidget(
      _app(comments, const CommentThreadView(postId: 'post-failure')),
    );
    await tester.pumpAndSettle();

    expect(find.byType(AppSectionErrorState), findsOneWidget);
    expect(find.byType(AppSectionErrorCard), findsNothing);
    expect(find.text(SearchText.recoveryInvalidContentTitle), findsOneWidget);
    expect(find.text(SearchText.recoveryInvalidContentMessage), findsOneWidget);
    expect(find.text(SearchText.reload), findsOneWidget);

    comments.failure = null;
    await tester.tap(find.text(SearchText.reload));
    await tester.pumpAndSettle();

    expect(find.byType(AppSectionErrorState), findsNothing);
    expect(find.text(ContentText.noComment), findsOneWidget);
  });

  testWidgets('评论弹层首屏失败不把未知总数误写成零评论', (tester) async {
    final comments = InMemoryContentCommentFacet()
      ..failure = StateError('comment load failed');

    await tester.pumpWidget(
      _app(
        comments,
        Builder(
          builder: (context) => CupertinoButton(
            onPressed: () =>
                CommentViewer.showModal(context: context, postId: 'post-error'),
            child: const Text('open-error-comments'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open-error-comments'));
    await tester.pumpAndSettle();

    expect(find.text(FoundationText.comment), findsOneWidget);
    expect(
      find.text(ContentText.commentCountTitleTemplate.replaceFirst('%s', '0')),
      findsNothing,
    );
    expect(find.byType(AppSectionErrorState), findsOneWidget);
  });

  testWidgets('Comment provider 不跨会话容器复用静态快照', (tester) async {
    const postId = 'post-session-isolation';
    final firstComments = InMemoryContentCommentFacet(
      items: <CommentListItem>[
        testCommentItem(
          id: 'first-session-comment',
          postId: postId,
          content: '前一会话的评论',
        ),
      ],
    );
    final firstContainer = ProviderContainer(
      overrides: [
        workBrowserContentCommentFacetProvider.overrideWithValue(firstComments),
        commentRemoteConfigProvider.overrideWithValue(
          const CommentRemoteConfig(),
        ),
      ],
    );
    final firstListener = firstContainer.listen(
      commentProviderFamily(postId),
      (_, _) {},
    );
    await firstContainer
        .read(commentProviderFamily(postId).notifier)
        .loadComments();
    expect(
      firstContainer
          .read(commentProviderFamily(postId))
          .comments
          .single
          .content,
      '前一会话的评论',
    );
    firstListener.close();
    firstContainer.dispose();
    await tester.pump();

    final secondComments = InMemoryContentCommentFacet(
      items: <CommentListItem>[
        testCommentItem(
          id: 'second-session-comment',
          postId: postId,
          content: '当前会话的评论',
        ),
      ],
    );
    final secondContainer = ProviderContainer(
      overrides: [
        workBrowserContentCommentFacetProvider.overrideWithValue(
          secondComments,
        ),
        commentRemoteConfigProvider.overrideWithValue(
          const CommentRemoteConfig(),
        ),
      ],
    );

    expect(
      secondContainer.read(commentProviderFamily(postId)).comments,
      isEmpty,
      reason: '新的会话必须从 Remote 权威投影加载，不能复用上一会话的 Comment 快照',
    );
    secondContainer.dispose();
    await tester.pump();
  });

  testWidgets('点赞经 typed reaction command 并用结果更新页态', (tester) async {
    final comments = InMemoryContentCommentFacet(
      items: <CommentListItem>[
        testCommentItem(
          id: 'comment-like',
          postId: 'post-like',
          content: '可点赞评论',
        ),
      ],
    );
    await tester.pumpWidget(
      _app(
        comments,
        const CommentThreadView(postId: 'post-like'),
        authenticated: true,
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(CupertinoIcons.heart));
    await tester.pumpAndSettle();

    expect(comments.reactionCalls, 1);
    expect(comments.lastReactionCommand?.reaction, CommentReactionType.like);
    expect(find.byIcon(CupertinoIcons.heart_fill), findsOneWidget);
  });

  testWidgets('点赞失败回滚乐观态并以统一恢复语义轻提示，不泄漏异常', (tester) async {
    final comments = InMemoryContentCommentFacet(
      items: <CommentListItem>[
        testCommentItem(
          id: 'comment-like-fail',
          postId: 'post-like-fail',
          content: '点赞会失败的评论',
        ),
      ],
    );
    await tester.pumpWidget(
      _app(
        comments,
        const CommentThreadView(postId: 'post-like-fail'),
        authenticated: true,
      ),
    );
    await tester.pumpAndSettle();

    final reactionFailure = StateError('reaction unavailable');
    comments.failure = reactionFailure;
    await tester.tap(find.byIcon(CupertinoIcons.heart));
    await tester.pumpAndSettle();

    // 乐观红心已回滚，用户不会停留在假成功态。
    expect(find.byIcon(CupertinoIcons.heart_fill), findsNothing);
    expect(find.byIcon(CupertinoIcons.heart), findsOneWidget);

    // 轻提示文案与统一 resolver 同源计算，不手写字面量。
    final context = tester.element(find.byType(CommentThreadView));
    final expectedMessage = runtimeErrorSemantic(
      context,
      error: reactionFailure,
      category: UiErrorCategory.backgroundAction,
      scope: UiErrorScope.global,
      allowRetry: false,
    ).message;
    expect(find.text(expectedMessage), findsOneWidget);

    // 异常已被 presentation helper 吸收，不进入 unhandled zone。
    expect(tester.takeException(), isNull);

    // 让 AppToast 的自动消失计时器走完，避免 pending timer。
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets(
    '回复预览数量由 CommentRemoteConfig 驱动，展开只调用 typed listReplies',
    testCommentReplyPreviewUsesConfig,
  );

  testWidgets(
    '评论赞踩三态互斥，已赞态切换踩后以 typed result 确认',
    testCommentReactionThreeStateWidget,
  );

  testWidgets('置顶操作经 typed 命名命令执行', (tester) async {
    final comments = InMemoryContentCommentFacet(
      items: <CommentListItem>[
        testCommentItem(
          id: 'comment-pin',
          postId: 'post-pin',
          content: '可置顶评论',
          version: 7,
          canPin: true,
        ),
      ],
    );
    await tester.pumpWidget(
      _app(
        comments,
        const CommentThreadView(postId: 'post-pin'),
        authenticated: true,
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(CupertinoIcons.pin));
    await tester.pumpAndSettle();

    expect(comments.pinCalls, 1);
    expect(comments.lastPinCommand?.postId, 'post-pin');
    expect(comments.lastPinCommand?.commentId, 'comment-pin');
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('热门最新与评论动作具备 44pt 语义，窄屏大字体 badge 不溢出', (tester) async {
    tester.view.physicalSize = const Size(320, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final comments = InMemoryContentCommentFacet(
      items: <CommentListItem>[
        testCommentItem(
          id: 'comment-accessibility',
          postId: 'post-accessibility',
          authorDisplayNameSnapshot: '一位拥有很长昵称的评论作者',
          content: '窄屏和动态字体下仍然完整显示的评论正文',
          isPinned: true,
          isAuthor: true,
          authorLiked: true,
          authorIpLocation: '新疆维吾尔自治区',
          viewerRelation: CommentViewerRelation.friend,
        ),
      ],
    );

    await tester.pumpWidget(
      _app(
        comments,
        MediaQuery(
          data: const MediaQueryData(textScaler: TextScaler.linear(2)),
          child: const CommentThreadView(postId: 'post-accessibility'),
        ),
        authenticated: true,
      ),
    );
    await tester.pumpAndSettle();

    final hot = find.bySemanticsLabel(ContentText.commentSortHot).first;
    final latest = find.bySemanticsLabel(ContentText.commentSortLatest).first;
    expect(tester.getSize(hot).height, greaterThanOrEqualTo(44));
    expect(tester.getSize(latest).height, greaterThanOrEqualTo(44));
    expect(
      tester.getSemantics(hot).flagsCollection.isSelected.toBoolOrNull(),
      isTrue,
    );
    expect(
      find.bySemanticsLabel(ContentText.commentMoreActions),
      findsOneWidget,
    );
    expect(find.text(ContentText.commentPinnedBadge), findsOneWidget);
    expect(find.text(ContentText.commentAuthorLikedBadge), findsOneWidget);
    expect(find.text(ContentText.commentRelationFriendBadge), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

/// mock.yaml dart_func: testCommentReplyPreviewUsesConfig
Future<void> testCommentReplyPreviewUsesConfig(WidgetTester tester) async {
  final firstReply = testCommentItem(
    id: 'reply-config-1',
    postId: 'post-reply-config',
    parentCommentId: 'root-config',
    content: '预览回复',
  );
  final secondReply = testCommentItem(
    id: 'reply-config-2',
    postId: 'post-reply-config',
    parentCommentId: 'root-config',
    content: '展开后回复',
  );
  final root = testCommentItem(
    id: 'root-config',
    postId: 'post-reply-config',
    content: '一级评论',
    replyCount: 2,
    replyPreview: <CommentListItem>[firstReply],
    replyNextCursor: '1',
  );
  final comments = InMemoryContentCommentFacet(
    items: <CommentListItem>[root, firstReply, secondReply],
  );

  await tester.pumpWidget(
    _app(comments, const CommentThreadView(postId: 'post-reply-config')),
  );
  await tester.pumpAndSettle();

  expect(find.textContaining('预览回复', findRichText: true), findsOneWidget);
  expect(find.textContaining('展开后回复', findRichText: true), findsNothing);
  expect(find.textContaining('展开'), findsOneWidget);

  await tester.tap(find.textContaining('展开'));
  await tester.pumpAndSettle();

  expect(find.textContaining('展开后回复', findRichText: true), findsOneWidget);
  expect(comments.queryCalls, greaterThan(1));
}

/// mock.yaml dart_func: testCommentReactionThreeStateWidget
Future<void> testCommentReactionThreeStateWidget(WidgetTester tester) async {
  final comments = InMemoryContentCommentFacet(
    items: <CommentListItem>[
      testCommentItem(
        id: 'comment-reaction-three-state',
        postId: 'post-reaction-three-state',
        content: '已赞评论',
        likeCount: 3,
        dislikeCount: 1,
        viewerReaction: CommentReactionType.like,
      ),
    ],
  );

  await tester.pumpWidget(
    _app(
      comments,
      const CommentThreadView(postId: 'post-reaction-three-state'),
      authenticated: true,
    ),
  );
  await tester.pumpAndSettle();

  expect(find.byIcon(CupertinoIcons.heart_fill), findsOneWidget);
  expect(find.byIcon(CupertinoIcons.hand_thumbsdown_fill), findsNothing);

  await tester.tap(find.byIcon(CupertinoIcons.hand_thumbsdown));
  await tester.pumpAndSettle();

  expect(comments.reactionCalls, 1);
  expect(comments.lastReactionCommand?.reaction, CommentReactionType.dislike);
  expect(comments.items.single.viewerReaction, CommentReactionType.dislike);
  expect(comments.items.single.likeCount, 2);
  expect(comments.items.single.dislikeCount, 2);
  expect(find.byIcon(CupertinoIcons.heart_fill), findsNothing);
  expect(find.byIcon(CupertinoIcons.hand_thumbsdown_fill), findsOneWidget);
}

Widget _app(
  ContentCommentFacet comments,
  Widget child, {
  bool authenticated = false,
}) {
  return ProviderScope(
    overrides: [
      workBrowserContentCommentFacetProvider.overrideWithValue(comments),
      profileCommentsContentCommentFacetProvider.overrideWithValue(comments),
      commentRemoteConfigProvider.overrideWithValue(
        const CommentRemoteConfig(
          replyPreviewCount: 1,
          replyFirstExpandPageSize: 5,
          replyExpandPageSize: 10,
        ),
      ),
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

class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() {
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'test-token',
      refreshToken: 'test-refresh',
      ownerId: 'test-owner',
      activePersonaId: 'test-persona',
      accountState: 'active',
      identityOrigin: 'test',
      installId: 'test-install',
    );
  }
}
