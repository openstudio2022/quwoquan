import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/widgets/app_list_page_semantics.dart';

void main() {
  testWidgets('AppSegmentedChoiceBar is tap-only and ignores horizontal drag', (
    tester,
  ) async {
    var selected = 'fans';

    await tester.pumpWidget(
      CupertinoApp(
        home: StatefulBuilder(
          builder: (context, setState) {
            return Center(
              child: AppSegmentedChoiceBar<String>(
                items: const <AppSegmentedChoiceItem<String>>[
                  AppSegmentedChoiceItem<String>(value: 'fans', label: 'Fans'),
                  AppSegmentedChoiceItem<String>(
                    value: 'following',
                    label: 'Following',
                  ),
                  AppSegmentedChoiceItem<String>(
                    value: 'circles',
                    label: 'Circles',
                  ),
                ],
                selectedValue: selected,
                onChanged: (value) => setState(() => selected = value),
              ),
            );
          },
        ),
      ),
    );

    await tester.drag(
      find.byType(AppSegmentedChoiceBar<String>),
      const Offset(-160, 0),
    );
    await tester.pumpAndSettle();
    expect(selected, 'fans');

    await tester.tap(find.text('Following'));
    await tester.pumpAndSettle();
    expect(selected, 'following');
  });

  testWidgets('AppSegmentedChoiceBar renders in dark theme and narrow width', (
    tester,
  ) async {
    await tester.pumpWidget(
      CupertinoApp(
        theme: const CupertinoThemeData(brightness: Brightness.dark),
        home: Center(
          child: SizedBox(
            width: 160,
            child: AppSegmentedChoiceBar<String>(
              items: <AppSegmentedChoiceItem<String>>[
                AppSegmentedChoiceItem<String>(value: 'a', label: 'A'),
                AppSegmentedChoiceItem<String>(value: 'b', label: 'B'),
              ],
              selectedValue: 'a',
              onChanged: _ignoreString,
            ),
          ),
        ),
      ),
    );

    expect(tester.takeException(), isNull);
    expect(find.text('A'), findsOneWidget);
    expect(find.text('B'), findsOneWidget);
  });
}

void _ignoreString(String _) {}
