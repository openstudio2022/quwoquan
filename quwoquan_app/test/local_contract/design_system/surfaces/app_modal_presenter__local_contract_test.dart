import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_surface.dart';

void main() {
  const panelKey = ValueKey<String>('presenter-bottom-panel');
  const closeKey = ValueKey<String>('presenter-dialog-close');

  Future<BuildContext> pumpHost(WidgetTester tester) async {
    late BuildContext hostContext;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) {
            hostContext = context;
            return const Scaffold(body: SizedBox.expand());
          },
        ),
      ),
    );
    return hostContext;
  }

  testWidgets('贴底弹窗亮度层原地 fade，不随面板 slide', (tester) async {
    final host = await pumpHost(tester);

    showAppBottomModal<void>(
      context: host,
      builder: (context) => AppBottomModalSurface(
        onDismiss: () => Navigator.of(context).pop(),
        panelKey: panelKey,
        child: const SizedBox(height: 120),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 120));

    expect(find.byKey(TestKeys.appModalBrightnessLayer), findsOneWidget);
    expect(find.byKey(panelKey), findsOneWidget);
    expect(
      find.ancestor(
        of: find.byKey(TestKeys.appModalBrightnessLayer),
        matching: find.byKey(TestKeys.appBottomModalSlideTransition),
      ),
      findsNothing,
    );
    expect(
      find.ancestor(
        of: find.byKey(panelKey),
        matching: find.byKey(TestKeys.appBottomModalSlideTransition),
      ),
      findsOneWidget,
    );

    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();
    expect(find.byKey(TestKeys.appModalBrightnessLayer), findsNothing);
    expect(find.byKey(panelKey), findsNothing);
  });

  testWidgets('Cupertino dialog 关闭后恢复底层亮度', (tester) async {
    final host = await pumpHost(tester);
    Object? result = 'unset';

    showAppCupertinoDialog<bool>(
      context: host,
      builder: (context) => CupertinoAlertDialog(
        title: const Text('确认'),
        actions: [
          CupertinoDialogAction(
            key: closeKey,
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('好'),
          ),
        ],
      ),
    ).then((value) => result = value);
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.appModalBrightnessLayer), findsOneWidget);
    expect(find.text('确认'), findsOneWidget);

    await tester.tap(find.byKey(closeKey));
    await tester.pumpAndSettle();
    expect(result, isTrue);
    expect(find.byKey(TestKeys.appModalBrightnessLayer), findsNothing);
    expect(find.text('确认'), findsNothing);
  });
}
