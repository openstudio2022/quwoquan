// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/spec.md#sit-001
// spec_ref: specs/feature-tree/runtime/runtime-errors/error-code-and-response-envelope/spec.md#gwt-002.t1
/// Chat 错误码契约：generated enum 与 chat/**/errors.yaml 同源往返，且高频
/// 用户可见码经 canonical 错误链路（CloudException -> UiErrorSemanticResolver）
/// 收敛为正确的 sourceCode 与恢复语义。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/generated/chat/chat_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/errors/runtime_failure_fixtures.dart';

void main() {
  group('ChatErrorCode enum 契约', () {
    test('所有错误码非空且 fromCode 往返一致', () {
      for (final value in ChatErrorCode.values) {
        if (value == ChatErrorCode.unknown) continue;
        expect(value.code, isNotEmpty);
        expect(value.code, startsWith('CHAT.'));
        expect(value.defaultMessage, isNotEmpty);
        expect(ChatErrorCode.fromCode(value.code), value);
      }
    });

    test('码清单无重复', () {
      final codes = ChatErrorCode.values
          .where((value) => value != ChatErrorCode.unknown)
          .map((value) => value.code)
          .toList();
      expect(codes.toSet(), hasLength(codes.length));
    });

    test('未知码回退 unknown 而不是抛错', () {
      expect(
        ChatErrorCode.fromCode('CHAT.USER.definitely_missing'),
        ChatErrorCode.unknown,
      );
    });
  });

  group('高频码经 canonical 链路收敛为正确 UI 语义', () {
    Future<BuildContext> pumpContext(WidgetTester tester) async {
      late BuildContext capturedContext;
      await tester.pumpWidget(
        CupertinoApp(
          locale: const Locale('zh'),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Builder(
            builder: (context) {
              capturedContext = context;
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      return capturedContext;
    }

    Future<UiErrorSemantic> resolveChatCode(
      WidgetTester tester,
      ChatErrorCode code, {
      required CloudErrorType type,
      required RuntimeFailureKind kind,
      required RuntimeFailureNature nature,
    }) async {
      final context = await pumpContext(tester);
      return UiErrorSemanticResolver.resolve(
        context,
        error: CloudException(
          type: type,
          message: code.defaultMessage,
          statusCode: code.httpStatus,
          code: code.code,
          runtimeFailure: testRuntimeFailure(
            code: code.code,
            kind: kind,
            nature: nature,
          ),
        ),
        category: UiErrorCategory.pageLoad,
        scope: UiErrorScope.page,
      );
    }

    testWidgets('conversation_not_found 收敛为确定性 not_found 语义', (tester) async {
      final semantic = await resolveChatCode(
        tester,
        ChatErrorCode.conversationNotFound,
        type: CloudErrorType.notFound,
        kind: RuntimeFailureKind.notFound,
        nature: RuntimeFailureNature.permanent,
      );
      expect(semantic.sourceCode, ChatErrorCode.conversationNotFound.code);
      expect(semantic.recoveryAction, isNot(RuntimeRecoveryAction.retry));
    });

    testWidgets('group_full 收敛为确定性拒绝语义（重试不改变结果）', (tester) async {
      final semantic = await resolveChatCode(
        tester,
        ChatErrorCode.groupFull,
        type: CloudErrorType.forbidden,
        kind: RuntimeFailureKind.permission,
        nature: RuntimeFailureNature.permanent,
      );
      expect(semantic.sourceCode, ChatErrorCode.groupFull.code);
      expect(semantic.recoveryAction, isNot(RuntimeRecoveryAction.retry));
    });

    testWidgets('message_media_unavailable 收敛为可重试的依赖失败语义', (tester) async {
      final semantic = await resolveChatCode(
        tester,
        ChatErrorCode.messageMediaUnavailable,
        type: CloudErrorType.server,
        kind: RuntimeFailureKind.unavailable,
        nature: RuntimeFailureNature.transient,
      );
      expect(semantic.sourceCode, ChatErrorCode.messageMediaUnavailable.code);
      expect(semantic.recoveryAction, RuntimeRecoveryAction.retry);
    });

    testWidgets('unauthorized 收敛为登录门语义而非重试', (tester) async {
      final semantic = await resolveChatCode(
        tester,
        ChatErrorCode.unauthorized,
        type: CloudErrorType.unauthorized,
        kind: RuntimeFailureKind.auth,
        nature: RuntimeFailureNature.requiresUserAction,
      );
      expect(semantic.sourceCode, ChatErrorCode.unauthorized.code);
      expect(semantic.recoveryAction, isNot(RuntimeRecoveryAction.retry));
    });
  });
}
