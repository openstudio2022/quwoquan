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
  test('source appearance helpers map route values and brightness', () {
    expect(
      uiErrorAppearanceModeFromRouteValue('light'),
      UiErrorAppearanceMode.light,
    );
    expect(
      uiErrorAppearanceModeFromRouteValue('dark'),
      UiErrorAppearanceMode.dark,
    );
    expect(
      uiErrorAppearanceModeFromRouteValue(null),
      UiErrorAppearanceMode.inherit,
    );
    expect(
      uiErrorAppearanceModeFromBrightness(Brightness.light).routeValue,
      'light',
    );
    expect(
      uiErrorAppearanceModeFromBrightness(Brightness.dark).routeValue,
      'dark',
    );
  });

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

  // 错误展示载体决策矩阵：守护 specs/ux/error-and-permission-semantics.md §1.13.2
  // 与 UiErrorSemanticResolver._presentationFor 的一一对应。任何改动需同步本组断言。
  group('错误展示载体决策矩阵', () {
    Future<UiErrorSemantic> resolveCase(
      WidgetTester tester, {
      required UiErrorCategory category,
      required UiErrorScope scope,
    }) async {
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
      return UiErrorSemanticResolver.resolve(
        capturedContext,
        error: CloudException(type: CloudErrorType.network, message: 'network'),
        category: category,
        scope: scope,
      );
    }

    testWidgets('规则1 inlineField scope → inlineField', (tester) async {
      final semantic = await resolveCase(
        tester,
        category: UiErrorCategory.validation,
        scope: UiErrorScope.inlineField,
      );
      expect(semantic.presentation, UiErrorPresentation.inlineField);
    });

    testWidgets('规则2 authRequired/permissionRequired → gateCard', (
      tester,
    ) async {
      final auth = await resolveCase(
        tester,
        category: UiErrorCategory.authRequired,
        scope: UiErrorScope.page,
      );
      expect(auth.presentation, UiErrorPresentation.gateCard);
      final perm = await resolveCase(
        tester,
        category: UiErrorCategory.permissionRequired,
        scope: UiErrorScope.page,
      );
      expect(perm.presentation, UiErrorPresentation.gateCard);
    });

    testWidgets('规则3 listAppend → appendFooter', (tester) async {
      final semantic = await resolveCase(
        tester,
        category: UiErrorCategory.listAppend,
        scope: UiErrorScope.page,
      );
      expect(semantic.presentation, UiErrorPresentation.appendFooter);
    });

    testWidgets('规则4 backgroundAction → transientNotice', (tester) async {
      final semantic = await resolveCase(
        tester,
        category: UiErrorCategory.backgroundAction,
        scope: UiErrorScope.section,
      );
      expect(semantic.presentation, UiErrorPresentation.transientNotice);
    });

    testWidgets('规则5 submit/rateLimited 或 dialog/global scope → actionDialog', (
      tester,
    ) async {
      final submit = await resolveCase(
        tester,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      expect(submit.presentation, UiErrorPresentation.actionDialog);
      final rate = await resolveCase(
        tester,
        category: UiErrorCategory.rateLimited,
        scope: UiErrorScope.page,
      );
      expect(rate.presentation, UiErrorPresentation.actionDialog);
      final dialogScope = await resolveCase(
        tester,
        category: UiErrorCategory.pageLoad,
        scope: UiErrorScope.dialog,
      );
      expect(dialogScope.presentation, UiErrorPresentation.actionDialog);
    });

    testWidgets('规则6 section scope 或 sectionLoad → sectionSoftCard', (
      tester,
    ) async {
      final byScope = await resolveCase(
        tester,
        category: UiErrorCategory.pageLoad,
        scope: UiErrorScope.section,
      );
      expect(byScope.presentation, UiErrorPresentation.sectionSoftCard);
      final byCategory = await resolveCase(
        tester,
        category: UiErrorCategory.sectionLoad,
        scope: UiErrorScope.page,
      );
      expect(byCategory.presentation, UiErrorPresentation.sectionSoftCard);
    });

    testWidgets('规则7 默认 pageLoad + page → emptyPage(全屏)', (tester) async {
      final semantic = await resolveCase(
        tester,
        category: UiErrorCategory.pageLoad,
        scope: UiErrorScope.page,
      );
      expect(semantic.presentation, UiErrorPresentation.emptyPage);
    });

    testWidgets('红线 提交失败即使在 section scope 也走弹窗而非全屏(保留用户输入)', (tester) async {
      final semantic = await resolveCase(
        tester,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.section,
      );
      expect(semantic.presentation, UiErrorPresentation.actionDialog);
      expect(semantic.presentation, isNot(UiErrorPresentation.emptyPage));
    });
  });
}
