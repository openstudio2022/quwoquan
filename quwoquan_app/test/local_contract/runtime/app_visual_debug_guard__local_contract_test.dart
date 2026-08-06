import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/startup/startup_welcome_appearance.dart';
import 'package:quwoquan_app/runtime/di/shell/composition/quwoquan_app_shell.dart';

void main() {
  tearDown(() {
    assert(() {
      debugPaintSizeEnabled = false;
      debugPaintBaselinesEnabled = false;
      debugPaintPointersEnabled = false;
      debugPaintLayerBordersEnabled = false;
      debugRepaintRainbowEnabled = false;
      return true;
    }());
  });

  testWidgets(
    'app appearance wrapper provides Material host and clears debug baselines',
    (tester) async {
      var assertEnabled = false;
      assert(() {
        assertEnabled = true;
        debugPaintBaselinesEnabled = true;
        return true;
      }());
      expect(assertEnabled, isTrue);

      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => wrapWithQuwoquanAppAppearance(
              context: context,
              snapshot: startupWelcomeAppearanceSnapshot(),
              child: const Text('认识实体主页'),
            ),
          ),
        ),
      );

      assert(() {
        expect(debugPaintBaselinesEnabled, isFalse);
        return true;
      }());
      expect(
        find.ancestor(of: find.text('认识实体主页'), matching: find.byType(Material)),
        findsWidgets,
      );
    },
  );
}
