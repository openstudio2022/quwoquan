import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/observability/analytics.dart';
import 'package:quwoquan_app/service/content_service/content/comment/application/comment_remote_config.dart';
import 'package:quwoquan_app/service/content_service/trust_safety/report/application/public/content_report_ports.dart';
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/service/content_service/content/comment/presentation/comment_thread_view.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/content_service/content/comment/in_memory_content_comment_facet.dart';

void main() {
  testWidgets('删除评论必须二次确认，取消不执行命令', (tester) async {
    final comments = InMemoryContentCommentFacet(
      items: <CommentListItem>[
        testCommentItem(
          id: 'comment-delete',
          postId: 'post-delete',
          content: '待确认删除的评论',
          isAuthor: true,
          canDelete: true,
          canReport: false,
        ),
      ],
    );
    final container = _container(comments: comments);
    addTearDown(container.dispose);
    await tester.pumpWidget(
      _app(container, const CommentThreadView(postId: 'post-delete')),
    );
    await tester.pumpAndSettle();

    await tester.longPress(find.text('待确认删除的评论'));
    await tester.pumpAndSettle();
    await tester.tap(find.text(ContentText.commentDeleteAction).last);
    await tester.pumpAndSettle();

    expect(find.text(ContentText.commentDeleteConfirmTitle), findsOneWidget);
    expect(comments.deleteCalls, 0);
    await tester.tap(find.text(FoundationText.cancel));
    await tester.pumpAndSettle();
    expect(comments.deleteCalls, 0);

    await tester.longPress(find.text('待确认删除的评论'));
    await tester.pumpAndSettle();
    await tester.tap(find.text(ContentText.commentDeleteAction).last);
    await tester.pumpAndSettle();
    await tester.tap(find.text(ContentText.commentDeleteAction).last);
    await tester.pumpAndSettle();

    expect(comments.deleteCalls, 1);
    expect(comments.lastDeleteCommand?.commentId, 'comment-delete');
  });

  testWidgets('可见删除快捷入口与更多操作均可访问且共用二次确认', (tester) async {
    final comments = InMemoryContentCommentFacet(
      items: <CommentListItem>[
        testCommentItem(
          id: 'comment-delete-shortcut',
          postId: 'post-delete-shortcut',
          content: '快捷入口也不能直接删除',
          isAuthor: true,
          canDelete: true,
          canReport: false,
        ),
      ],
    );
    final container = _container(comments: comments);
    addTearDown(container.dispose);
    await tester.pumpWidget(
      _app(container, const CommentThreadView(postId: 'post-delete-shortcut')),
    );
    await tester.pumpAndSettle();

    expect(
      find.bySemanticsLabel(ContentText.commentMoreActions),
      findsOneWidget,
    );
    await tester.tap(find.byIcon(CupertinoIcons.trash));
    await tester.pumpAndSettle();

    expect(find.text(ContentText.commentDeleteConfirmTitle), findsOneWidget);
    expect(comments.deleteCalls, 0);
    await tester.tap(find.text(ContentText.commentDeleteAction).last);
    await tester.pumpAndSettle();

    expect(comments.deleteCalls, 1);
    expect(comments.lastDeleteCommand?.commentId, 'comment-delete-shortcut');
  });

  testWidgets('登录成功后原 CommentThread 续接 typed 评论举报', (tester) async {
    final comments = InMemoryContentCommentFacet();
    final reports = _RecordingContentReportWriter();
    const pending = SubmitCommentReportContinuation(
      postId: 'post-report',
      commentId: 'comment-report',
      reason: ReportReason.spam,
    );
    final container = _container(
      comments: comments,
      reports: reports,
      continuation: pending,
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      _app(container, const CommentThreadView(postId: 'post-report')),
    );
    await tester.pumpAndSettle();

    expect(reports.commands, hasLength(1));
    expect(reports.commands.single.targetId, 'comment-report');
    expect(reports.commands.single.targetType, ReportTargetType.comment);
    expect(reports.commands.single.reason, ReportReason.spam);
    expect(container.read(authContinuationProvider), isNull);
    await tester.pump(const Duration(seconds: 3));
  });
}

ProviderContainer _container({
  required ContentCommentFacet comments,
  ContentReportWriter? reports,
  AuthContinuation? continuation,
}) {
  return ProviderContainer(
    overrides: [
      workBrowserContentCommentFacetProvider.overrideWithValue(comments),
      commentRemoteConfigProvider.overrideWithValue(
        const CommentRemoteConfig(),
      ),
      analyticsProvider.overrideWithValue(AnalyticsService.forTesting()),
      authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
      if (reports != null)
        workBrowserContentReportCommandWriterProvider.overrideWithValue(
          reports,
        ),
      if (continuation != null)
        authContinuationProvider.overrideWith(
          () => _PendingAuthContinuation(continuation),
        ),
    ],
  );
}

Widget _app(ProviderContainer container, Widget child) {
  return UncontrolledProviderScope(
    container: container,
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

class _PendingAuthContinuation extends AuthContinuationController {
  _PendingAuthContinuation(this.pending);

  final AuthContinuation pending;

  @override
  AuthContinuation? build() => pending;
}

class _RecordingContentReportWriter implements ContentReportWriter {
  final List<CreateContentReportCommand> commands =
      <CreateContentReportCommand>[];

  @override
  Future<void> createReport(CreateContentReportCommand command) async {
    commands.add(command);
  }
}
