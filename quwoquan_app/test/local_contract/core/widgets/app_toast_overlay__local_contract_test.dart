import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

void main() {
  testWidgets('AppToast.show defers Overlay insert off the build phase', (
    tester,
  ) async {
    var buildNestedToast = false;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) {
              return CupertinoButton(
                onPressed: () {
                  // Nested build-phase insert: show toast while a child builds.
                  showDialog<void>(
                    context: context,
                    builder: (dialogContext) {
                      if (!buildNestedToast) {
                        buildNestedToast = true;
                        AppToast.show(dialogContext, 'deferred-toast');
                      }
                      return const SizedBox.shrink();
                    },
                  );
                },
                child: const Text('open'),
              );
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text('open'));
    await tester.pump();
    // Post-frame insert should land without framework assertion.
    await tester.pump();
    expect(find.text('deferred-toast'), findsOneWidget);
    AppToast.dismiss();
    await tester.pump();
  });
}
