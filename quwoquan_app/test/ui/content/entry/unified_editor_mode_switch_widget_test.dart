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

Widget _buildCreatePageApp({
  String? initialTabKey,
  EditorStartAction? initialAction,
}) {
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
        home: CreatePage(
          initialTabKey: initialTabKey,
          initialAction: initialAction,
        ),
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
    expect(find.text('输入标题（可选）'), findsOneWidget);
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
    expect(find.text('添加'), findsOneWidget);
    expect(find.byKey(TestKeys.createIdentityMoment), findsNothing);
    expect(find.byKey(TestKeys.createWorkFormatVideo), findsNothing);
  });

  testWidgets('长正文会按分页软上限拆分到文章页中', (tester) async {
    await tester.pumpWidget(_buildCreatePageApp());
    await tester.pumpAndSettle();

    final text = 'a' * 5200;
    await tester.enterText(find.byKey(TestKeys.createMomentInput), text);
    await tester.pump();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(CreatePage)),
    );
    final state = container.read(createEditorProvider);
    final bodyField = tester.widget<CupertinoTextField>(
      find.byKey(TestKeys.createMomentInput),
    );
    expect(bodyField.controller?.text.length, kArticlePageSoftCharacterLimit);
    expect(state.articlePages.length, greaterThan(1));
    expect(
      state.articlePages
          .map((page) => page.body)
          .where((body) => body.isNotEmpty)
          .join(),
      text,
    );
  });

  testWidgets('写文字入口进入沉浸式文章编辑页', (tester) async {
    await tester.pumpWidget(
      _buildCreatePageApp(initialAction: EditorStartAction.write),
    );
    await tester.pumpAndSettle();

    expect(find.text('文章编辑'), findsOneWidget);
    expect(find.text('草稿'), findsOneWidget);
    expect(find.byKey(TestKeys.createPublishButton), findsOneWidget);
    expect(find.text('输入标题（可选）'), findsOneWidget);
    expect(find.text('继续写内容，支持 emoji、图片、序号和模板'), findsOneWidget);
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

  testWidgets('空态添加按钮只占一个宫格且窄屏保持三列', (tester) async {
    await tester.binding.setSurfaceSize(const Size(320, 640));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(_buildCreatePageApp(initialTabKey: 'photo'));
    await tester.pumpAndSettle();

    final pageWidth = tester.getSize(find.byType(CreatePage)).width;
    final addWidth = tester.getSize(find.byKey(TestKeys.createMediaAddButton)).width;
    expect(addWidth, lessThan(pageWidth - 80));

    final container = ProviderScope.containerOf(
      tester.element(find.byType(CreatePage)),
    );
    final notifier = container.read(createEditorProvider.notifier);
    notifier.setImages(<String>[
      '/tmp/a.jpg',
      '/tmp/b.jpg',
    ], editorKind: CreateEditorKind.media);
    await tester.pumpAndSettle();

    final firstTile = find.byWidgetPredicate((widget) => widget is LongPressDraggable<String>);
    final firstTileTop = tester.getTopLeft(firstTile.first).dy;
    final addButtonTop = tester.getTopLeft(find.byKey(TestKeys.createMediaAddButton)).dy;
    expect(addButtonTop, closeTo(firstTileTop, 1));
  });

  testWidgets('图片达到上限时添加按钮不可继续唤起操作面板', (tester) async {
    await tester.pumpWidget(_buildCreatePageApp(initialTabKey: 'photo'));
    await tester.pumpAndSettle();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(CreatePage)),
    );
    final notifier = container.read(createEditorProvider.notifier);
    notifier.setImages(
      List<String>.generate(20, (index) => '/tmp/$index.jpg'),
      editorKind: CreateEditorKind.media,
    );
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.byKey(TestKeys.createMediaAddButton));
    await tester.tap(find.byKey(TestKeys.createMediaAddButton));
    await tester.pumpAndSettle();

    expect(find.byType(CupertinoActionSheet), findsNothing);
  });

  testWidgets('视频态居中展示并提供封面编辑入口', (tester) async {
    await tester.pumpWidget(_buildCreatePageApp(initialTabKey: 'photo'));
    await tester.pumpAndSettle();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(CreatePage)),
    );
    final notifier = container.read(createEditorProvider.notifier);
    notifier.setVideo(
      '/tmp/demo.mp4',
      editorKind: CreateEditorKind.media,
      thumbnail: '/tmp/demo_cover.jpg',
    );
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.createMediaAddButton), findsNothing);
    expect(find.text('轻点视频编辑，支持裁切、静音和精细选帧'), findsOneWidget);
    expect(find.text('更换视频'), findsOneWidget);

    await tester.tap(find.byIcon(CupertinoIcons.play_fill));
    await tester.pumpAndSettle();

    expect(find.text('视频编辑'), findsOneWidget);
  });
}
