// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-009
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-013
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import '../../../support/runtime/errors/runtime_failure_fixtures.dart';

void main() {
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

  test('用户恢复组文案只表达已确认事实与可执行下一步', () {
    for (final group in AppUserRecoveryGroup.values) {
      final copy = AppUserRecoveryContract.copyFor(group);
      final visibleCopy = '${copy.title}${copy.message}${copy.action.label}';
      expect(
        visibleCopy,
        isNot(
          anyOf(
            contains('DNS'),
            contains('TLS'),
            contains('HTTP'),
            contains('证书'),
            contains('趣我圈'),
          ),
        ),
        reason: group.name,
      );
      expect(copy.title.trim(), isNot(copy.message.trim()), reason: group.name);
      expect(
        copy.title.trim(),
        isNot(copy.action.label.trim()),
        reason: group.name,
      );
      expect(
        copy.message,
        isNot(contains(copy.action.label)),
        reason: '${group.name} 的说明不应复述动作',
      );
    }
    expect(
      AppUserRecoveryContract.copyFor(AppUserRecoveryGroup.reloadLater).title,
      SearchText.recoveryReloadLaterTitle,
    );
  });

  testWidgets('权限错误不透传技术或页面文案，统一为可执行的去设置语义', (tester) async {
    final semantic = UiErrorSemanticResolver.resolve(
      await pumpContext(tester),
      error: CloudException(
        type: CloudErrorType.forbidden,
        message: 'permission denied permanently',
        runtimeFailure: testRuntimeFailure(
          code: 'INTEGRATION.USER.location_permission_required',
          kind: RuntimeFailureKind.permission,
          nature: RuntimeFailureNature.requiresPermission,
        ),
      ),
      category: UiErrorCategory.permissionRequired,
      scope: UiErrorScope.page,
      allowRetry: false,
      allowOpenSettings: true,
    );

    expect(semantic.userRecoveryGroup, AppUserRecoveryGroup.enablePermission);
    expect(semantic.title, SearchText.recoveryEnablePermissionTitle);
    expect(semantic.message, SearchText.recoveryEnablePermissionMessage);
    expect(semantic.primaryAction?.type, UiErrorActionType.openSettings);
    expect(
      semantic.primaryAction?.label,
      SearchText.recoveryEnablePermissionAction,
    );
  });

  testWidgets('auth gate 不按业务动作改写用户标题和说明', (tester) async {
    final semantic = authGateSemantic(
      await pumpContext(tester),
      reason: AuthGateReason.startGroupChat,
      scope: UiErrorScope.section,
    );

    expect(semantic.category, UiErrorCategory.authRequired);
    expect(semantic.userRecoveryGroup, AppUserRecoveryGroup.loginAgain);
    expect(semantic.title, SearchText.recoveryLoginAgainTitle);
    expect(semantic.message, SearchText.recoveryLoginAgainMessage);
    expect(semantic.primaryAction?.type, UiErrorActionType.login);
    expect(semantic.secondaryMessage, isNull);
  });

  testWidgets('发起活动 continuation 提供精确的登录后续接说明', (tester) async {
    final semantic = authGateSemantic(
      await pumpContext(tester),
      reason: AuthGateReason.startGathering,
      continuation: const OpenSheetContinuation(
        AuthContinuationSheet.startGathering,
      ),
      scope: UiErrorScope.section,
    );

    expect(semantic.category, UiErrorCategory.authRequired);
    expect(
      semantic.secondaryMessage,
      CommunityText.authContinuationStartGathering,
    );
  });

  testWidgets('列表追加仍用 footer，但文案和动作来自恢复组', (tester) async {
    final semantic = UiErrorSemanticResolver.resolve(
      await pumpContext(tester),
      error: CloudException(
        type: CloudErrorType.network,
        message: 'network',
        runtimeFailure: testRuntimeFailure(
          code: 'APP.NETWORK.offline',
          kind: RuntimeFailureKind.network,
          nature: RuntimeFailureNature.transient,
        ),
      ),
      category: UiErrorCategory.listAppend,
      scope: UiErrorScope.section,
    );

    expect(semantic.presentation, UiErrorPresentation.appendFooter);
    expect(semantic.userRecoveryGroup, AppUserRecoveryGroup.connectNetwork);
    expect(semantic.message, SearchText.recoveryConnectNetworkMessage);
    expect(semantic.copyKey, 'recovery.connectNetwork');
    expect(semantic.primaryAction?.label, SearchText.reload);
  });

  testWidgets('后台刷新保留短提示，恢复组合同仍保持唯一动作', (tester) async {
    final semantic = UiErrorSemanticResolver.resolve(
      await pumpContext(tester),
      error: CloudException(
        type: CloudErrorType.network,
        message: 'network',
        runtimeFailure: testRuntimeFailure(
          code: 'APP.NETWORK.offline',
          kind: RuntimeFailureKind.network,
          nature: RuntimeFailureNature.transient,
        ),
      ),
      category: UiErrorCategory.backgroundAction,
      scope: UiErrorScope.section,
      allowRetry: false,
    );

    expect(semantic.presentation, UiErrorPresentation.transientNotice);
    expect(semantic.primaryAction?.label, SearchText.reload);
  });

  testWidgets('不透明 404 只陈述内容不可用事实，不猜测具体删除原因', (tester) async {
    final semantic = UiErrorSemanticResolver.resolve(
      await pumpContext(tester),
      error: CloudErrorMapper.fromStatusCode(
        404,
        requestPath: '/content/opaque-id',
      ),
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );

    expect(semantic.userRecoveryGroup, AppUserRecoveryGroup.contentUnavailable);
    expect(semantic.title, SearchText.recoveryContentUnavailableTitle);
    expect(semantic.message, SearchText.recoveryContentUnavailableMessage);
    expect(semantic.primaryAction?.type, UiErrorActionType.dismiss);
  });

  testWidgets('仅系统确认离线进入连网组，拒绝连接进入连接不可用组', (tester) async {
    final context = await pumpContext(tester);
    final offline = UiErrorSemanticResolver.resolve(
      context,
      error: CloudException(
        type: CloudErrorType.network,
        message: 'offline',
        runtimeFailure: testRuntimeFailure(
          code: RuntimeFailureCodes.appNetworkOffline,
          kind: RuntimeFailureKind.network,
        ),
      ),
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
    final refused = UiErrorSemanticResolver.resolve(
      context,
      error: CloudException(
        type: CloudErrorType.network,
        message: 'connection refused',
        requestId: 'request-1',
        traceId: 'trace-1',
        runtimeFailure: testRuntimeFailure(
          code: RuntimeFailureCodes.appNetworkConnectionRefused,
          kind: RuntimeFailureKind.network,
        ),
      ),
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
      sourceOperationId: AppCloudOperationIds.contentPostGetFeed,
    );

    expect(offline.userRecoveryGroup, AppUserRecoveryGroup.connectNetwork);
    expect(offline.title, SearchText.recoveryConnectNetworkTitle);
    expect(offline.message, SearchText.recoveryConnectNetworkMessage);
    expect(
      refused.userRecoveryGroup,
      AppUserRecoveryGroup.connectionUnavailable,
    );
    expect(refused.title, SearchText.recoveryConnectionUnavailableTitle);
    expect(refused.message, SearchText.recoveryConnectionUnavailableMessage);
    expect(refused.sourceOperationId, AppCloudOperationIds.contentPostGetFeed);
    expect(refused.requestId, 'request-1');
    expect(refused.traceId, 'trace-1');
  });

  testWidgets('组合查询保留实际失败 operation，禁止被页面外层 GetFeed 覆盖', (tester) async {
    final semantic = UiErrorSemanticResolver.resolve(
      await pumpContext(tester),
      error: CloudException(
        type: CloudErrorType.notFound,
        message: 'privacy route missing',
        statusCode: 404,
        sourceOperationId: 'GetPrivacySettings',
        runtimeFailure: testRuntimeFailure(
          code: 'APP.USER.not_found',
          kind: RuntimeFailureKind.notFound,
        ),
      ),
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
      sourceOperationId: 'GetFeed',
    );

    expect(semantic.sourceOperationId, 'GetPrivacySettings');
    expect(semantic.userRecoveryGroup, AppUserRecoveryGroup.contentUnavailable);
    expect(semantic.title, SearchText.recoveryContentUnavailableTitle);
    expect(semantic.title, isNot(SearchText.feedVersionMismatchTitle));
  });

  testWidgets('DNS、TLS、5xx、超时、响应异常和未知异常进入各自恢复组', (tester) async {
    final context = await pumpContext(tester);
    final cases =
        <
          ({
            Object error,
            AppUserRecoveryGroup group,
            String title,
            String message,
          })
        >[
          (
            error: CloudException(
              type: CloudErrorType.network,
              message: 'dns',
              runtimeFailure: testRuntimeFailure(
                code: RuntimeFailureCodes.appNetworkNameResolutionFailed,
                kind: RuntimeFailureKind.network,
                nature: RuntimeFailureNature.transient,
              ),
            ),
            group: AppUserRecoveryGroup.connectionUnavailable,
            title: SearchText.recoveryConnectionUnavailableTitle,
            message: SearchText.recoveryConnectionUnavailableMessage,
          ),
          (
            error: CloudException(
              type: CloudErrorType.network,
              message: 'tls',
              runtimeFailure: testRuntimeFailure(
                code: RuntimeFailureCodes.appNetworkSecureConnectionFailed,
                kind: RuntimeFailureKind.network,
                nature: RuntimeFailureNature.permanent,
              ),
            ),
            group: AppUserRecoveryGroup.connectionUnavailable,
            title: SearchText.recoveryConnectionUnavailableTitle,
            message: SearchText.recoveryConnectionUnavailableMessage,
          ),
          (
            error: CloudErrorMapper.fromStatusCode(
              500,
              requestPath: '/content/feed',
            ),
            group: AppUserRecoveryGroup.serviceUnavailable,
            title: SearchText.recoveryServiceUnavailableTitle,
            message: SearchText.recoveryServiceUnavailableMessage,
          ),
          (
            error: CloudErrorMapper.fromStatusCode(
              504,
              requestPath: '/content/feed',
            ),
            group: AppUserRecoveryGroup.requestTimedOut,
            title: SearchText.recoveryRequestTimedOutTitle,
            message: SearchText.recoveryRequestTimedOutMessage,
          ),
          (
            error: CloudErrorMapper.invalidResponse(
              message: 'unexpected response shape',
              requestPath: '/content/feed',
            ),
            group: AppUserRecoveryGroup.invalidContent,
            title: SearchText.recoveryInvalidContentTitle,
            message: SearchText.recoveryInvalidContentMessage,
          ),
          (
            error: Exception('unexpected response shape'),
            group: AppUserRecoveryGroup.reloadLater,
            title: SearchText.recoveryReloadLaterTitle,
            message: SearchText.recoveryReloadLaterMessage,
          ),
        ];

    for (final entry in cases) {
      final semantic = UiErrorSemanticResolver.resolve(
        context,
        error: entry.error,
        category: UiErrorCategory.pageLoad,
        scope: UiErrorScope.page,
      );
      expect(semantic.userRecoveryGroup, entry.group);
      expect(semantic.title, entry.title);
      expect(semantic.message, entry.message);
      expect(semantic.primaryAction?.type, UiErrorActionType.retry);
    }
  });

  testWidgets('公开或可选鉴权 Feed 的 401 重试游客会话而不要求登录', (tester) async {
    final semantic = UiErrorSemanticResolver.resolve(
      await pumpContext(tester),
      error: CloudErrorMapper.fromStatusCode(401, requestPath: '/content/feed'),
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
      sourceOperationId: AppCloudOperationIds.contentPostGetFeed,
    );

    expect(
      semantic.userRecoveryGroup,
      AppUserRecoveryGroup.guestSessionUnavailable,
    );
    expect(semantic.title, SearchText.recoveryGuestSessionUnavailableTitle);
    expect(semantic.message, SearchText.recoveryGuestSessionUnavailableMessage);
    expect(semantic.primaryAction?.type, UiErrorActionType.retry);
  });

  testWidgets('明确删除事实与普通 404 使用不同视觉语义', (tester) async {
    final context = await pumpContext(tester);
    final gone = UiErrorSemanticResolver.resolve(
      context,
      error: CloudException(
        type: CloudErrorType.notFound,
        message: 'gone',
        code: ContentErrorCode.contentDeleted.code,
        statusCode: 410,
        runtimeFailure: testRuntimeFailure(
          code: ContentErrorCode.contentDeleted.code,
          kind: RuntimeFailureKind.notFound,
        ),
      ),
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
    final opaque = UiErrorSemanticResolver.resolve(
      context,
      error: CloudErrorMapper.fromStatusCode(
        404,
        requestPath: '/content/opaque-id',
      ),
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );

    expect(gone.userRecoveryGroup, AppUserRecoveryGroup.contentGone);
    expect(gone.title, SearchText.recoveryContentGoneTitle);
    expect(opaque.userRecoveryGroup, AppUserRecoveryGroup.contentUnavailable);
    expect(opaque.title, SearchText.recoveryContentUnavailableTitle);
  });

  testWidgets('Feed HTTP 状态只映射到唯一用户恢复组', (tester) async {
    final context = await pumpContext(tester);
    const expected = <int, AppUserRecoveryGroup>{
      400: AppUserRecoveryGroup.reloadLater,
      401: AppUserRecoveryGroup.guestSessionUnavailable,
      403: AppUserRecoveryGroup.noAccess,
      404: AppUserRecoveryGroup.contentUnavailable,
      409: AppUserRecoveryGroup.reloadLater,
      422: AppUserRecoveryGroup.reloadLater,
      429: AppUserRecoveryGroup.waitThenReload,
      500: AppUserRecoveryGroup.serviceUnavailable,
      503: AppUserRecoveryGroup.serviceUnavailable,
      504: AppUserRecoveryGroup.requestTimedOut,
    };

    for (final entry in expected.entries) {
      final semantic = UiErrorSemanticResolver.resolve(
        context,
        error: CloudErrorMapper.fromStatusCode(
          entry.key,
          requestPath: '/content/feed',
          retryAfter: entry.key == 429 ? '12' : null,
        ),
        category: UiErrorCategory.pageLoad,
        scope: UiErrorScope.page,
        sourceOperationId: AppCloudOperationIds.contentPostGetFeed,
      );
      final copy = AppUserRecoveryContract.copyFor(
        entry.value,
        retryAfterSeconds: entry.key == 429 ? 12 : 0,
      );
      expect(
        semantic.userRecoveryGroup,
        entry.value,
        reason: 'HTTP ${entry.key}',
      );
      expect(semantic.title, copy.title, reason: 'HTTP ${entry.key}');
      expect(semantic.message, copy.message, reason: 'HTTP ${entry.key}');
      expect(
        semantic.primaryAction?.type,
        copy.action.type,
        reason: 'HTTP ${entry.key}',
      );
      expect(
        semantic.primaryAction?.availableAfterSeconds ?? 0,
        entry.key == 429 ? 12 : 0,
      );
    }
  });

  testWidgets('只有已确认且存在官方入口时才展示立即更新语义', (tester) async {
    final context = await pumpContext(tester);
    final unverified = UiErrorSemanticResolver.resolve(
      context,
      error: Exception('minimum version mismatch'),
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
    final verified = UiErrorSemanticResolver.resolve(
      context,
      error: Exception('minimum version mismatch'),
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
      verifiedUpdateAvailable: true,
    );

    expect(unverified.userRecoveryGroup, AppUserRecoveryGroup.reloadLater);
    expect(unverified.title, SearchText.recoveryReloadLaterTitle);
    expect(unverified.message, SearchText.recoveryReloadLaterMessage);
    expect(verified.userRecoveryGroup, AppUserRecoveryGroup.updateApp);
    expect(verified.primaryAction?.type, UiErrorActionType.openUpdate);
    expect(verified.primaryAction?.label, SearchText.recoveryUpdateAppAction);
  });

  // 错误展示载体：守护 error-permission-display-semantics L3 spec。
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
        error: CloudException(
          type: CloudErrorType.network,
          message: 'network',
          runtimeFailure: testRuntimeFailure(
            code: 'APP.NETWORK.offline',
            kind: RuntimeFailureKind.network,
            nature: RuntimeFailureNature.transient,
          ),
        ),
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

    testWidgets('规则1b form scope → formInlineCard', (tester) async {
      final semantic = await resolveCase(
        tester,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.form,
      );
      expect(semantic.presentation, UiErrorPresentation.formInlineCard);
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
