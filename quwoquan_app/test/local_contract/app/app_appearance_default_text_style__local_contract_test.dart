import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/startup_welcome_appearance.dart';
import 'package:quwoquan_app/quwoquan_app_shell.dart';

void main() {
  testWidgets('App 外观层清除 fallback DefaultTextStyle 黄色下划线', (tester) async {
    const textKey = ValueKey<String>('appearance-text');

    await tester.pumpWidget(
      MaterialApp(
        home: DefaultTextStyle(
          style: const TextStyle(
            decoration: TextDecoration.underline,
            decorationColor: Colors.yellow,
          ),
          child: Builder(
            builder: (context) => wrapWithQuwoquanAppAppearance(
              context: context,
              snapshot: startupWelcomeAppearanceSnapshot(),
              child: const Text(
                '交集配对',
                key: textKey,
                style: TextStyle(fontSize: 18),
              ),
            ),
          ),
        ),
      ),
    );

    final style = DefaultTextStyle.of(
      tester.element(find.byKey(textKey)),
    ).style;
    expect(style.decoration, TextDecoration.none);
  });
}
