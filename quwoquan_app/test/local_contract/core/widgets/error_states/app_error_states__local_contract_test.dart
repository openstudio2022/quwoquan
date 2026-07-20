import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/telemetry/app_page_experience_tracker.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

void main() {
  testWidgets('AppPageErrorState 使用柔和整页空态和再试一次动作', (tester) async {
    var retryCount = 0;
    await tester.pumpWidget(
      CupertinoApp(
        home: AppPageErrorState(
          semantic: const UiErrorSemantic(
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
            title: UITextConstants.temporarilyUnavailable,
            message: UITextConstants.checkNetworkAndTryAgain,
            primaryAction: UiErrorAction(
              type: UiErrorActionType.retry,
              label: UITextConstants.tryAgain,
            ),
          ),
          onAction: (_) async => retryCount++,
        ),
      ),
    );

    expect(find.text(UITextConstants.temporarilyUnavailable), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('app-page-error-close-button')),
      findsNothing,
    );
    expect(find.text(UITextConstants.back), findsNothing);
    expect(find.text(UITextConstants.tryAgain), findsOneWidget);
    expect(find.text(UITextConstants.loadFailed), findsNothing);
    expect(find.text(UITextConstants.retry), findsNothing);
    expect(UITextConstants.checkNetworkAndTryAgain, isNot(contains('再试一次')));
    expect(UITextConstants.checkNetworkAndTryAgain, isNot(contains('稍后')));
    final defaultText = tester.widget<DefaultTextStyle>(
      find
          .ancestor(
            of: find.text(UITextConstants.temporarilyUnavailable),
            matching: find.byType(DefaultTextStyle),
          )
          .first,
    );
    expect(defaultText.style.decoration, TextDecoration.none);

    await tester.tap(find.text(UITextConstants.tryAgain));
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
            title: UITextConstants.temporarilyUnavailable,
            message: UITextConstants.checkNetworkAndTryAgain,
            primaryAction: UiErrorAction(
              type: UiErrorActionType.retry,
              label: UITextConstants.tryAgain,
            ),
          ),
        ),
      ),
    );

    expect(find.text(UITextConstants.back), findsNothing);
    expect(find.byIcon(CupertinoIcons.xmark), findsNothing);
    expect(find.text(UITextConstants.tryAgain), findsOneWidget);
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
            title: UITextConstants.temporarilyUnavailable,
            message: UITextConstants.checkNetworkAndTryAgain,
            sourceCode: 'CONTENT.SYSTEM.read_unavailable',
            sourceSurfaceId: 'home_feed',
            recoveryAction: RuntimeRecoveryAction.retry,
            primaryAction: UiErrorAction(
              type: UiErrorActionType.retry,
              label: UITextConstants.tryAgain,
            ),
          ),
          onAction: (_) async {},
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

    await tester.tap(find.text(UITextConstants.tryAgain));
    await tester.pumpAndSettle();

    final outcomes = recorder.records
        .where((payload) => payload.eventType == 'page_error_outcome')
        .map((payload) => payload.extensions['result'])
        .toList(growable: false);
    expect(outcomes, <Object?>['shown', 'recovery_started', 'recovered']);
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
            title: UITextConstants.temporarilyUnavailable,
            message: UITextConstants.checkNetworkAndTryAgain,
            sourceSurfaceId: 'home_feed',
            recoveryAction: RuntimeRecoveryAction.retry,
            primaryAction: UiErrorAction(
              type: UiErrorActionType.retry,
              label: UITextConstants.tryAgain,
            ),
          ),
          onAction: (_) async => retryCount += 1,
        ),
      ),
    );
    await tester.pump();

    await tester.tap(find.text(UITextConstants.tryAgain));
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
            title: UITextConstants.commentLoadFailedTitle,
            message: UITextConstants.pageLoadFailedMessage,
            primaryAction: UiErrorAction(
              type: UiErrorActionType.retry,
              label: UITextConstants.tryAgain,
            ),
          ),
        ),
      ),
    );

    expect(find.byType(AppSectionErrorState), findsOneWidget);
    expect(find.byType(AppSectionErrorCard), findsNothing);
    expect(find.text(UITextConstants.commentLoadFailedTitle), findsOneWidget);
    expect(UITextConstants.pageLoadFailedMessage, isNot(contains('再试一次')));
    expect(UITextConstants.pageLoadFailedMessage, isNot(contains('稍后')));
    expect(find.text(UITextConstants.tryAgain), findsOneWidget);
  });

  testWidgets('AppFormErrorCard 使用透明统一错误行并提供 44dp 恢复动作', (tester) async {
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
    expect(find.byIcon(CupertinoIcons.exclamationmark_circle), findsOneWidget);
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

  testWidgets('AppInlineFieldError 使用统一错误色和 16px 图标', (tester) async {
    await tester.pumpWidget(
      const CupertinoApp(home: AppInlineFieldError(message: '请输入正确的手机号')),
    );

    final text = tester.widget<Text>(find.text('请输入正确的手机号'));
    final context = tester.element(find.text('请输入正确的手机号'));
    expect(text.style?.color, AppColors.errorForeground(context));
    expect(text.style?.fontSize, AppTypography.inlineError);
    final icon = tester.widget<Icon>(
      find.byIcon(CupertinoIcons.exclamationmark_circle),
    );
    expect(icon.size, AppSpacing.inlineErrorIconSize);
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
            title: UITextConstants.temporarilyUnavailable,
            message: UITextConstants.checkNetworkAndTryAgain,
            appearanceMode: UiErrorAppearanceMode.light,
          ),
        ),
      ),
    );

    final titleText = tester.widget<Text>(
      find.text(UITextConstants.temporarilyUnavailable),
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
            title: UITextConstants.temporarilyUnavailable,
            message: UITextConstants.refreshSoftFailed,
            presentation: UiErrorPresentation.transientNotice,
          ),
        ),
      ),
    );

    expect(find.text(UITextConstants.refreshSoftFailed), findsOneWidget);
    expect(find.text(UITextConstants.tryAgain), findsNothing);
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
            message: UITextConstants.appendSoftFailed,
            presentation: UiErrorPresentation.appendFooter,
            primaryAction: UiErrorAction(
              type: UiErrorActionType.retry,
              label: UITextConstants.tryAgain,
            ),
          ),
          onAction: (_) async => retryCount++,
        ),
      ),
    );

    expect(find.text(UITextConstants.appendSoftFailed), findsOneWidget);
    expect(find.text(UITextConstants.loadFailed), findsNothing);

    await tester.tap(find.text(UITextConstants.appendSoftFailed));
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
    expect(find.text(UITextConstants.gotIt), findsOneWidget);
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
