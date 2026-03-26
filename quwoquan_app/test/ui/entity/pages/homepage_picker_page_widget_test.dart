import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/entity/mock/homepage_mock_data.dart';
import 'package:quwoquan_app/cloud/services/entity/homepage_models.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_route_models.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_picker_page.dart';

void main() {
  late FlutterExceptionHandler? originalOnError;

  setUp(() {
    HttpOverrides.global = _NoNetworkHttpOverrides();
    originalOnError = FlutterError.onError;
    FlutterError.onError = (details) {
      final message = details.exceptionAsString();
      if (message.contains('HTTP request failed') ||
          message.contains('NetworkImageLoadException')) {
        return;
      }
      originalOnError?.call(details);
    };
  });

  tearDown(() {
    HttpOverrides.global = null;
    FlutterError.onError = originalOnError;
  });

  testWidgets('主页 picker 以统一单选列表展示主页结果', (tester) async {
    await tester.pumpWidget(
      _buildApp(const HomepagePickerPage(initialQuery: '西湖')),
    );
    await tester.pumpAndSettle();

    expect(find.text('西湖景区'), findsWidgets);
    expect(find.textContaining('景点'), findsWidgets);
    expect(find.byKey(TestKeys.homepagePickerConfirmButton), findsOneWidget);
    expect(find.byKey(TestKeys.homepagePickerClearSelectionTile), findsNothing);
  });

  testWidgets('主页 picker 可清除当前关联并通过底部确认返回', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        _HomepagePickerHarness(
          initialSelection: HomepageSummary.fromMap(
            HomepageMockData.homepages.first,
          ).canonicalReference,
        ),
      ),
    );
    await tester.tap(find.text('打开主页选择'));
    await tester.pumpAndSettle();

    expect(
      find.byKey(TestKeys.homepagePickerClearSelectionTile),
      findsOneWidget,
    );

    await tester.tap(find.byKey(TestKeys.homepagePickerClearSelectionTile));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(TestKeys.homepagePickerConfirmButton));
    await tester.pumpAndSettle();

    expect(find.text('result:clear'), findsOneWidget);
  });

  testWidgets('主页 picker 选择结果后通过底部确认返回', (tester) async {
    await tester.pumpWidget(_buildApp(const _HomepagePickerHarness()));
    await tester.tap(find.text('打开主页选择'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('西湖景区').first);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(TestKeys.homepagePickerConfirmButton));
    await tester.pumpAndSettle();

    expect(find.text('result:homepage_sight_west_lake'), findsOneWidget);
  });
}

Widget _buildApp(Widget home) {
  return ProviderScope(child: MaterialApp(home: home));
}

class _HomepagePickerHarness extends StatefulWidget {
  const _HomepagePickerHarness({this.initialSelection});

  final HomepageCanonicalReference? initialSelection;

  @override
  State<_HomepagePickerHarness> createState() => _HomepagePickerHarnessState();
}

class _HomepagePickerHarnessState extends State<_HomepagePickerHarness> {
  String _resultText = 'result:none';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            ElevatedButton(
              onPressed: () async {
                final result = await Navigator.of(context)
                    .push<HomepagePickerSelectionResult>(
                      MaterialPageRoute<HomepagePickerSelectionResult>(
                        builder: (_) => HomepagePickerPage(
                          initialQuery: '西湖',
                          initialSelection: widget.initialSelection,
                        ),
                      ),
                    );
                if (!mounted) {
                  return;
                }
                setState(() {
                  if (result == null) {
                    _resultText = 'result:none';
                  } else if (result.clearSelection) {
                    _resultText = 'result:clear';
                  } else {
                    _resultText = 'result:${result.selection?.id ?? 'none'}';
                  }
                });
              },
              child: const Text('打开主页选择'),
            ),
            const SizedBox(height: 12),
            Text(_resultText),
          ],
        ),
      ),
    );
  }
}

class _NoNetworkHttpOverrides extends HttpOverrides {}
