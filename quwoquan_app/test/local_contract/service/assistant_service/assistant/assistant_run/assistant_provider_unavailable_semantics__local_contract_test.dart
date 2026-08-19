// spec_ref: specs/feature-tree/assistant-run-learning/spec.md#dom-001
// spec_ref: specs/feature-tree/runtime/runtime-errors/error-code-and-response-envelope/spec.md#gwt-002.t1
/// Assistant 外部 Provider 不可用码的 UI 语义契约：五个 MIDDLEWARE
/// unavailable 码（模型/工具/公开检索/金融行情/交集证据）必须经 canonical
/// 错误链路收敛为可重试的依赖失败语义，且 sourceCode 透传，禁止把
/// Provider 缺位伪装成第一方业务失败或空态。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/generated/assistant/assistant_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/errors/runtime_failure_fixtures.dart';

void main() {
  const providerUnavailableCodes = <AssistantErrorCode>[
    AssistantErrorCode.modelProviderUnavailable,
    AssistantErrorCode.toolUnavailable,
    AssistantErrorCode.publicSearchProviderUnavailable,
    AssistantErrorCode.financeProviderUnavailable,
    AssistantErrorCode.intersectionEvidenceUnavailable,
  ];

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

  testWidgets('Provider 不可用码收敛为可重试依赖失败并透传 sourceCode', (tester) async {
    final context = await pumpContext(tester);
    for (final code in providerUnavailableCodes) {
      final semantic = UiErrorSemanticResolver.resolve(
        context,
        error: CloudException(
          type: CloudErrorType.server,
          message: code.defaultMessage,
          statusCode: 503,
          code: code.code,
          runtimeFailure: testRuntimeFailure(
            code: code.code,
            kind: RuntimeFailureKind.unavailable,
            nature: RuntimeFailureNature.transient,
          ),
        ),
        category: UiErrorCategory.pageLoad,
        scope: UiErrorScope.page,
      );
      expect(
        semantic.sourceCode,
        code.code,
        reason: '${code.code} 必须透传给观测与恢复链路',
      );
      expect(
        semantic.recoveryAction,
        RuntimeRecoveryAction.retry,
        reason: '${code.code} 是瞬时依赖失败，必须给用户重试入口',
      );
      expect(
        semantic.message,
        isNotEmpty,
        reason: '${code.code} 必须有用户可理解文案而非空态伪装',
      );
    }
  });

  test('enum fromCode 对五码往返一致', () {
    for (final code in providerUnavailableCodes) {
      expect(AssistantErrorCode.fromCode(code.code), code);
      expect(code.defaultMessage, isNotEmpty);
    }
  });
}
