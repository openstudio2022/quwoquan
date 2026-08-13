// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#req-005

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';

/// 轻量错误载体的深浅双模式渲染契约。
///
/// Transient / SectionCard / ListAppendFooter 经 `CupertinoTheme.brightness`
/// 驱动配色；本文件锁定「同一载体在两种模式下色值必须随主题变化」，防止
/// 后续改动把任一载体固定成单一模式的颜色。
void main() {
  const semantic = UiErrorSemantic(
    category: UiErrorCategory.backgroundAction,
    scope: UiErrorScope.section,
    title: SearchText.recoveryServiceUnavailableTitle,
    message: SearchText.recoveryServiceUnavailableMessage,
    primaryAction: UiErrorAction(
      type: UiErrorActionType.retry,
      label: SearchText.reload,
    ),
  );

  Future<void> pumpThemed(
    WidgetTester tester,
    Brightness brightness,
    Widget child,
  ) async {
    await tester.pumpWidget(
      CupertinoApp(
        theme: CupertinoThemeData(brightness: brightness),
        home: CupertinoPageScaffold(child: Center(child: child)),
      ),
    );
  }

  Color textColorOf(WidgetTester tester, String text) {
    final widget = tester.widget<Text>(find.text(text).first);
    return widget.style!.color!;
  }

  testWidgets('AppTransientErrorNotice 背景与文字色随深浅模式变化', (tester) async {
    await pumpThemed(
      tester,
      Brightness.light,
      const AppTransientErrorNotice(semantic: semantic),
    );
    final lightText = textColorOf(
      tester,
      SearchText.recoveryServiceUnavailableMessage,
    );
    final lightBox = tester
        .widget<DecoratedBox>(
          find
              .ancestor(
                of: find.text(SearchText.recoveryServiceUnavailableMessage),
                matching: find.byType(DecoratedBox),
              )
              .first,
        )
        .decoration as BoxDecoration;

    await pumpThemed(
      tester,
      Brightness.dark,
      const AppTransientErrorNotice(semantic: semantic),
    );
    final darkText = textColorOf(
      tester,
      SearchText.recoveryServiceUnavailableMessage,
    );
    final darkBox = tester
        .widget<DecoratedBox>(
          find
              .ancestor(
                of: find.text(SearchText.recoveryServiceUnavailableMessage),
                matching: find.byType(DecoratedBox),
              )
              .first,
        )
        .decoration as BoxDecoration;

    expect(lightText, isNot(darkText));
    expect(lightBox.color, isNot(darkBox.color));
    // 深色模式提高浸染 alpha 以维持可辨识度（0.18 vs 0.08）。
    expect(darkBox.color!.a, greaterThan(lightBox.color!.a));
  });

  testWidgets('AppSectionErrorCard 标题与说明色随深浅模式变化', (tester) async {
    await pumpThemed(
      tester,
      Brightness.light,
      const AppSectionErrorCard(semantic: semantic),
    );
    final lightTitle = textColorOf(
      tester,
      SearchText.recoveryServiceUnavailableTitle,
    );
    final lightMessage = textColorOf(
      tester,
      SearchText.recoveryServiceUnavailableMessage,
    );

    await pumpThemed(
      tester,
      Brightness.dark,
      const AppSectionErrorCard(semantic: semantic),
    );
    final darkTitle = textColorOf(
      tester,
      SearchText.recoveryServiceUnavailableTitle,
    );
    final darkMessage = textColorOf(
      tester,
      SearchText.recoveryServiceUnavailableMessage,
    );

    expect(lightTitle, isNot(darkTitle));
    expect(lightMessage, isNot(darkMessage));
  });

  testWidgets('AppListAppendErrorFooter 文字色随深浅模式变化', (tester) async {
    await pumpThemed(
      tester,
      Brightness.light,
      AppListAppendErrorFooter(semantic: semantic, onAction: (_) async {}),
    );
    final lightText = textColorOf(
      tester,
      SearchText.recoveryServiceUnavailableMessage,
    );

    await pumpThemed(
      tester,
      Brightness.dark,
      AppListAppendErrorFooter(semantic: semantic, onAction: (_) async {}),
    );
    final darkText = textColorOf(
      tester,
      SearchText.recoveryServiceUnavailableMessage,
    );

    expect(lightText, isNot(darkText));
  });

  testWidgets('AppToast 深色模式使用深色胶囊分支且警示圆点保持 token 色', (tester) async {
    late BuildContext hostContext;
    await tester.pumpWidget(
      CupertinoApp(
        theme: const CupertinoThemeData(brightness: Brightness.dark),
        home: Builder(
          builder: (context) {
            hostContext = context;
            return const SizedBox.shrink();
          },
        ),
      ),
    );

    AppToast.showError(hostContext, semantic);
    await tester.pump();

    final dot = tester.widget<Container>(
      find.byKey(const ValueKey<String>('app-toast-tone-dot')),
    );
    final dotColor = (dot.decoration! as BoxDecoration).color!;
    // 警示圆点在深色模式保持 token 色，不随主题褪色。
    expect(dotColor.a, greaterThan(0));

    final capsule = tester
        .widget<Container>(
          find
              .ancestor(
                of: find.byKey(const ValueKey<String>('app-toast-tone-dot')),
                matching: find.byType(Container),
              )
              .last,
        )
        .decoration! as BoxDecoration;
    // 深色模式走 systemGrey6.darkColor 分支，而非浅色模式的纯黑胶囊。
    expect(
      capsule.color,
      CupertinoColors.systemGrey6.darkColor.withValues(alpha: 0.9),
    );

    AppToast.dismiss();
    await tester.pump();
  });
}
