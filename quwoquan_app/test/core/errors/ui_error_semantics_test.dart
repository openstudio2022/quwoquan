import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/entity/generated/entity_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/core/auth/auth_continuation.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';

void main() {
  testWidgets('权限永久拒绝时优先透传本地 permission 文案并给出去设置动作', (tester) async {
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

    final semantic = UiErrorSemanticResolver.resolve(
      capturedContext,
      error: CloudException(
        type: CloudErrorType.forbidden,
        message: '请在设置中为本应用开启定位权限',
      ),
      category: UiErrorCategory.permissionRequired,
      scope: UiErrorScope.page,
      allowRetry: false,
      allowOpenSettings: true,
    );

    expect(semantic.message, '请在设置中为本应用开启定位权限');
    expect(semantic.primaryAction?.type, UiErrorActionType.openSettings);
    expect(semantic.primaryAction?.label, '去设置');
  });

  testWidgets('auth gate 语义会携带 continuation 的续接提示', (tester) async {
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

    final semantic = authGateSemantic(
      capturedContext,
      reason: AuthGateReason.startGroupChat,
      continuation: const OpenSheetContinuation(
        AuthContinuationSheet.startGroupChat,
      ),
      scope: UiErrorScope.section,
    );

    expect(semantic.category, UiErrorCategory.authRequired);
    expect(semantic.primaryAction?.type, UiErrorActionType.login);
    expect(semantic.secondaryMessage, '登录后将继续打开发起讨论流程');
  });

  testWidgets('列表追加失败映射为 footer 而不是区块卡片', (tester) async {
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

    final semantic = UiErrorSemanticResolver.resolve(
      capturedContext,
      error: CloudException(type: CloudErrorType.network, message: 'network'),
      category: UiErrorCategory.listAppend,
      scope: UiErrorScope.section,
    );

    expect(semantic.presentation, UiErrorPresentation.appendFooter);
    expect(semantic.message, UITextConstants.appendFailedRetry);
    expect(semantic.copyKey, 'appendFailedRetry');
    expect(semantic.primaryAction?.label, '再试一次');
  });

  testWidgets('后台刷新失败映射为短暂提示且不强制重试按钮', (tester) async {
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

    final semantic = UiErrorSemanticResolver.resolve(
      capturedContext,
      error: CloudException(type: CloudErrorType.network, message: 'network'),
      category: UiErrorCategory.backgroundAction,
      scope: UiErrorScope.section,
      allowRetry: false,
    );

    expect(semantic.presentation, UiErrorPresentation.transientNotice);
    expect(semantic.primaryAction, isNull);
  });

  testWidgets('无本地化上下文时也按错误码给出可理解的失效页文案', (tester) async {
    late BuildContext capturedContext;
    await tester.pumpWidget(
      CupertinoApp(
        home: Builder(
          builder: (context) {
            capturedContext = context;
            return const SizedBox.shrink();
          },
        ),
      ),
    );

    final semantic = UiErrorSemanticResolver.resolve(
      capturedContext,
      error: CloudException(
        type: CloudErrorType.notFound,
        message: 'Not found',
        code: EntityErrorCode.homepageNotFound.code,
      ),
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
      allowRetry: false,
    );

    expect(semantic.title, UITextConstants.homepageLoadFailedTitle);
    expect(semantic.message, UITextConstants.contentUnavailableReason);
    expect(semantic.copyKey, 'homepageLoadFailedTitle');
    expect(semantic.primaryAction, isNull);
  });
}
