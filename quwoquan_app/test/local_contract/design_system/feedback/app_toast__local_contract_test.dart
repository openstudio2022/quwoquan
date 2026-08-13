// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-001
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';

const _toneDot = ValueKey<String>('app-toast-tone-dot');

Widget _host(void Function(BuildContext context) onShow) {
  return CupertinoApp(
    home: Builder(
      builder: (context) => CupertinoPageScaffold(
        child: Center(
          child: CupertinoButton(
            onPressed: () => onShow(context),
            child: const Text('show-toast'),
          ),
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('中性 toast 保持纯文字胶囊，无 tone 强调', (tester) async {
    await tester.pumpWidget(
      _host((context) => AppToast.show(context, FoundationText.loading)),
    );
    await tester.tap(find.text('show-toast'));
    await tester.pump();

    expect(find.text(FoundationText.loading), findsOneWidget);
    expect(find.byKey(_toneDot), findsNothing);
    expect(find.byType(Icon), findsNothing);

    await tester.pump(const Duration(seconds: 4));
    expect(find.text(FoundationText.loading), findsNothing);
  });

  testWidgets('错误语义 toast 前置 tone 圆点且宣告 liveRegion', (tester) async {
    const semantic = UiErrorSemantic(
      category: UiErrorCategory.backgroundAction,
      scope: UiErrorScope.global,
      title: '',
      message: SearchText.recoveryReloadLaterMessage,
      tone: UiErrorTone.critical,
      presentation: UiErrorPresentation.transientNotice,
    );
    await tester.pumpWidget(
      _host((context) => AppToast.showError(context, semantic)),
    );
    await tester.tap(find.text('show-toast'));
    await tester.pump();

    expect(find.text(SearchText.recoveryReloadLaterMessage), findsOneWidget);
    final dot = tester.widget<Container>(find.byKey(_toneDot));
    final decoration = dot.decoration! as BoxDecoration;
    expect(decoration.shape, BoxShape.circle);
    // critical → 深底可读的错误前景；非文本指示对深色胶囊 ≥3:1。
    expect(decoration.color, AppColors.errorForegroundDark);
    expect(
      (decoration.color!.computeLuminance() + 0.05) / 0.05,
      greaterThanOrEqualTo(3.0),
    );
    // 仍不引入任何图标（惊叹号禁令由 ratchet 门禁静态保障）。
    expect(find.byType(Icon), findsNothing);

    final semantics = tester.getSemantics(
      find.text(SearchText.recoveryReloadLaterMessage),
    );
    expect(semantics.flagsCollection.isLiveRegion, isTrue);

    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('中性 tone 的错误语义经 showError 仍以警示呈现', (tester) async {
    const semantic = UiErrorSemantic(
      category: UiErrorCategory.backgroundAction,
      scope: UiErrorScope.global,
      title: '',
      message: SearchText.recoveryServiceUnavailableMessage,
      presentation: UiErrorPresentation.transientNotice,
    );
    await tester.pumpWidget(
      _host((context) => AppToast.showError(context, semantic)),
    );
    await tester.tap(find.text('show-toast'));
    await tester.pump();

    final dot = tester.widget<Container>(find.byKey(_toneDot));
    expect((dot.decoration! as BoxDecoration).color, AppColors.warning);

    await tester.pump(const Duration(seconds: 4));
  });
}
