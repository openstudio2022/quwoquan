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
    expect(find.text(UITextConstants.tryAgain), findsOneWidget);
    expect(find.text(UITextConstants.loadFailed), findsNothing);
    expect(find.text(UITextConstants.retry), findsNothing);

    await tester.tap(find.text(UITextConstants.tryAgain));
    await tester.pump();
    expect(retryCount, 1);
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
