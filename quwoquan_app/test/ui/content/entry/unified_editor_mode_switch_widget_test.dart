import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/create_page.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

Widget _buildCreatePageApp({String? initialTabKey}) {
  return ProviderScope(
    overrides: [
      contentRepositoryProvider.overrideWithValue(MockContentRepository()),
      circleRepositoryProvider.overrideWithValue(MockCircleRepository()),
    ],
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => MaterialApp(
        locale: const Locale('zh'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: CreatePage(initialTabKey: initialTabKey),
      ),
    ),
  );
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  testWidgets('默认进入文字编辑器，正文输入为第一优先级', (tester) async {
    await tester.pumpWidget(_buildCreatePageApp());
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(TestKeys.createMomentInput), '今天的旅行记录');
    await tester.pump();

    expect(find.byKey(TestKeys.createIdentityWork), findsNothing);
    expect(find.byKey(TestKeys.createWorkFormatImage), findsNothing);
    expect(find.text('添加标题（可选）'), findsOneWidget);
    expect(find.byKey(TestKeys.createMediaAddButton), findsOneWidget);
    expect(find.text('从相册加图'), findsNothing);
    expect(find.text('相机补图'), findsNothing);

    final bodyField = tester.widget<CupertinoTextField>(
      find.byKey(TestKeys.createMomentInput),
    );
    expect(bodyField.controller?.text, '今天的旅行记录');
  });

  testWidgets('legacy photo tab key 进入单主按钮媒体编辑器骨架', (tester) async {
    await tester.pumpWidget(_buildCreatePageApp(initialTabKey: 'photo'));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.createMediaAddButton), findsOneWidget);
    expect(find.text('添加图片或视频'), findsOneWidget);
    expect(find.byKey(TestKeys.createIdentityMoment), findsNothing);
    expect(find.byKey(TestKeys.createWorkFormatVideo), findsNothing);
  });

  testWidgets('正文输入限制为 5000 字', (tester) async {
    await tester.pumpWidget(_buildCreatePageApp());
    await tester.pumpAndSettle();

    final text = 'a' * 5200;
    await tester.enterText(find.byKey(TestKeys.createMomentInput), text);
    await tester.pump();

    final bodyField = tester.widget<CupertinoTextField>(
      find.byKey(TestKeys.createMomentInput),
    );
    expect(bodyField.controller?.text.length, 5000);
  });

  testWidgets('媒体区改为多行拖拽网格且不显示图片封面语义', (tester) async {
    await tester.pumpWidget(_buildCreatePageApp(initialTabKey: 'photo'));
    await tester.pumpAndSettle();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(CreatePage)),
    );
    final notifier = container.read(createEditorProvider.notifier);
    notifier.setImages(<String>[
      '/tmp/a.jpg',
      '/tmp/b.jpg',
    ], editorKind: CreateEditorKind.media);
    notifier.setCurrentMediaIndex(0);
    await tester.pumpAndSettle();

    expect(find.byType(ReorderableListView), findsNothing);
    expect(find.byType(Wrap), findsWidgets);
    expect(find.text('封面'), findsNothing);
    expect(find.textContaining('轻点任意图片设为封面'), findsNothing);
    expect(find.textContaining('视频会自动使用封面帧'), findsNothing);
    expect(find.textContaining('需要配图时直接在这里添加'), findsNothing);
    expect(find.text('下一步'), findsOneWidget);
  });
}
