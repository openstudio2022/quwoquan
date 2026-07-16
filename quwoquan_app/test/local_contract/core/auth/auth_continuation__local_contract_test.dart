import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/components/comment_system/comment_composer_models.dart';
import 'package:quwoquan_app/ui/content/comments/widgets/comment_input_overlay.dart';
import 'package:quwoquan_app/core/auth/auth_continuation.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('AuthContinuationController', () {
    test('set / take<匹配类型> / clear 的单槽位语义', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);
      final controller = container.read(authContinuationProvider.notifier);

      expect(container.read(authContinuationProvider), isNull);

      final accepted = controller.set(
        SubmitCommentContinuation(
          content: '游客想说的话',
          replyToCommentId: 'c1',
          attachmentMediaIds: const <String>['media-1'],
          mentions: <ContentCommentMention>[
            ContentCommentMention(
              subjectType: 'assistant',
              subjectId: 'assistant_xiaoqu',
              displayName: '小趣',
            ),
          ],
        ),
        ownerToken: 'comment-action-1',
      );
      expect(accepted, isTrue);
      expect(controller.ownerToken, 'comment-action-1');
      expect(container.read(authContinuationProvider), isNotNull);

      final overwritten = controller.set(
        const JoinCircleContinuation(circleId: 'circle-2'),
        ownerToken: 'circle-action-2',
      );
      expect(overwritten, isFalse, reason: '第二个受限动作不得覆盖首个续接所有者');
      expect(controller.ownerToken, 'comment-action-1');

      // 类型不匹配不取出、不清空。
      expect(controller.take<JoinCircleContinuation>(), isNull);
      expect(container.read(authContinuationProvider), isNotNull);

      final taken = controller.take<SubmitCommentContinuation>();
      expect(taken, isNotNull);
      expect(taken!.content, '游客想说的话');
      expect(taken.replyToCommentId, 'c1');
      expect(taken.attachmentMediaIds, const <String>['media-1']);
      expect(taken.mentions.single.subjectId, 'assistant_xiaoqu');
      // 取出后清空，二次 take 为空（杜绝重复续接）。
      expect(container.read(authContinuationProvider), isNull);
      expect(controller.take<SubmitCommentContinuation>(), isNull);
    });
  });

  group('评论统一输入浮层登录续接', () {
    testWidgets('游客输入评论点提交→登记续接并引导登录→登录后同一浮层续提原文本', (tester) async {
      AuthGate.resetDebounce();
      final submitted = <CommentComposerPayload>[];
      final container = ProviderContainer(
        overrides: [
          authSessionControllerProvider.overrideWith(_FlippableSession.new),
        ],
      );
      addTearDown(container.dispose);

      final router = GoRouter(
        initialLocation: '/home',
        routes: [
          GoRoute(
            path: '/home',
            builder: (context, state) => Scaffold(
              body: Builder(
                builder: (context) => Center(
                  child: ElevatedButton(
                    onPressed: () => CommentInputOverlay.show(
                      context,
                      postId: 'post-1',
                      onSubmit: submitted.add,
                    ),
                    child: const Text('open-input'),
                  ),
                ),
              ),
            ),
          ),
          GoRoute(
            path: '/login',
            builder: (context, state) =>
                const Scaffold(body: Center(child: Text('LOGIN_PLACEHOLDER'))),
          ),
        ],
      );

      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: container,
          child: MaterialApp.router(
            localizationsDelegates: const [
              AppLocalizations.delegate,
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
            routerConfig: router,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('open-input'));
      await tester.pumpAndSettle();

      await tester.enterText(find.byKey(TestKeys.commentTextField), '第一条评论');
      await tester.pump();
      await tester.tap(find.byKey(TestKeys.submitCommentButton));
      await tester.pumpAndSettle();

      // 游客提交：未登录，已引导到登录占位页，评论未发出，但待续接评论已登记。
      expect(find.text('LOGIN_PLACEHOLDER'), findsOneWidget);
      expect(submitted, isEmpty);
      expect(
        container.read(authContinuationProvider),
        isA<SubmitCommentContinuation>(),
      );

      // 模拟登录成功：浮层仍在栈上并监听登录态翻转，自动续提原文本。
      (container.read(authSessionControllerProvider.notifier)
              as _FlippableSession)
          .loginNow();
      await tester.pumpAndSettle();

      expect(submitted.length, 1);
      expect(submitted.single.content, '第一条评论');
      // 续接后槽位清空，不会重复发出。
      expect(container.read(authContinuationProvider), isNull);

      await tester.pump(const Duration(seconds: 3));
    });
  });
}

/// 可控测试会话：初始为游客，调用 [loginNow] 翻转为已认证以触发登录后续接。
class _FlippableSession extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);

  void loginNow() {
    state = const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'test-token',
      ownerId: 'test-user',
      activeSubAccountId: 'test-user',
      accountState: 'active',
      identityOrigin: 'phone',
      installId: 'test-install',
    );
  }
}
