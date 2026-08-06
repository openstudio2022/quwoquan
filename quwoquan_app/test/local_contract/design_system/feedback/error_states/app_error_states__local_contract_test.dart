import 'dart:async';
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_appearance.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_page_experience_tracker.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

Finder _decorativeCircleWithin(Finder ancestor) {
  return find.descendant(
    of: ancestor,
    matching: find.byWidgetPredicate((widget) {
      if (widget is! Container || widget.decoration is! BoxDecoration) {
        return false;
      }
      return (widget.decoration! as BoxDecoration).shape == BoxShape.circle;
    }),
  );
}

void main() {
  testWidgets('AppPageErrorState 使用柔和整页空态和重新加载动作', (tester) async {
    var retryCount = 0;
    await tester.pumpWidget(
      CupertinoApp(
        home: AppPageErrorState(
          semantic: const UiErrorSemantic(
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
            title: SearchText.recoveryReloadLaterTitle,
            message: SearchText.recoveryReloadLaterMessage,
            sourceCode: 'CONTENT.SYSTEM.required_dependency_unavailable',
            primaryAction: UiErrorAction(
              type: UiErrorActionType.retry,
              label: SearchText.reload,
            ),
          ),
          onRecovery: (_) async {
            retryCount += 1;
            return UiRecoveryOutcome.recovered;
          },
        ),
      ),
    );

    expect(find.text(SearchText.recoveryReloadLaterTitle), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('app-page-error-close-button')),
      findsNothing,
    );
    expect(find.text(ContentText.back), findsNothing);
    expect(find.text(SearchText.reload), findsOneWidget);
    expect(find.text(FoundationText.loadFailed), findsNothing);
    expect(find.text(FoundationText.retry), findsNothing);
    final defaultText = tester.widget<DefaultTextStyle>(
      find
          .ancestor(
            of: find.text(SearchText.recoveryReloadLaterTitle),
            matching: find.byType(DefaultTextStyle),
          )
          .first,
    );
    expect(defaultText.style.decoration, TextDecoration.none);

    await tester.tap(find.text(SearchText.reload));
    await tester.pump();
    expect(retryCount, 1);
  });

  testWidgets('AppPageErrorState 不自动注入返回或关闭导航', (tester) async {
    await tester.pumpWidget(
      const CupertinoApp(
        home: AppPageErrorState(
          semantic: UiErrorSemantic(
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
            title: SearchText.recoveryReloadLaterTitle,
            message: SearchText.recoveryReloadLaterMessage,
            primaryAction: UiErrorAction(
              type: UiErrorActionType.retry,
              label: SearchText.reload,
            ),
          ),
        ),
      ),
    );

    expect(find.text(ContentText.back), findsNothing);
    expect(find.byIcon(CupertinoIcons.xmark), findsNothing);
    expect(find.text(SearchText.reload), findsNothing);
  });

  testWidgets('AppPageErrorState 用户树不展示图标或技术诊断', (tester) async {
    await tester.pumpWidget(
      const CupertinoApp(
        home: AppPageErrorState(
          semantic: UiErrorSemantic(
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
            title: SearchText.recoveryReloadLaterTitle,
            message: SearchText.recoveryReloadLaterMessage,
            sourceCode: 'APP.NETWORK.connection_refused',
            sourceOperationId: 'GetFeed',
            sourceRouteId: '/content/feed',
            requestId: 'request-1',
            traceId: 'trace-1',
          ),
        ),
      ),
    );

    expect(find.byType(Icon), findsNothing);
    expect(find.textContaining('GetFeed'), findsNothing);
    expect(find.textContaining('APP.NETWORK.connection_refused'), findsNothing);
    expect(find.textContaining('/content/feed'), findsNothing);
    expect(find.textContaining('request-1'), findsNothing);
    expect(find.textContaining('trace-1'), findsNothing);
    final semantics = tester.getSemantics(
      find.text(SearchText.recoveryReloadLaterTitle),
    );
    expect(semantics.flagsCollection.isLiveRegion, isTrue);
  });

  testWidgets('429 主操作在 Retry-After 倒计时结束前不可触发', (tester) async {
    var retryCount = 0;
    await tester.pumpWidget(
      CupertinoApp(
        home: AppPageErrorState(
          semantic: const UiErrorSemantic(
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
            title: SearchText.recoveryWaitThenReloadTitle,
            message: '操作有点频繁，2 秒后可以重新加载。',
            sourceCode: 'CONTENT.USER.rate_limited',
            primaryAction: UiErrorAction(
              type: UiErrorActionType.retry,
              label: SearchText.reload,
              availableAfterSeconds: 2,
            ),
          ),
          onRecovery: (_) async {
            retryCount += 1;
            return UiRecoveryOutcome.recovered;
          },
        ),
      ),
    );

    expect(find.text('2 秒后再试'), findsOneWidget);
    await tester.tap(find.text('2 秒后再试'));
    expect(retryCount, 0);
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('1 秒后再试'), findsOneWidget);
    await tester.pump(const Duration(seconds: 1));
    expect(find.text(SearchText.reload), findsOneWidget);
    await tester.tap(find.text(SearchText.reload));
    await tester.pump();
    expect(retryCount, 1);
  });

  testWidgets('AppPageErrorState 统一结算错误 TTI 与恢复 outcome', (tester) async {
    final pageContext = AppPageContextStore.instance..setPageName('home');
    final recorder = _CapturingTelemetryRecorder();
    final tracker = AppPageExperienceTracker(pageContextStore: pageContext)
      ..attachReporter(recorder)
      ..beginPageVisit(
        pageName: 'home',
        pageVisitId: 'visit-error-1',
        openedAt: DateTime.now(),
      );

    await tester.pumpWidget(
      CupertinoApp(
        home: AppPageErrorState(
          experienceTracker: tracker,
          semantic: const UiErrorSemantic(
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
            title: SearchText.recoveryReloadLaterTitle,
            message: SearchText.recoveryReloadLaterMessage,
            sourceCode: 'CONTENT.SYSTEM.read_unavailable',
            sourceSurfaceId: 'home_feed',
            recoveryAction: RuntimeRecoveryAction.retry,
            primaryAction: UiErrorAction(
              type: UiErrorActionType.retry,
              label: SearchText.reload,
            ),
          ),
          onRecovery: (_) async => UiRecoveryOutcome.recovered,
        ),
      ),
    );
    await tester.pump();

    expect(
      recorder.records.map((payload) => payload.eventType),
      containsAll(<String>['page_first_usable', 'page_error_outcome']),
    );
    final shown = recorder.records.lastWhere(
      (payload) =>
          payload.eventType == 'page_error_outcome' &&
          payload.extensions['result'] == 'shown',
    );
    expect(shown.extensions['surfaceId'], 'home_feed');
    expect(shown.extensions['errorCode'], 'CONTENT.SYSTEM.read_unavailable');

    await tester.tap(find.text(SearchText.reload));
    await tester.pumpAndSettle();

    final outcomes = recorder.records
        .where((payload) => payload.eventType == 'page_error_outcome')
        .map((payload) => payload.extensions['result'])
        .toList(growable: false);
    expect(outcomes, <Object?>['shown', 'recovery_started', 'recovered']);
  });

  testWidgets('typed stillBlocked 是正常终态且不进入 bootstrap zone', (tester) async {
    final pageContext = AppPageContextStore.instance..setPageName('home');
    final recorder = _CapturingTelemetryRecorder();
    final tracker = AppPageExperienceTracker(pageContextStore: pageContext)
      ..attachReporter(recorder)
      ..beginPageVisit(
        pageName: 'home',
        pageVisitId: 'visit-still-blocked',
        openedAt: DateTime.now(),
      );

    await tester.pumpWidget(
      CupertinoApp(
        home: AppPageErrorState(
          experienceTracker: tracker,
          semantic: const UiErrorSemantic(
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
            title: SearchText.recoveryServiceUnavailableTitle,
            message: SearchText.recoveryServiceUnavailableMessage,
            sourceCode: 'CONTENT.SYSTEM.required_dependency_unavailable',
            primaryAction: UiErrorAction(
              type: UiErrorActionType.retry,
              label: SearchText.reload,
            ),
          ),
          onRecovery: (_) async => UiRecoveryOutcome.stillBlocked,
        ),
      ),
    );
    await tester.pump();

    await tester.tap(find.text(SearchText.reload));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(
      find.text(SearchText.recoveryServiceUnavailableTitle),
      findsOneWidget,
    );
    expect(
      recorder.records
          .where((payload) => payload.eventType == 'page_error_outcome')
          .map((payload) => payload.extensions['result']),
      <Object?>['shown', 'recovery_started', 'still_blocked'],
    );
  });

  testWidgets('typed 交接、被新请求接管与取消都记录唯一明确终态', (tester) async {
    const cases = <UiRecoveryOutcome, String>{
      UiRecoveryOutcome.handedOff: 'handed_off',
      UiRecoveryOutcome.superseded: 'superseded',
      UiRecoveryOutcome.cancelled: 'cancelled',
    };

    for (final entry in cases.entries) {
      final recorder = _CapturingTelemetryRecorder();
      final tracker = AppPageExperienceTracker(
        pageContextStore: AppPageContextStore.instance..setPageName('home'),
      )
        ..attachReporter(recorder)
        ..beginPageVisit(
          pageName: 'home',
          pageVisitId: 'visit-${entry.value}',
          openedAt: DateTime.now(),
        );
      await tester.pumpWidget(
        CupertinoApp(
          home: AppPageErrorState(
            key: ValueKey<String>('page-error-${entry.value}'),
            experienceTracker: tracker,
            semantic: const UiErrorSemantic(
              category: UiErrorCategory.pageLoad,
              scope: UiErrorScope.page,
              title: SearchText.recoveryReloadLaterTitle,
              message: SearchText.recoveryReloadLaterMessage,
              sourceCode: 'CONTENT.SYSTEM.read_unavailable',
              primaryAction: UiErrorAction(
                type: UiErrorActionType.retry,
                label: SearchText.reload,
              ),
            ),
            onRecovery: (_) async => entry.key,
          ),
        ),
      );
      await tester.pump();
      await tester.tap(find.text(SearchText.reload));
      await tester.pumpAndSettle();

      expect(
        recorder.records
            .where((payload) => payload.eventType == 'page_error_outcome')
            .map((payload) => payload.extensions['result']),
        <Object?>['shown', 'recovery_started', entry.value],
      );
    }
  });

  testWidgets('未分类恢复回调异常被记录但不重抛', (tester) async {
    final pageContext = AppPageContextStore.instance..setPageName('home');
    final recorder = _CapturingTelemetryRecorder();
    final tracker = AppPageExperienceTracker(pageContextStore: pageContext)
      ..attachReporter(recorder)
      ..beginPageVisit(
        pageName: 'home',
        pageVisitId: 'visit-unexpected-recovery',
        openedAt: DateTime.now(),
      );

    await tester.pumpWidget(
      CupertinoApp(
        home: AppPageErrorState(
          experienceTracker: tracker,
          semantic: const UiErrorSemantic(
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
            title: SearchText.recoveryReloadLaterTitle,
            message: SearchText.recoveryReloadLaterMessage,
            sourceCode: 'CONTENT.SYSTEM.required_dependency_unavailable',
            primaryAction: UiErrorAction(
              type: UiErrorActionType.retry,
              label: SearchText.reload,
            ),
          ),
          onRecovery: (_) async => throw StateError('programming defect'),
        ),
      ),
    );
    await tester.pump();

    await tester.tap(find.text(SearchText.reload));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(
      recorder.records
          .where((payload) => payload.eventType == 'page_error_outcome')
          .map((payload) => payload.extensions['result']),
      <Object?>['shown', 'recovery_started', 'recovery_unexpected_failure'],
    );
  });

  testWidgets('AppPageErrorState 不以遥测持久化阻塞用户恢复动作', (tester) async {
    final pageContext = AppPageContextStore.instance..setPageName('home');
    final recorder = _BlockingTelemetryRecorder();
    final tracker = AppPageExperienceTracker(pageContextStore: pageContext)
      ..attachReporter(recorder)
      ..beginPageVisit(
        pageName: 'home',
        pageVisitId: 'visit-non-blocking-recovery',
        openedAt: DateTime.now(),
      );
    var retryCount = 0;

    await tester.pumpWidget(
      CupertinoApp(
        home: AppPageErrorState(
          experienceTracker: tracker,
          semantic: const UiErrorSemantic(
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
            title: SearchText.recoveryReloadLaterTitle,
            message: SearchText.recoveryReloadLaterMessage,
            sourceCode: 'CONTENT.SYSTEM.read_unavailable',
            sourceSurfaceId: 'home_feed',
            recoveryAction: RuntimeRecoveryAction.retry,
            primaryAction: UiErrorAction(
              type: UiErrorActionType.retry,
              label: SearchText.reload,
            ),
          ),
          onRecovery: (_) async {
            retryCount += 1;
            return UiRecoveryOutcome.recovered;
          },
        ),
      ),
    );
    await tester.pump();

    await tester.tap(find.text(SearchText.reload));
    await tester.pump();

    expect(retryCount, 1);
    expect(
      recorder.records
          .where((payload) => payload.eventType == 'page_error_outcome')
          .map((payload) => payload.extensions['result']),
      <Object?>['shown'],
    );

    recorder.release.complete();
    await tester.pumpAndSettle();

    expect(
      recorder.records
          .where((payload) => payload.eventType == 'page_error_outcome')
          .map((payload) => payload.extensions['result']),
      <Object?>['shown', 'recovery_started', 'recovered'],
    );
  });

  testWidgets('AppSectionErrorState 使用无卡片外框的区块阻塞空态', (tester) async {
    await tester.pumpWidget(
      const CupertinoApp(
        home: AppSectionErrorState(
          semantic: UiErrorSemantic(
            category: UiErrorCategory.sectionLoad,
            scope: UiErrorScope.section,
            title: SearchText.recoveryReloadLaterTitle,
            message: SearchText.recoveryReloadLaterMessage,
            primaryAction: UiErrorAction(
              type: UiErrorActionType.retry,
              label: SearchText.reload,
            ),
          ),
        ),
      ),
    );

    expect(find.byType(AppSectionErrorState), findsOneWidget);
    expect(find.byType(AppSectionErrorCard), findsNothing);
    expect(find.text(SearchText.recoveryReloadLaterTitle), findsOneWidget);
    expect(find.text(SearchText.reload), findsNothing);
  });

  testWidgets('AppFormErrorCard 使用无图标错误行并保留 44dp 恢复动作', (tester) async {
    var retryCount = 0;
    await tester.pumpWidget(
      CupertinoApp(
        home: AppFormErrorCard(
          semantic: const UiErrorSemantic(
            category: UiErrorCategory.submit,
            scope: UiErrorScope.form,
            title: '',
            message: '验证码发送失败，请重试',
            presentation: UiErrorPresentation.formInlineCard,
            primaryAction: UiErrorAction(
              type: UiErrorActionType.retry,
              label: '重新获取',
            ),
          ),
          onAction: (_) async => retryCount++,
        ),
      ),
    );

    final semantics = tester.widgetList<Semantics>(find.byType(Semantics));
    expect(semantics.any((node) => node.properties.liveRegion == true), isTrue);
    expect(find.byType(Icon), findsNothing);
    final message = tester.widget<Text>(find.text('验证码发送失败，请重试'));
    expect(message.style?.fontSize, AppTypography.inlineError);
    expect(message.style?.fontWeight, AppTypography.inlineErrorWeight);
    expect(
      message.style?.color,
      AppColors.errorForeground(tester.element(find.text('验证码发送失败，请重试'))),
    );
    expect(
      tester.getSize(find.widgetWithText(CupertinoButton, '重新获取')).height,
      greaterThanOrEqualTo(AppSpacing.minInteractiveSize),
    );
    await tester.tap(find.text('重新获取'));
    await tester.pump();
    expect(retryCount, 1);
  });

  testWidgets('AppFormErrorCard compact 只展示单条说明且不复制动作', (tester) async {
    await tester.pumpWidget(
      const CupertinoApp(
        home: AppFormErrorCard(
          density: AppFormErrorCardDensity.compact,
          semantic: UiErrorSemantic(
            category: UiErrorCategory.submit,
            scope: UiErrorScope.form,
            title: '暂时无法使用此方式',
            message: '本机号码登录暂不可用，请使用短信验证码',
            presentation: UiErrorPresentation.formInlineCard,
            tone: UiErrorTone.caution,
          ),
        ),
      ),
    );

    expect(find.text('本机号码登录暂不可用，请使用短信验证码'), findsOneWidget);
    expect(find.text('暂时无法使用此方式'), findsNothing);
    expect(find.byType(CupertinoButton), findsNothing);
    final semantics = tester.widgetList<Semantics>(find.byType(Semantics));
    expect(semantics.any((node) => node.properties.liveRegion == true), isTrue);
  });

  testWidgets('AppInlineFieldError 使用统一错误色且不展示错误图标', (tester) async {
    await tester.pumpWidget(
      const CupertinoApp(home: AppInlineFieldError(message: '请输入正确的手机号')),
    );

    final text = tester.widget<Text>(find.text('请输入正确的手机号'));
    final context = tester.element(find.text('请输入正确的手机号'));
    expect(text.style?.color, AppColors.errorForeground(context));
    expect(text.style?.fontSize, AppTypography.inlineError);
    expect(find.byType(Icon), findsNothing);
    final semantics = tester.widgetList<Semantics>(find.byType(Semantics));
    expect(semantics.any((node) => node.properties.liveRegion == true), isTrue);
  });

  testWidgets('窄屏内联错误最多显示两行并使用深色 token', (tester) async {
    await tester.pumpWidget(
      const CupertinoApp(
        theme: CupertinoThemeData(brightness: Brightness.dark),
        home: MediaQuery(
          data: MediaQueryData(size: Size(320, 640)),
          child: AppInlineFieldError(message: '登录服务暂不可用，请使用其他方式登录并确认网络连接后再继续'),
        ),
      ),
    );

    final text = tester.widget<Text>(
      find.text('登录服务暂不可用，请使用其他方式登录并确认网络连接后再继续'),
    );
    expect(text.maxLines, 2);
    final color = text.style!.color! as CupertinoDynamicColor;
    expect(color.darkColor, const Color(0xFFFF6B6B));
  });

  testWidgets('AppPageErrorState 按 semantic appearanceMode 局部渲染', (
    tester,
  ) async {
    await tester.pumpWidget(
      const CupertinoApp(
        theme: CupertinoThemeData(brightness: Brightness.dark),
        home: AppPageErrorState(
          semantic: UiErrorSemantic(
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
            title: FoundationText.temporarilyUnavailable,
            message: FoundationText.checkNetworkAndTryAgain,
            appearanceMode: UiErrorAppearanceMode.light,
          ),
        ),
      ),
    );

    final titleText = tester.widget<Text>(
      find.text(FoundationText.temporarilyUnavailable),
    );
    final titleColor = titleText.style!.color!;
    expect(titleColor.computeLuminance(), lessThan(0.5));

    final backgroundBox = tester.widget<ColoredBox>(
      find
          .descendant(
            of: find.byType(AppPageErrorState),
            matching: find.byType(ColoredBox),
          )
          .first,
    );
    expect(backgroundBox.color.computeLuminance(), greaterThan(0.5));
  });

  testWidgets('AppTransientErrorNotice 渲染刷新失败轻提示', (tester) async {
    await tester.pumpWidget(
      const CupertinoApp(
        home: AppTransientErrorNotice(
          semantic: UiErrorSemantic(
            category: UiErrorCategory.backgroundAction,
            scope: UiErrorScope.section,
            title: FoundationText.temporarilyUnavailable,
            message: FoundationText.refreshSoftFailed,
            presentation: UiErrorPresentation.transientNotice,
          ),
        ),
      ),
    );

    expect(find.text(FoundationText.refreshSoftFailed), findsOneWidget);
    expect(find.text(ContentText.tryAgain), findsNothing);
    expect(
      _decorativeCircleWithin(find.byType(AppTransientErrorNotice)),
      findsNothing,
    );
  });

  testWidgets('区块错误与权限 gate 不展示装饰性前导圆点并保留动作', (tester) async {
    var actionCount = 0;
    const semantic = UiErrorSemantic(
      category: UiErrorCategory.sectionLoad,
      scope: UiErrorScope.section,
      title: SearchText.recoveryReloadLaterTitle,
      message: SearchText.recoveryReloadLaterMessage,
      primaryAction: UiErrorAction(
        type: UiErrorActionType.retry,
        label: SearchText.reload,
      ),
    );
    await tester.pumpWidget(
      CupertinoApp(
        home: Column(
          children: <Widget>[
            AppSectionErrorCard(
              semantic: semantic,
              onAction: (_) async => actionCount += 1,
            ),
            AppInlineGateState(
              semantic: semantic,
              onAction: (_) async => actionCount += 1,
            ),
          ],
        ),
      ),
    );

    expect(
      _decorativeCircleWithin(find.byType(AppSectionErrorCard)),
      findsNothing,
    );
    expect(
      _decorativeCircleWithin(find.byType(AppInlineGateState)),
      findsNothing,
    );
    expect(find.text(SearchText.reload), findsNWidgets(2));
    await tester.tap(find.text(SearchText.reload).first);
    await tester.pump();
    expect(actionCount, 1);
  });

  testWidgets('AppListAppendErrorFooter 渲染分页失败轻提示并支持点击重试', (tester) async {
    var retryCount = 0;
    await tester.pumpWidget(
      CupertinoApp(
        home: AppListAppendErrorFooter(
          semantic: const UiErrorSemantic(
            category: UiErrorCategory.listAppend,
            scope: UiErrorScope.section,
            title: '继续加载没成功',
            message: FoundationText.appendSoftFailed,
            presentation: UiErrorPresentation.appendFooter,
            primaryAction: UiErrorAction(
              type: UiErrorActionType.retry,
              label: ContentText.tryAgain,
            ),
          ),
          onAction: (_) async => retryCount++,
        ),
      ),
    );

    expect(find.text(FoundationText.appendSoftFailed), findsOneWidget);
    expect(find.text(FoundationText.loadFailed), findsNothing);

    await tester.tap(find.text(FoundationText.appendSoftFailed));
    await tester.pump();
    expect(retryCount, 1);
  });

  testWidgets('AppActionErrorFeedback 无恢复动作时使用标准对话框而非失败 toast', (tester) async {
    await tester.pumpWidget(
      CupertinoApp(
        home: Builder(
          builder: (context) => CupertinoButton(
            onPressed: () {
              AppActionErrorFeedback.show(
                context,
                semantic: const UiErrorSemantic(
                  category: UiErrorCategory.submit,
                  scope: UiErrorScope.dialog,
                  title: '提交未完成',
                  message: '当前内容无法提交。',
                  presentation: UiErrorPresentation.actionDialog,
                ),
              );
            },
            child: const Text('触发失败'),
          ),
        ),
      ),
    );

    await tester.tap(find.text('触发失败'));
    await tester.pumpAndSettle();

    expect(find.byType(CupertinoAlertDialog), findsOneWidget);
    expect(find.text('提交未完成'), findsOneWidget);
    expect(find.text(ContentText.gotIt), findsOneWidget);
  });
}

