/// T2 模块交互：评论详情「有新评论」通知位展示可解释增量
/// 「较进入时新增 N 条 / 删除 M 条评论」（对齐 T1 mock 半开区间语义字段）。
///
/// 隔离策略：不初始化 Hive。`postInteractionState` 持久化（best-effort）在无 Hive
/// 时静默失败，不创建任何盒子/锁，避免 fake-async 区残留的 Hive 写阻塞下一测试。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/cloud/runtime/models/comment_remote_config.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/components/comment_system/comment_thread_view.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/providers/comment_provider.dart';

/// 受控 delta 桩：首同步（since=null）只建基线；后续 poll 返回固定 created/deleted，
/// 隔离时间不确定性，专注断言 UI 文案装配（半开语义已在 T1 mock 覆盖）。
class _DeltaStubRepository extends MockContentRepository {
  _DeltaStubRepository({
    required this.postId,
    required this.createdOnPoll,
    required this.deletedOnPoll,
    required this.currentTotalOnPoll,
  }) {
    commentsStub = <CommentDto>[
      CommentDto(
        id: 'c1',
        postId: postId,
        authorId: 'u1',
        content: '第一条',
        recommendedScore: 2,
        createdAt: DateTime.utc(2026, 6, 1),
      ),
      CommentDto(
        id: 'c2',
        postId: postId,
        authorId: 'u2',
        content: '第二条',
        recommendedScore: 1,
        createdAt: DateTime.utc(2026, 6, 2),
      ),
    ];
  }

  final String postId;
  final int createdOnPoll;
  final int deletedOnPoll;
  final int currentTotalOnPoll;

  static final DateTime baselineWatermark = DateTime.utc(2026, 6, 20, 9, 0);
  static final DateTime pollWatermark = DateTime.utc(2026, 6, 20, 9, 30);

  @override
  Future<CommentCountsDelta> getCommentCountsDelta({
    required String postId,
    DateTime? since,
  }) async {
    if (since == null) {
      return CommentCountsDelta(
        createdSinceCount: 0,
        deletedSinceCount: 0,
        currentTotal: 2,
        watermark: baselineWatermark,
      );
    }
    return CommentCountsDelta(
      createdSinceCount: createdOnPoll,
      deletedSinceCount: deletedOnPoll,
      currentTotal: currentTotalOnPoll,
      watermark: pollWatermark,
      since: since,
    );
  }
}

Widget _app(_DeltaStubRepository repo, String postId) {
  // 用 ProviderScope（随 widget 树释放）承载 provider，确保测试结束时
  // 30s 轮询定时器随容器释放取消，避免 pending timer 断言失败。
  return ProviderScope(
    overrides: [
      contentRepositoryProvider.overrideWithValue(repo),
      analyticsProvider.overrideWithValue(AnalyticsService.forTesting()),
      commentRemoteConfigProvider.overrideWithValue(const CommentRemoteConfig()),
    ],
    child: CupertinoApp(
      locale: const Locale('zh'),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: CupertinoPageScaffold(child: CommentThreadView(postId: postId)),
    ),
  );
}

/// 有界 pump：让异步 loadComments/checkForNewComments 落定，又不被
/// CupertinoActivityIndicator 等持续动画拖死（pumpAndSettle 会无限等待）。
Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 8; i++) {
    await tester.pump(const Duration(milliseconds: 20));
  }
}

/// 卸载组件树，触发 provider 释放并取消 30s 共享轮询定时器，
/// 隔离跨测静态状态，避免上一测试残留定时器影响下一测试。
Future<void> _disposeTree(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump();
}

/// 先 pump 详情（触发并完成 auto loadComments 建立基线），再在「轮询时机」
/// 调 checkForNewComments 产出可解释 delta；返回 widget 树的 container 供断言。
Future<ProviderContainer> _pumpAndPrimeDelta(
  WidgetTester tester, {
  required String postId,
  required _DeltaStubRepository repo,
}) async {
  await tester.pumpWidget(_app(repo, postId));
  await _settle(tester);
  final container = ProviderScope.containerOf(
    tester.element(find.byType(CommentThreadView)),
  );
  await container
      .read(commentProviderFamily(postId).notifier)
      .checkForNewComments();
  await _settle(tester);
  return container;
}

void main() {
  testWidgets('新增与删除并存：通知位展示「新增 N 条 / 删除 M 条」', (tester) async {
    const postId = 'delta-notice-both';
    final repo = _DeltaStubRepository(
      postId: postId,
      createdOnPoll: 2,
      deletedOnPoll: 1,
      currentTotalOnPoll: 3,
    );
    final container = await _pumpAndPrimeDelta(
      tester,
      postId: postId,
      repo: repo,
    );

    final state = container.read(commentProviderFamily(postId));
    expect(state.hasNewComments, isTrue);
    expect(state.countsDelta?.createdSinceCount, 2);
    expect(state.countsDelta?.deletedSinceCount, 1);

    final noticeFinder = find.byKey(TestKeys.commentCountsDeltaNotice);
    expect(noticeFinder, findsOneWidget);
    final text = tester.widget<Text>(noticeFinder).data;
    expect(text, contains('新增 2'));
    expect(text, contains('删除 1'));

    await _disposeTree(tester);
  });

  testWidgets('仅新增：通知位展示「新增 N 条」', (tester) async {
    const postId = 'delta-notice-created';
    final repo = _DeltaStubRepository(
      postId: postId,
      createdOnPoll: 5,
      deletedOnPoll: 0,
      currentTotalOnPoll: 7,
    );
    final container = await _pumpAndPrimeDelta(
      tester,
      postId: postId,
      repo: repo,
    );

    final state = container.read(commentProviderFamily(postId));
    expect(state.countsDelta?.createdSinceCount, 5);
    expect(state.countsDelta?.deletedSinceCount, 0);

    final text = tester
        .widget<Text>(find.byKey(TestKeys.commentCountsDeltaNotice))
        .data;
    expect(text, contains('新增 5'));
    expect(text, isNot(contains('删除')));

    await _disposeTree(tester);
  });

  testWidgets('点击通知刷新后推进基线并清空增量解释', (tester) async {
    const postId = 'delta-notice-refresh';
    final repo = _DeltaStubRepository(
      postId: postId,
      createdOnPoll: 2,
      deletedOnPoll: 1,
      currentTotalOnPoll: 3,
    );
    final container = await _pumpAndPrimeDelta(
      tester,
      postId: postId,
      repo: repo,
    );

    expect(find.byKey(TestKeys.commentCountsDeltaNotice), findsOneWidget);

    await tester.tap(find.byKey(TestKeys.commentCountsDeltaNotice));
    await _settle(tester);

    final state = container.read(commentProviderFamily(postId));
    expect(state.hasNewComments, isFalse);
    expect(state.countsDelta, isNull);
    expect(
      state.baselineWatermark,
      _DeltaStubRepository.pollWatermark,
      reason: '基线推进到已展示 delta 的 watermark',
    );
    expect(find.byKey(TestKeys.commentCountsDeltaNotice), findsNothing);

    await _disposeTree(tester);
  });
}
