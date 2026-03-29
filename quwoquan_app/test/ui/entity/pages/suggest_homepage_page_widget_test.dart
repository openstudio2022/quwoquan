import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/entity/pages/suggest_homepage_page.dart';

void main() {
  testWidgets('添加主页页切换车型后展示车型字段', (tester) async {
    final repository = _TrackingHomepageRepository();

    await tester.pumpWidget(
      _buildApp(
        repository: repository,
        child: const _SuggestHomepageHarness(),
      ),
    );
    await tester.tap(find.text('打开添加主页'));
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.addHomepageCityLabel), findsOneWidget);

    await tester.tap(find.text(UITextConstants.homepageTypeVehicle));
    await tester.pumpAndSettle();

    expect(
      find.text(UITextConstants.addHomepageVehicleManufacturerLabel),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.addHomepageVehicleSeriesLabel),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.addHomepageCityLabel), findsNothing);
  });

  testWidgets('添加主页页关闭时会提示放弃未提交修改', (tester) async {
    final repository = _TrackingHomepageRepository();

    await tester.pumpWidget(
      _buildApp(
        repository: repository,
        child: const _SuggestHomepageHarness(),
      ),
    );
    await tester.tap(find.text('打开添加主页'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(CupertinoTextField).first, '西湖景区');
    await tester.pump();

    await tester.tap(find.byIcon(CupertinoIcons.xmark));
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.unsavedChangesTitle), findsOneWidget);
    expect(find.text(UITextConstants.continueEditing), findsOneWidget);

    await tester.tap(find.text(UITextConstants.discard));
    await tester.pumpAndSettle();

    expect(find.text('result:closed'), findsOneWidget);
  });

  testWidgets('添加主页页提交车型草稿时会按实体语义组合标题', (tester) async {
    final repository = _TrackingHomepageRepository();

    await tester.pumpWidget(
      _buildApp(
        repository: repository,
        child: const _SuggestHomepageHarness(),
      ),
    );
    await tester.tap(find.text('打开添加主页'));
    await tester.pumpAndSettle();

    await tester.tap(find.text(UITextConstants.homepageTypeVehicle));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(CupertinoTextField).at(0), '丰田');
    await tester.enterText(find.byType(CupertinoTextField).at(1), 'RAV4');
    await tester.enterText(find.byType(CupertinoTextField).at(2), '2024 款');
    await tester.enterText(find.byType(CupertinoTextField).at(3), '双擎四驱');
    await tester.pump();

    await tester.tap(find.byKey(TestKeys.suggestHomepageSubmitButton));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();

    expect(repository.lastDraft?.homepageType, 'vehicle');
    expect(repository.lastDraft?.title, '丰田 RAV4');
    expect(repository.lastDraft?.subtitle, '2024 款 · 双擎四驱');
    expect(repository.lastDraft?.city, isEmpty);
    expect(repository.lastDraft?.address, isEmpty);
    expect(repository.lastDraft?.categoryTags, <String>['丰田']);
  });
}

Widget _buildApp({
  required _TrackingHomepageRepository repository,
  required Widget child,
}) {
  return ProviderScope(
    overrides: [
      homepageRepositoryProvider.overrideWithValue(repository),
    ],
    child: MaterialApp(home: child),
  );
}

class _SuggestHomepageHarness extends StatefulWidget {
  const _SuggestHomepageHarness();

  @override
  State<_SuggestHomepageHarness> createState() => _SuggestHomepageHarnessState();
}

class _SuggestHomepageHarnessState extends State<_SuggestHomepageHarness> {
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
                final result = await Navigator.of(context).push<bool>(
                  MaterialPageRoute<bool>(
                    builder: (_) => const SuggestHomepagePage(),
                  ),
                );
                if (!mounted) {
                  return;
                }
                setState(() {
                  _resultText =
                      result == true ? 'result:submitted' : 'result:closed';
                });
              },
              child: const Text('打开添加主页'),
            ),
            const SizedBox(height: 12),
            Text(_resultText),
          ],
        ),
      ),
    );
  }
}

class _TrackingHomepageRepository extends MockHomepageRepository {
  HomepageSuggestionDraft? lastDraft;

  @override
  Future<HomepageDetail> suggestHomepageCandidate({
    required HomepageSuggestionDraft draft,
  }) async {
    lastDraft = draft;
    return super.suggestHomepageCandidate(draft: draft);
  }
}