final class _CapturingTelemetryRecorder implements AppTelemetryRecorder {
  final List<AppTelemetryPayload> records = <AppTelemetryPayload>[];

  @override
  Future<void> clearPendingForLogout() async {}

  @override
  Future<AppTelemetryFlushResult> flush() async =>
      AppTelemetryFlushResult.empty;

  @override
  void onNetworkAvailable() {}

  @override
  Future<AppTelemetryRecordResult> record(
    AppTelemetryPayload payload, {
    String? pageName,
    DateTime? occurredAt,
  }) async {
    records.add(payload);
    return AppTelemetryRecordResult.accepted;
  }
}

final class _BlockingTelemetryRecorder implements AppTelemetryRecorder {
  final List<AppTelemetryPayload> records = <AppTelemetryPayload>[];
  final Completer<void> release = Completer<void>();

  @override
  Future<void> clearPendingForLogout() async {}

  @override
  Future<AppTelemetryFlushResult> flush() async =>
      AppTelemetryFlushResult.empty;

  @override
  void onNetworkAvailable() {}

  @override
  Future<AppTelemetryRecordResult> record(
    AppTelemetryPayload payload, {
    String? pageName,
    DateTime? occurredAt,
  }) async {
    records.add(payload);
    await release.future;
    return AppTelemetryRecordResult.accepted;
  }
}
