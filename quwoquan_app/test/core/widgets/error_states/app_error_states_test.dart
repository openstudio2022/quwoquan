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
      findsOneWidget,
    );
    final closeButton = tester.widget<CupertinoButton>(
      find.byKey(const ValueKey<String>('app-page-error-close-button')),
    );
    expect(closeButton.child, isA<SizedBox>());
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
    await tester.tap(
      find.byKey(const ValueKey<String>('app-page-error-close-button')),
    );
    await tester.pump();
  });

  testWidgets('AppPageErrorState 的返回动作使用中性色胶囊按钮', (tester) async {
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

    expect(find.text(UITextConstants.back), findsOneWidget);
    final backButtonDecoration = tester.widget<DecoratedBox>(
      find
          .ancestor(
            of: find.text(UITextConstants.back),
            matching: find.byWidgetPredicate(
              (widget) =>
                  widget is DecoratedBox &&
                  widget.decoration is BoxDecoration &&
                  (widget.decoration as BoxDecoration).border != null,
            ),
          )
          .first,
    );
    final decoration = backButtonDecoration.decoration as BoxDecoration;
    expect(decoration.border, isNotNull);
    final backButtonSize = tester.getSize(
      find
          .ancestor(
            of: find.text(UITextConstants.back),
            matching: find.byType(CupertinoButton),
          )
          .first,
    );
    final retryButtonSize = tester.getSize(
      find
          .ancestor(
            of: find.text(UITextConstants.tryAgain),
            matching: find.byType(CupertinoButton),
          )
          .first,
    );
    expect(backButtonSize.width, retryButtonSize.width);
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
}
