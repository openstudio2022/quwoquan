import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

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
    expect(find.text(UITextConstants.tryAgain), findsOneWidget);
  });

  testWidgets('AppFormErrorCard 就近展示、播报一次并提供 44dp 恢复动作', (tester) async {
    var retryCount = 0;
    await tester.pumpWidget(
      CupertinoApp(
        home: AppFormErrorCard(
          semantic: const UiErrorSemantic(
            category: UiErrorCategory.submit,
            scope: UiErrorScope.form,
            title: '未能获取验证码',
            message: '验证码发送失败，请重试',
            presentation: UiErrorPresentation.formInlineCard,
            tone: UiErrorTone.caution,
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

  testWidgets('AppInlineFieldError 使用破坏色并建立 live region', (tester) async {
    await tester.pumpWidget(
      const CupertinoApp(home: AppInlineFieldError(message: '请输入正确的手机号')),
    );

    final text = tester.widget<Text>(find.text('请输入正确的手机号'));
    expect(text.style?.color, isNotNull);
    final semantics = tester.widgetList<Semantics>(find.byType(Semantics));
    expect(semantics.any((node) => node.properties.liveRegion == true), isTrue);
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
