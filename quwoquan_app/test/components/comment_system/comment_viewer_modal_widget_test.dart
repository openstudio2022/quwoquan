import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/runtime/models/comment_remote_config.dart';
import 'package:quwoquan_app/components/comment_system/immersive_comment_split_sheet.dart';
import 'package:quwoquan_app/components/comment_system/comment_input_overlay.dart';
import 'package:quwoquan_app/components/comment_system/comment_toolbar.dart';
import 'package:quwoquan_app/components/comment_system/comment_thread_view.dart';
import 'package:quwoquan_app/components/comment_system/comment_detail_surface.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer_modal.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/trackers/comment_observability.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/providers/comment_provider.dart';

void main() {
  late Directory tempDir;

  setUpAll(() async {
    tempDir = await Directory.systemTemp.createTemp('comment_viewer_test_');
    Hive.init(tempDir.path);
    final box = await Hive.openBox<String>('client_interaction_state');
    await box.clear();
    await box.close();
  });

  setUp(() async {
    if (Hive.isBoxOpen('client_interaction_state')) {
      await Hive.box<String>('client_interaction_state').clear();
      return;
    }
    final box = await Hive.openBox<String>('client_interaction_state');
    await box.clear();
    await box.close();
  });

  tearDownAll(() async {
    await Hive.close();
    if (await tempDir.exists()) {
      await tempDir.delete(recursive: true);
    }
  });

  testWidgets('评论面板以非全屏底部面板呈现并贴底工具栏', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: MediaQuery(
            data: const MediaQueryData(
              viewPadding: EdgeInsets.only(bottom: 34),
              padding: EdgeInsets.only(bottom: 34),
            ),
            child: Scaffold(
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
    expect(
      tester.getBottomLeft(find.byKey(TestKeys.commentToolbar)).dy,
      closeTo(tester.getBottomLeft(panel).dy, 0.1),
    );
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
    'testCommentReplyPreviewUsesConfig: reply preview 与展开配置生效',
    testCommentReplyPreviewUsesConfig,
  );

  testWidgets(
    'testCommentReactionThreeStateWidget: like / dislike / none 三态互斥',
    testCommentReactionThreeStateWidget,
  );

  testWidgets(
    'testCommentThreadHighlightDeeplink: 深链命中一级评论后高亮该项',
    testCommentThreadHighlightDeeplink,
  );

  testWidgets(
    'testCommentDisplayFieldBadges: 置顶/作者赞过/IP 属地展示字段渲染',
    testCommentDisplayFieldBadges,
  );

  testWidgets(
    'testCommentPinByAuthorWidget: 作者点按置顶图标后该评论置顶且排到最前、埋点发射',
    testCommentPinByAuthorWidget,
  );

  testWidgets(
    'testCommentObservabilityEmissions: 曝光/深链命中/互动/延迟埋点真实发射',
    testCommentObservabilityEmissions,
  );

  testWidgets(
    'testCommentTotalCountContractDrivesHeader: 标题使用 CommentPage.totalCount 而非已加载一级条数',
    testCommentTotalCountContractDrivesHeader,
  );

  test('评论真实 totalCount 同步外层 post interaction 计数', () async {
    final repo = MockContentRepository();
    const postId = 'comment_total_sync_post';
    repo.commentsStub = <CommentDto>[
      _comment(
        id: 'parent_1',
        postId: postId,
        authorId: 'user_parent',
        content: '一级评论',
        createdAt: DateTime.utc(2026, 1, 1),
      ),
      _comment(
        id: 'reply_1',
        postId: postId,
        authorId: 'user_reply',
        content: '二级回复',
        parentCommentId: 'parent_1',
        replyToCommentId: 'parent_1',
        createdAt: DateTime.utc(2026, 1, 2),
      ),
    ];
    final container = ProviderContainer(
      overrides: [
        contentRepositoryProvider.overrideWithValue(repo),
        analyticsProvider.overrideWithValue(AnalyticsService.forTesting()),
      ],
    );
    addTearDown(container.dispose);

    container
        .read(postInteractionStateProvider.notifier)
        .setCommentCount(postId, 19);

    final notifier = container.read(commentProviderFamily(postId).notifier);
    await notifier.loadComments();
    expect(container.read(commentProviderFamily(postId)).totalCount, 2);
    expect(
      container.read(postInteractionStateProvider).commentCountFor(postId),
      2,
    );

    final added = await notifier.addComment('新增评论');
    expect(added, isNotNull);
    expect(container.read(commentProviderFamily(postId)).totalCount, 3);
    expect(
      container.read(postInteractionStateProvider).commentCountFor(postId),
      3,
    );

    await notifier.deleteComment(added!.id);
    expect(container.read(commentProviderFamily(postId)).totalCount, 2);
    expect(
      container.read(postInteractionStateProvider).commentCountFor(postId),
      2,
    );
  });

  test('评论已有列表时在线加载失败保留旧评论并记录 retained 兜底', () async {
    const postId = 'comment_retained_failure_post';
    final repo = _SecondLoadFailsContentRepository()
      ..commentsStub = <CommentDto>[
        _comment(
          id: 'retained_comment_1',
          postId: postId,
          authorId: 'user_parent',
          content: '先看到的评论',
          createdAt: DateTime.utc(2026, 1, 1),
        ),
      ];
    final analytics = _RecordingAnalyticsService();
    final container = ProviderContainer(
      overrides: [
        contentRepositoryProvider.overrideWithValue(repo),
        analyticsProvider.overrideWithValue(analytics),
      ],
    );
    addTearDown(container.dispose);

    final notifier = container.read(commentProviderFamily(postId).notifier);
    await notifier.loadComments();
    expect(
      container.read(commentProviderFamily(postId)).comments,
      hasLength(1),
    );

    await notifier.loadComments();

    final state = container.read(commentProviderFamily(postId));
    expect(state.status, CommentListStatus.idle);
    expect(state.comments.single.id, 'retained_comment_1');
    expect(state.rawError, isNotNull);
    expect(
      analytics.events.where((event) {
        final properties = event.properties;
        return event.eventName == 'page_lifecycle_state' &&
            properties['pageName'] == 'comment_thread' &&
            properties['route'] == '/posts/$postId/comments' &&
            properties['phase'] == 'cacheFallback' &&
            properties['source'] == 'retained' &&
            properties['copyKey'] == 'refreshFailedRetained' &&
            properties['hasCache'] == true &&
            properties['itemCount'] == 1;
      }),
      isNotEmpty,
    );
  });

  testWidgets(
    'testCommentThreadCoreFixtureCoversReplyMagnitudes: 真实 mock 入口覆盖 0/1/5/10/50/100+ 且总数一致',
    testCommentThreadCoreFixtureCoversReplyMagnitudes,
  );

  testWidgets(
    'testCommentReactionColumnsAlignAcrossLevels: 一级/二级赞踩固定列对齐且 compact 计数不漂移',
    testCommentReactionColumnsAlignAcrossLevels,
  );

  testWidgets(
    'testOwnCommentUsesDeleteSlotAcrossLevels: 自己的一级/二级评论显示 like+delete 且删除不再落在 footer',
    testOwnCommentUsesDeleteSlotAcrossLevels,
  );

  testWidgets(
    'testCommentToolbarFidelityMetrics: 底栏低胶囊、描边、固定动作列符合高保约束',
    testCommentToolbarFidelityMetrics,
  );

  testWidgets(
    '二级评论深链会自动展开父评论并高亮目标回复',
    testCommentReplyDeeplinkExpandsAndHighlights,
  );

  testWidgets(
    '深链一级目标在第 2 页之后自动翻页定位并高亮',
    testCommentDeeplinkPagesToTargetOnLaterPage,
  );

  testWidgets(
    '深链二级回复父评论未加载时先翻页加载父再展开定位',
    testCommentReplyDeeplinkLoadsParentThenPositions,
  );

  testWidgets(
    '深链目标翻尽仍不存在时明确反馈并发 miss 埋点',
    testCommentDeeplinkMissReportsFeedback,
  );

  testWidgets('点击他人一级或二级评论正文进入对应回复态', testCommentTapReplyTargetContract);

  testWidgets('长评论三行内联全文折叠且多图只展示第一张', testInlineFoldAndSingleImageDisplay);
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

/// 强制小分页的评论仓储：无论调用方传入 limit 多少，一律按 [pageSize] 返回，
/// 用于稳定复现「深链目标落在第 2 页之后需自动翻页」的场景。
class _PagedCommentRepository extends MockContentRepository {
  _PagedCommentRepository({required this.pageSize});

  final int pageSize;

  @override
  Future<CommentPage> listComments({
    required String postId,
    String? cursor,
    String sort = 'recommended',
    int limit = CloudApiDefaults.pageLimit,
  }) {
    return super.listComments(
      postId: postId,
      cursor: cursor,
      sort: sort,
      limit: pageSize,
    );
  }
}

class _SecondLoadFailsContentRepository extends MockContentRepository {
  int _listCommentsCallCount = 0;

  @override
  Future<CommentPage> listComments({
    required String postId,
    String? cursor,
    String sort = 'recommended',
    int limit = CloudApiDefaults.pageLimit,
  }) {
    _listCommentsCallCount += 1;
    if (_listCommentsCallCount >= 2) {
      throw StateError('comment list refresh failed');
    }
    return super.listComments(
      postId: postId,
      cursor: cursor,
      sort: sort,
      limit: limit,
    );
  }
}

class _RecordingAnalyticsService extends AnalyticsService {
  _RecordingAnalyticsService() : super.forTesting();

  final List<AnalyticsEvent> events = <AnalyticsEvent>[];

  @override
  Future<void> trackEvent(AnalyticsEvent event) async {
    events.add(event);
  }
}

Widget _threadTestApp({
  required MockContentRepository repo,
  required Widget child,
  CommentRemoteConfig commentConfig = const CommentRemoteConfig(),
  bool authenticated = false,
  CommentObservability? observability,
}) {
  return ProviderScope(
    overrides: [
      contentRepositoryProvider.overrideWithValue(repo),
      analyticsProvider.overrideWithValue(AnalyticsService.forTesting()),
      commentRemoteConfigProvider.overrideWithValue(commentConfig),
      if (observability != null)
        commentObservabilityProvider.overrideWithValue(observability),
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
  bool authorLiked = false,
  bool isPinned = false,
  DateTime? pinnedAt,
  String? ipLocation,
  bool canReply = true,
  bool canDelete = false,
  bool canReport = false,
  bool canPin = false,
  String? replyToDisplayName,
  List<CommentAttachmentDto> attachments = const <CommentAttachmentDto>[],
  double? recommendedScore,
  DateTime? createdAt,
}) {
  return CommentDto(
    id: id,
    postId: postId,
    authorId: authorId,
    displayName: displayName,
    avatarUrl: avatarUrl,
    ipLocation: ipLocation,
    content: content,
    recommendedScore: recommendedScore,
    replyToCommentId: replyToCommentId,
    replyToDisplayName: replyToDisplayName,
    parentCommentId: parentCommentId,
    attachments: attachments,
    replyCount: replyCount,
    replyPreview: replyPreview,
    replyNextCursor: replyNextCursor,
    likeCount: likeCount,
    dislikeCount: dislikeCount,
    viewerReaction: viewerReaction,
    authorLiked: authorLiked,
    isPinned: isPinned,
    pinnedAt: pinnedAt,
    canReply: canReply,
    canDelete: canDelete,
    canReport: canReport,
    canPin: canPin,
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
        replyFirstExpandPageSize: 2,
        replyExpandPageSize: 3,
      ),
      child: const CommentThreadView(postId: postId, shrinkWrap: true),
    ),
  );
  await tester.pumpAndSettle();

  final container = ProviderScope.containerOf(
    tester.element(find.byType(CupertinoPageScaffold)),
  );
  final state = container.read(commentProviderFamily(postId));
  expect(state.replyPreviewCount, equals(1));
  expect(state.replyFirstExpandPageSize, equals(2));
  expect(state.replyExpandPageSize, equals(3));
  expect(find.text('一级评论'), findsOneWidget);
  // 回复改为引用昵称 TextSpan 弱化的富文本，合并明文仍为「昵称：正文」。
  expect(find.text('第一位回复者：第一条回复', findRichText: true), findsOneWidget);
  expect(find.text('第二位回复者：第二条回复', findRichText: true), findsNothing);
  expect(find.text('展开 1 条回复'), findsOneWidget);

  // 首次展开使用 replyFirstExpandPageSize（首屏 5 的语义，本例配置为 2）。
  await tester.tap(find.byKey(TestKeys.commentReplyExpand));
  await tester.pumpAndSettle();

  expect(repo.lastReplyLimit, equals(2));
  expect(find.text('第二位回复者：第二条回复', findRichText: true), findsOneWidget);
  expect(find.text('展开 1 条回复'), findsNothing);
  // 服务端已无更多回复且展示数 > 预览数：出现「收起」。
  expect(find.byKey(TestKeys.commentReplyCollapse), findsOneWidget);

  // 收起后回到预览态：第二条回复隐藏，重新出现「展开 1 条回复」。
  await tester.tap(find.byKey(TestKeys.commentReplyCollapse));
  await tester.pumpAndSettle();
  expect(find.text('第二位回复者：第二条回复', findRichText: true), findsNothing);
  expect(find.byKey(TestKeys.commentReplyExpand), findsOneWidget);
}

Future<void> testCommentThreadHighlightDeeplink(WidgetTester tester) async {
  final repo = MockContentRepository();
  const postId = 'comment_highlight_post';
  repo.commentsStub = <CommentDto>[
    _comment(
      id: 'comment_a',
      postId: postId,
      authorId: 'user_a',
      displayName: '甲',
      content: '第一条评论',
      createdAt: DateTime.utc(2026, 1, 1),
    ),
    _comment(
      id: 'comment_target',
      postId: postId,
      authorId: 'user_b',
      displayName: '乙',
      content: '被深链定位的评论',
      createdAt: DateTime.utc(2026, 1, 2),
    ),
    _comment(
      id: 'comment_c',
      postId: postId,
      authorId: 'user_c',
      displayName: '丙',
      content: '第三条评论',
      createdAt: DateTime.utc(2026, 1, 3),
    ),
  ];

  await tester.pumpWidget(
    _threadTestApp(
      repo: repo,
      child: const CommentThreadView(
        postId: postId,
        shrinkWrap: true,
        highlightCommentId: 'comment_target',
      ),
    ),
  );
  await tester.pumpAndSettle();

  expect(find.text('被深链定位的评论'), findsOneWidget);
  // 命中目标一级评论：高亮容器出现。
  expect(find.byKey(TestKeys.commentHighlightedItem), findsOneWidget);

  // 高亮在 2.4s 后淡出，避免长期占用视觉。
  await tester.pump(const Duration(milliseconds: 2600));
  await tester.pumpAndSettle();
  expect(find.byKey(TestKeys.commentHighlightedItem), findsNothing);
}

Future<void> testCommentDisplayFieldBadges(WidgetTester tester) async {
  final repo = MockContentRepository();
  const postId = 'comment_display_post';
  repo.commentsStub = <CommentDto>[
    _comment(
      id: 'comment_pinned',
      postId: postId,
      authorId: 'user_pin',
      displayName: '被置顶者',
      content: '置顶并被作者赞过的评论',
      isPinned: true,
      pinnedAt: DateTime.utc(2026, 1, 9),
      authorLiked: true,
      ipLocation: '浙江',
      createdAt: DateTime.utc(2026, 1, 1),
    ),
    _comment(
      id: 'comment_plain',
      postId: postId,
      authorId: 'user_plain',
      displayName: '普通评论者',
      content: '普通评论',
      ipLocation: '广东',
      createdAt: DateTime.utc(2026, 1, 2),
    ),
  ];

  await tester.pumpWidget(
    _threadTestApp(
      repo: repo,
      child: const CommentThreadView(postId: postId, shrinkWrap: true),
    ),
  );
  await tester.pumpAndSettle();

  // 置顶徽标与作者赞过徽标只出现在对应评论上。
  expect(find.text(UITextConstants.commentPinnedBadge), findsOneWidget);
  expect(find.text(UITextConstants.commentAuthorLikedBadge), findsOneWidget);
  // IP 属地以「IP 属地 浙江/广东」次要文本渲染（每条评论一处）。
  expect(find.textContaining('浙江'), findsOneWidget);
  expect(find.textContaining('广东'), findsOneWidget);
}

Future<void> testCommentPinByAuthorWidget(WidgetTester tester) async {
  final repo = MockContentRepository();
  const postId = 'comment_pin_post';
  // 第二条评论 canPin=true（视角为内容作者）。
  repo.commentsStub = <CommentDto>[
    _comment(
      id: 'comment_first',
      postId: postId,
      authorId: 'fan_1',
      displayName: '甲',
      content: '第一条评论',
      createdAt: DateTime.utc(2026, 1, 1),
    ),
    _comment(
      id: 'comment_pinnable',
      postId: postId,
      authorId: 'fan_2',
      displayName: '乙',
      content: '可被作者置顶的评论',
      canPin: true,
      createdAt: DateTime.utc(2026, 1, 2),
    ),
  ];
  final recorder = _RecordingCommentObservability();

  await tester.pumpWidget(
    _threadTestApp(
      repo: repo,
      authenticated: true,
      observability: recorder,
      child: const CommentThreadView(postId: postId, shrinkWrap: true),
    ),
  );
  await tester.pumpAndSettle();

  // 仅 canPin=true 的评论暴露置顶图标（未置顶态为空心 pin）。
  expect(find.byIcon(CupertinoIcons.pin), findsOneWidget);
  expect(find.byIcon(CupertinoIcons.pin_fill), findsNothing);

  await tester.tap(find.byIcon(CupertinoIcons.pin));
  await tester.pumpAndSettle();

  // Mock 仓储真实写入置顶并将其排到最前（与云侧排序一致）。
  final pinned = repo.commentsStub.firstWhere(
    (c) => c.id == 'comment_pinnable',
  );
  expect(pinned.isPinned, isTrue);
  expect(pinned.pinnedAt, isNotNull);
  expect(repo.commentsStub.first.id, equals('comment_pinnable'));

  // Provider 状态：置顶项排首位且渲染置顶徽标与实心 pin。
  final container = ProviderScope.containerOf(
    tester.element(find.byType(CupertinoPageScaffold)),
  );
  expect(
    container.read(commentProviderFamily(postId)).comments.first.id,
    equals('comment_pinnable'),
  );
  expect(find.text(UITextConstants.commentPinnedBadge), findsOneWidget);
  expect(find.byIcon(CupertinoIcons.pin_fill), findsOneWidget);

  // 置顶埋点与延迟指标真实发射。
  final pinAction = recorder.firstAction(CommentEventNames.pinChanged);
  expect(pinAction, isNotNull);
  expect(pinAction!.properties['reaction'], equals('pin'));
  expect(pinAction.properties['commentId'], equals('comment_pinnable'));
  expect(recorder.latencyMetrics, contains(CommentMetricNames.pinConfirmMs));

  // 排空成功提示 toast 的 3s 定时器，避免测试结束残留 pending timer。
  await tester.pump(const Duration(seconds: 3));
  await tester.pumpAndSettle();
}

Future<void> testCommentObservabilityEmissions(WidgetTester tester) async {
  final repo = MockContentRepository();
  const postId = 'comment_obs_post';
  repo.commentsStub = <CommentDto>[
    _comment(
      id: 'comment_target',
      postId: postId,
      authorId: 'user_b',
      displayName: '乙',
      content: '被深链定位的评论',
      createdAt: DateTime.utc(2026, 1, 2),
    ),
  ];
  final recorder = _RecordingCommentObservability();

  await tester.pumpWidget(
    _threadTestApp(
      repo: repo,
      authenticated: true,
      observability: recorder,
      child: const CommentThreadView(
        postId: postId,
        shrinkWrap: true,
        highlightCommentId: 'comment_target',
      ),
    ),
  );
  await tester.pumpAndSettle();

  // 曝光埋点真实发射。
  expect(recorder.hasAction(CommentEventNames.surfaceExpose), isTrue);
  // 列表加载延迟指标真实发射。
  expect(recorder.latencyMetrics, contains(CommentMetricNames.listLoadMs));
  // 深链命中落地埋点：entrySource=deeplink-highlight, result=hit, 携带 commentId。
  final deeplink = recorder.firstAction(CommentEventNames.deeplinkOpened);
  expect(deeplink, isNotNull);
  expect(deeplink!.properties['entrySource'], equals('deeplink-highlight'));
  expect(deeplink.properties['result'], equals('hit'));
  expect(deeplink.properties['commentId'], equals('comment_target'));

  // 互动埋点：点赞触发 reactionChanged（携带 reaction=like）。
  await tester.tap(find.byIcon(CupertinoIcons.heart));
  await tester.pumpAndSettle();
  final reaction = recorder.firstAction(CommentEventNames.reactionChanged);
  expect(reaction, isNotNull);
  expect(reaction!.properties['reaction'], equals('like'));
  expect(
    recorder.latencyMetrics,
    contains(CommentMetricNames.reactionConfirmMs),
  );

  // 排空高亮淡出定时器，避免测试结束残留 pending timer。
  await tester.pump(const Duration(milliseconds: 2600));
  await tester.pumpAndSettle();
}

Future<void> testCommentTotalCountContractDrivesHeader(
  WidgetTester tester,
) async {
  final repo = MockContentRepository();
  const postId = 'comment_total_contract_post';
  repo.commentsStub = <CommentDto>[
    _comment(
      id: 'parent_1',
      postId: postId,
      authorId: 'user_parent',
      displayName: '一级评论者',
      content: '一级评论',
      createdAt: DateTime.utc(2026, 1, 1),
    ),
    _comment(
      id: 'reply_1',
      postId: postId,
      authorId: 'user_reply',
      displayName: '二级回复者',
      content: '二级回复',
      parentCommentId: 'parent_1',
      replyToCommentId: 'parent_1',
      createdAt: DateTime.utc(2026, 1, 2),
    ),
  ];

  await tester.pumpWidget(
    _threadTestApp(
      repo: repo,
      child: const CommentDetailSurface(
        postId: postId,
        mode: CommentDetailSurfaceMode.cardModal,
      ),
    ),
  );
  await tester.pumpAndSettle();

  final container = ProviderScope.containerOf(
    tester.element(find.byType(CupertinoPageScaffold)),
  );
  final state = container.read(commentProviderFamily(postId));
  expect(state.comments, hasLength(1));
  expect(state.totalCount, equals(2));
  // 标题计数由 CommentDetailHeader 消费 CommentPage.totalCount（2）渲染，
  // 而非已加载一级条数（1）。
  expect(
    find.text(
      UITextConstants.commentCountTitleTemplate.replaceFirst('%s', '2'),
    ),
    findsOneWidget,
  );
}

Future<void> testCommentThreadCoreFixtureCoversReplyMagnitudes(
  WidgetTester tester,
) async {
  final repo = MockContentRepository();
  const postIds = <String>['fixture_photo_001', 'alpha_moment_grid_1'];

  for (final postId in postIds) {
    final page = await repo.listComments(postId: postId, limit: 100);
    final byId = {for (final comment in page.items) comment.id: comment};
    expect(page.totalCount, equals(182), reason: postId);
    expect(byId['fixture_comment_thread_empty']?.replyCount, equals(0));
    expect(byId['fixture_comment_parent_001']?.replyCount, equals(1));
    expect(byId['fixture_comment_thread_five']?.replyCount, equals(5));
    expect(byId['fixture_comment_thread_ten']?.replyCount, equals(10));
    expect(byId['fixture_comment_thread_fifty']?.replyCount, equals(50));
    expect(byId['fixture_comment_thread_hundred']?.replyCount, equals(110));
  }

  final feed = await repo.listDiscoveryFeed(category: 'all', limit: 0);
  final feedById = {for (final post in feed) post.id: post};
  expect(feedById['fixture_photo_001']?.commentCount, equals(182));
  final showcaseDetail = await repo.getPost(postId: 'alpha_moment_grid_1');
  expect(showcaseDetail.post.commentCount, equals(182));

  await tester.pumpWidget(
    _threadTestApp(
      repo: repo,
      child: const SingleChildScrollView(
        child: CommentThreadView(
          postId: 'alpha_moment_grid_1',
          shrinkWrap: true,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();

  final container = ProviderScope.containerOf(
    tester.element(find.byType(CupertinoPageScaffold)),
  );
  final state = container.read(commentProviderFamily('alpha_moment_grid_1'));
  final byId = {for (final comment in state.comments) comment.id: comment};

  expect(state.totalCount, equals(182));
  expect(state.comments, hasLength(6));
  expect(byId['fixture_comment_thread_empty']?.replyCount, equals(0));
  expect(byId['fixture_comment_parent_001']?.replyCount, equals(1));
  expect(byId['fixture_comment_thread_five']?.replyCount, equals(5));
  expect(byId['fixture_comment_thread_ten']?.replyCount, equals(10));
  expect(byId['fixture_comment_thread_fifty']?.replyCount, equals(50));
  expect(byId['fixture_comment_thread_hundred']?.replyCount, equals(110));
}

Future<void> testCommentReactionColumnsAlignAcrossLevels(
  WidgetTester tester,
) async {
  final repo = MockContentRepository();
  const postId = 'comment_reaction_align_post';
  final reply = _comment(
    id: 'reply_align',
    postId: postId,
    authorId: 'reply_author',
    displayName: '回复者',
    content: '二级回复',
    parentCommentId: 'parent_align',
    replyToCommentId: 'parent_align',
    likeCount: 10000,
    dislikeCount: 9265,
    createdAt: DateTime.utc(2026, 1, 2),
  );
  repo.commentsStub = <CommentDto>[
    _comment(
      id: 'parent_align',
      postId: postId,
      authorId: 'parent_author',
      displayName: '一级甲',
      content: '一级评论甲',
      replyCount: 1,
      replyPreview: <CommentDto>[reply],
      likeCount: 2,
      dislikeCount: 11,
      createdAt: DateTime.utc(2026, 1, 1),
    ),
    reply,
    _comment(
      id: 'parent_align_b',
      postId: postId,
      authorId: 'parent_author_b',
      displayName: '一级乙',
      content: '一级评论乙',
      likeCount: 199,
      dislikeCount: 9265,
      createdAt: DateTime.utc(2026, 1, 3),
    ),
  ];

  await tester.pumpWidget(
    _threadTestApp(
      repo: repo,
      child: const CommentThreadView(postId: postId, shrinkWrap: true),
    ),
  );
  await tester.pumpAndSettle();

  final heartCenters = tester
      .widgetList<Icon>(find.byIcon(CupertinoIcons.heart))
      .map((icon) => tester.getCenter(find.byWidget(icon)).dx)
      .toList(growable: false);
  final dislikeCenters = tester
      .widgetList<Icon>(find.byIcon(CupertinoIcons.hand_thumbsdown))
      .map((icon) => tester.getCenter(find.byWidget(icon)).dx)
      .toList(growable: false);
  final dislikeRightEdges = tester
      .widgetList<Icon>(find.byIcon(CupertinoIcons.hand_thumbsdown))
      .map((icon) => tester.getTopRight(find.byWidget(icon)).dx)
      .toList(growable: false);

  expect(heartCenters.length, greaterThanOrEqualTo(3));
  expect(dislikeCenters.length, greaterThanOrEqualTo(3));
  expect(_maxDelta(heartCenters), lessThanOrEqualTo(1));
  expect(_maxDelta(dislikeCenters), lessThanOrEqualTo(1));
  expect(_maxDelta(dislikeRightEdges), lessThanOrEqualTo(1));
  for (var i = 0; i < heartCenters.length && i < dislikeCenters.length; i++) {
    expect(
      dislikeCenters[i] - heartCenters[i],
      lessThanOrEqualTo(AppSpacing.commentReactionColumnWidth + AppSpacing.xs),
    );
  }
  expect(find.text('1万'), findsOneWidget);
  expect(find.text('9.3k'), findsAtLeastNWidgets(1));
}

Future<void> testOwnCommentUsesDeleteSlotAcrossLevels(
  WidgetTester tester,
) async {
  final repo = MockContentRepository();
  const postId = 'comment_delete_slot_post';
  final ownReply = _comment(
    id: 'reply_mine',
    postId: postId,
    authorId: 'me',
    displayName: '我自己',
    content: '我的二级回复',
    parentCommentId: 'parent_mine',
    replyToCommentId: 'parent_mine',
    likeCount: 7,
    canDelete: true,
    createdAt: DateTime.utc(2026, 1, 2),
  );
  repo.commentsStub = <CommentDto>[
    _comment(
      id: 'parent_mine',
      postId: postId,
      authorId: 'me',
      displayName: '我自己',
      content: '我的一级评论',
      replyCount: 1,
      replyPreview: <CommentDto>[ownReply],
      likeCount: 12,
      canDelete: true,
      createdAt: DateTime.utc(2026, 1, 1),
    ),
    ownReply,
    _comment(
      id: 'parent_other',
      postId: postId,
      authorId: 'other',
      displayName: '别人',
      content: '别人的评论',
      dislikeCount: 3,
      createdAt: DateTime.utc(2026, 1, 3),
    ),
  ];

  await tester.pumpWidget(
    _threadTestApp(
      repo: repo,
      authenticated: true,
      child: const CommentThreadView(postId: postId, shrinkWrap: true),
    ),
  );
  await tester.pumpAndSettle();

  expect(find.byIcon(CupertinoIcons.trash), findsNWidgets(2));
  expect(find.byIcon(CupertinoIcons.hand_thumbsdown), findsOneWidget);

  final deleteCenters = tester
      .widgetList<Icon>(find.byIcon(CupertinoIcons.trash))
      .map((icon) => tester.getCenter(find.byWidget(icon)).dx)
      .toList(growable: false);
  expect(deleteCenters.length, equals(2));
  expect(_maxDelta(deleteCenters), lessThanOrEqualTo(1));
}

Future<void> testCommentToolbarFidelityMetrics(WidgetTester tester) async {
  await tester.pumpWidget(
    const CupertinoApp(
      home: CupertinoPageScaffold(
        child: Align(
          alignment: Alignment.bottomCenter,
          child: CommentToolbar(likeCount: 10000, shareCount: 9265),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();

  expect(
    tester.getSize(find.byKey(TestKeys.commentInputBar)).height,
    equals(AppSpacing.commentToolbarInputHeight),
  );
  expect(
    tester.getSize(find.byKey(TestKeys.likeButton)),
    equals(
      const Size(
        AppSpacing.commentToolbarActionColumnWidth,
        AppSpacing.commentToolbarActionHitSize,
      ),
    ),
  );
  final capsule = tester.widget<Container>(
    find.byKey(TestKeys.commentInputCapsule),
  );
  final decoration = capsule.decoration as BoxDecoration;
  expect(
    decoration.borderRadius,
    equals(BorderRadius.circular(AppSpacing.commentToolbarInputRadius)),
  );
  expect(decoration.border, isNotNull);
  expect(
    tester.getSize(find.byKey(TestKeys.commentToolbar)).height,
    lessThanOrEqualTo(45),
  );

  await tester.pumpWidget(
    const CupertinoApp(
      home: MediaQuery(
        data: MediaQueryData(
          viewPadding: EdgeInsets.only(bottom: 24),
          padding: EdgeInsets.only(bottom: 24),
        ),
        child: CupertinoPageScaffold(
          child: ColoredBox(
            color: AppColors.warning,
            child: Align(
              alignment: Alignment.bottomCenter,
              child: CommentToolbar(likeCount: 1, shareCount: 1),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  final toolbar = find.byKey(TestKeys.commentToolbar);
  final capsuleFinder = find.byKey(TestKeys.commentInputCapsule);
  expect(tester.getBottomLeft(toolbar).dy, closeTo(600, 0.1));
  expect(
    tester.getBottomLeft(capsuleFinder).dy,
    lessThan(tester.getBottomLeft(toolbar).dy),
  );
  expect(
    tester.getSize(toolbar).height,
    closeTo(
      AppSpacing.commentToolbarInputHeight +
          AppSpacing.commentToolbarVerticalPadding * 2 +
          24,
      AppSpacing.hairline,
    ),
  );
}

double _maxDelta(List<double> values) {
  final minValue = values.reduce((a, b) => a < b ? a : b);
  final maxValue = values.reduce((a, b) => a > b ? a : b);
  return maxValue - minValue;
}

Future<void> testCommentReplyDeeplinkExpandsAndHighlights(
  WidgetTester tester,
) async {
  final repo = MockContentRepository();
  const postId = 'comment_reply_deeplink_post';
  final firstReply = _comment(
    id: 'reply_preview',
    postId: postId,
    authorId: 'reply_author_a',
    displayName: '二级甲',
    content: '预览回复',
    parentCommentId: 'parent_deeplink',
    replyToCommentId: 'parent_deeplink',
    createdAt: DateTime.utc(2026, 1, 2),
  );
  final targetReply = _comment(
    id: 'reply_target',
    postId: postId,
    authorId: 'reply_author_b',
    displayName: '二级乙',
    content: '需要定位的二级回复',
    parentCommentId: 'parent_deeplink',
    replyToCommentId: 'reply_preview',
    replyToDisplayName: '二级甲',
    createdAt: DateTime.utc(2026, 1, 3),
  );
  repo.commentsStub = <CommentDto>[
    _comment(
      id: 'parent_deeplink',
      postId: postId,
      authorId: 'parent_author',
      displayName: '一级作者',
      content: '一级评论',
      replyCount: 2,
      createdAt: DateTime.utc(2026, 1, 1),
    ),
    firstReply,
    targetReply,
  ];

  await tester.pumpWidget(
    _threadTestApp(
      repo: repo,
      child: const SingleChildScrollView(
        child: CommentThreadView(
          postId: postId,
          shrinkWrap: true,
          highlightCommentId: 'parent_deeplink',
          highlightReplyId: 'reply_target',
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();

  expect(
    find.text('二级乙：回复 @二级甲 需要定位的二级回复', findRichText: true),
    findsOneWidget,
  );
  expect(find.byKey(TestKeys.commentHighlightedReply), findsOneWidget);

  await tester.pump(const Duration(milliseconds: 2600));
  await tester.pumpAndSettle();
  expect(find.byKey(TestKeys.commentHighlightedReply), findsNothing);
}

Future<void> testCommentDeeplinkPagesToTargetOnLaterPage(
  WidgetTester tester,
) async {
  // pageSize=2：目标评论排在第 2 页，需自动翻页才能命中。
  final repo = _PagedCommentRepository(pageSize: 2);
  const postId = 'comment_deeplink_paged_post';
  repo.commentsStub = <CommentDto>[
    _comment(
      id: 'paged_c1',
      postId: postId,
      authorId: 'u1',
      content: '第一条',
      recommendedScore: 400,
      createdAt: DateTime.utc(2026, 1, 1),
    ),
    _comment(
      id: 'paged_c2',
      postId: postId,
      authorId: 'u2',
      content: '第二条',
      recommendedScore: 300,
      createdAt: DateTime.utc(2026, 1, 2),
    ),
    _comment(
      id: 'paged_c3',
      postId: postId,
      authorId: 'u3',
      content: '第三条',
      recommendedScore: 200,
      createdAt: DateTime.utc(2026, 1, 3),
    ),
    _comment(
      id: 'paged_target',
      postId: postId,
      authorId: 'u4',
      content: '第二页的目标评论',
      recommendedScore: 100,
      createdAt: DateTime.utc(2026, 1, 4),
    ),
  ];
  final recorder = _RecordingCommentObservability();

  await tester.pumpWidget(
    _threadTestApp(
      repo: repo,
      observability: recorder,
      child: const SingleChildScrollView(
        child: CommentThreadView(
          postId: postId,
          shrinkWrap: true,
          highlightCommentId: 'paged_target',
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();

  // 自动翻页命中第 2 页目标并高亮。
  expect(find.text('第二页的目标评论'), findsOneWidget);
  expect(find.byKey(TestKeys.commentHighlightedItem), findsOneWidget);
  final hit = recorder.firstAction(CommentEventNames.deeplinkOpened);
  expect(hit, isNotNull);
  expect(hit!.properties['result'], equals('hit'));
  expect(hit.properties['commentId'], equals('paged_target'));

  await tester.pump(const Duration(milliseconds: 2600));
  await tester.pumpAndSettle();
  expect(find.byKey(TestKeys.commentHighlightedItem), findsNothing);
}

Future<void> testCommentReplyDeeplinkLoadsParentThenPositions(
  WidgetTester tester,
) async {
  // pageSize=1：目标回复所属父评论排在第 2 页，需先翻页加载父，再展开回复定位。
  final repo = _PagedCommentRepository(pageSize: 1);
  const postId = 'comment_reply_paged_parent_post';
  final firstReply = _comment(
    id: 'paged_reply_preview',
    postId: postId,
    authorId: 'reply_author_a',
    displayName: '二级甲',
    content: '预览回复',
    parentCommentId: 'paged_parent_target',
    replyToCommentId: 'paged_parent_target',
    createdAt: DateTime.utc(2026, 1, 10),
  );
  final targetReply = _comment(
    id: 'paged_reply_target',
    postId: postId,
    authorId: 'reply_author_b',
    displayName: '二级乙',
    content: '需要定位的二级回复',
    parentCommentId: 'paged_parent_target',
    replyToCommentId: 'paged_reply_preview',
    replyToDisplayName: '二级甲',
    createdAt: DateTime.utc(2026, 1, 11),
  );
  repo.commentsStub = <CommentDto>[
    _comment(
      id: 'paged_parent_other',
      postId: postId,
      authorId: 'other_author',
      displayName: '一级其他',
      content: '第一页的其他一级评论',
      recommendedScore: 500,
      createdAt: DateTime.utc(2026, 1, 1),
    ),
    _comment(
      id: 'paged_parent_target',
      postId: postId,
      authorId: 'parent_author',
      displayName: '一级作者',
      content: '第二页才加载的父评论',
      recommendedScore: 100,
      replyCount: 2,
      createdAt: DateTime.utc(2026, 1, 2),
    ),
    firstReply,
    targetReply,
  ];
  final recorder = _RecordingCommentObservability();

  await tester.pumpWidget(
    _threadTestApp(
      repo: repo,
      observability: recorder,
      child: const SingleChildScrollView(
        child: CommentThreadView(
          postId: postId,
          shrinkWrap: true,
          highlightCommentId: 'paged_parent_target',
          highlightReplyId: 'paged_reply_target',
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();

  // 父评论先被翻页加载，再展开其回复并定位高亮目标二级回复。
  expect(find.text('第二页才加载的父评论'), findsOneWidget);
  expect(
    find.text('二级乙：回复 @二级甲 需要定位的二级回复', findRichText: true),
    findsOneWidget,
  );
  expect(find.byKey(TestKeys.commentHighlightedReply), findsOneWidget);
  final hit = recorder.firstAction(CommentEventNames.deeplinkOpened);
  expect(hit, isNotNull);
  expect(hit!.properties['result'], equals('hit'));
  expect(hit.properties['commentId'], equals('paged_reply_target'));

  await tester.pump(const Duration(milliseconds: 2600));
  await tester.pumpAndSettle();
  expect(find.byKey(TestKeys.commentHighlightedReply), findsNothing);
}

Future<void> testCommentDeeplinkMissReportsFeedback(WidgetTester tester) async {
  final repo = MockContentRepository();
  const postId = 'comment_deeplink_miss_post';
  repo.commentsStub = <CommentDto>[
    _comment(
      id: 'present_comment',
      postId: postId,
      authorId: 'u1',
      content: '存在的评论',
      createdAt: DateTime.utc(2026, 1, 1),
    ),
  ];
  final recorder = _RecordingCommentObservability();

  await tester.pumpWidget(
    _threadTestApp(
      repo: repo,
      observability: recorder,
      child: const SingleChildScrollView(
        child: CommentThreadView(
          postId: postId,
          shrinkWrap: true,
          highlightCommentId: 'missing_comment',
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();

  // 翻尽全部分页仍未命中：明确 toast 反馈 + miss 埋点，绝不静默。
  expect(
    find.text(UITextConstants.commentDeeplinkTargetMissing),
    findsOneWidget,
  );
  final miss = recorder.firstAction(CommentEventNames.deeplinkOpened);
  expect(miss, isNotNull);
  expect(miss!.properties['result'], equals('miss'));
  expect(miss.properties['commentId'], equals('missing_comment'));

  await tester.pump(const Duration(seconds: 3));
  await tester.pumpAndSettle();
}

Future<void> testCommentTapReplyTargetContract(WidgetTester tester) async {
  final repo = MockContentRepository();
  const postId = 'comment_tap_reply_post';
  final nestedReply = _comment(
    id: 'reply_tappable',
    postId: postId,
    authorId: 'reply_author',
    displayName: '二级乙',
    content: '二级回复正文',
    parentCommentId: 'parent_tappable',
    replyToCommentId: 'parent_tappable',
    createdAt: DateTime.utc(2026, 1, 2),
  );
  repo.commentsStub = <CommentDto>[
    _comment(
      id: 'parent_tappable',
      postId: postId,
      authorId: 'parent_author',
      displayName: '路人甲',
      content: '可回复的一级评论',
      replyCount: 1,
      replyPreview: <CommentDto>[nestedReply],
      createdAt: DateTime.utc(2026, 1, 1),
    ),
    nestedReply,
  ];

  await tester.pumpWidget(
    _threadTestApp(
      repo: repo,
      authenticated: true,
      child: Builder(
        builder: (context) => CommentThreadView(
          postId: postId,
          shrinkWrap: true,
          onReplySelected: (comment) => CommentInputOverlay.show(
            context,
            postId: postId,
            replyTo: comment,
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();

  await tester.tap(find.text('可回复的一级评论'));
  await tester.pumpAndSettle();
  expect(find.byKey(TestKeys.commentInputOverlay), findsOneWidget);
  expect(find.textContaining('回复 @路人甲'), findsOneWidget);

  await tester.tap(find.byKey(TestKeys.commentInputOverlayScrim));
  await tester.pumpAndSettle();
  await tester.tap(find.text('二级乙：二级回复正文', findRichText: true));
  await tester.pumpAndSettle();
  expect(find.byKey(TestKeys.commentInputOverlay), findsOneWidget);
  expect(find.textContaining('回复 @二级乙'), findsOneWidget);
}

Future<void> testInlineFoldAndSingleImageDisplay(WidgetTester tester) async {
  final repo = MockContentRepository();
  const postId = 'comment_fold_image_post';
  final longText = List<String>.filled(18, '这是一段很长的评论内容').join('，');
  repo.commentsStub = <CommentDto>[
    _comment(
      id: 'comment_long',
      postId: postId,
      authorId: 'long_author',
      displayName: '长评作者',
      content: longText,
      attachments: const <CommentAttachmentDto>[
        CommentAttachmentDto(
          mediaId: 'comment_image_1',
          type: 'image',
          url: 'media/comment/comment_image_1/v1/comment.png',
        ),
        CommentAttachmentDto(
          mediaId: 'comment_image_2',
          type: 'image',
          url: 'media/comment/comment_image_2/v1/comment.png',
        ),
      ],
      canReply: false,
      createdAt: DateTime.utc(2026, 1, 1),
    ),
  ];

  await tester.pumpWidget(
    _threadTestApp(
      repo: repo,
      child: const SingleChildScrollView(
        child: SizedBox(
          width: 320,
          child: CommentThreadView(postId: postId, shrinkWrap: true),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();

  expect(find.textContaining('全文', findRichText: true), findsOneWidget);
  expect(find.byType(AppCachedNetworkImage), findsOneWidget);
  expect(find.textContaining('收起', findRichText: true), findsNothing);

  final fullText = find.textContaining('全文', findRichText: true);
  await tester.tapAt(tester.getBottomRight(fullText) - const Offset(4, 4));
  await tester.pumpAndSettle();
  expect(find.textContaining('收起', findRichText: true), findsOneWidget);
  expect(find.byType(AppCachedNetworkImage), findsOneWidget);
}

Future<void> testCommentReactionThreeStateWidget(WidgetTester tester) async {
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
      child: const CommentThreadView(postId: postId, shrinkWrap: true),
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

class _RecordedCommentAction {
  _RecordedCommentAction(this.eventName, this.properties);

  final String eventName;
  final Map<String, Object?> properties;
}

/// 记录型评论可观测桩：捕获 UI/Provider 是否真实调用埋点（T2 发射断言）。
class _RecordingCommentObservability extends CommentObservability {
  _RecordingCommentObservability()
    : super(analytics: AnalyticsService.forTesting());

  final List<_RecordedCommentAction> actions = <_RecordedCommentAction>[];
  final List<String> latencyMetrics = <String>[];

  @override
  void trackAction({
    required String eventName,
    required String postId,
    String? commentId,
    String? entrySource,
    String? surfaceMode,
    String? sortMode,
    int? replyDepth,
    int? latencyMs,
    String? failureKind,
    int? attachmentCount,
    int? mentionCount,
    int? itemCount,
    String? reaction,
    String? result,
  }) {
    actions.add(
      _RecordedCommentAction(eventName, <String, Object?>{
        'postId': postId,
        'commentId': ?commentId,
        'entrySource': ?entrySource,
        'surfaceMode': ?surfaceMode,
        'reaction': ?reaction,
        'result': ?result,
      }),
    );
  }

  @override
  void trackLatency({
    required String metricName,
    required String postId,
    required int durationMs,
    required String result,
    String? commentId,
    String? source,
    int? itemCount,
  }) {
    latencyMetrics.add(metricName);
  }

  bool hasAction(String eventName) =>
      actions.any((a) => a.eventName == eventName);

  _RecordedCommentAction? firstAction(String eventName) {
    for (final action in actions) {
      if (action.eventName == eventName) return action;
    }
    return null;
  }
}
