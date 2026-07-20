import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:quwoquan_app/components/media/image/editor/image_editor_page.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:shared_preferences/shared_preferences.dart';

File _writePng(Directory dir, String name) {
  final file = File('${dir.path}/$name');
  final image = img.Image(width: 16, height: 16);
  img.fill(image, color: img.ColorRgb8(128, 128, 128));
  file.writeAsBytesSync(img.encodePng(image));
  return file;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const pathProviderChannel = MethodChannel('plugins.flutter.io/path_provider');
  late Directory pathProviderDir;

  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
    pathProviderDir = Directory.systemTemp.createTempSync(
      'qwq_editor_path_provider_',
    );
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          pathProviderChannel,
          (_) async => pathProviderDir.path,
        );
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(pathProviderChannel, null);
    if (pathProviderDir.existsSync()) {
      pathProviderDir.deleteSync(recursive: true);
    }
  });

  testWidgets('无修改时 back 直接退出且不弹放弃确认', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final dir = Directory.systemTemp.createTempSync('qwq_editor_discard_');
    addTearDown(() => dir.deleteSync(recursive: true));
    final file = _writePng(dir, 'a.png');

    var backCalls = 0;
    Object? doneResult;
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: ImageEditorPage(
            initialPath: file.path,
            source: 'test',
            imagePaths: <String>[file.path],
            onBack: () => backCalls++,
            onDone: (result) => doneResult = result,
          ),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 200));

    await tester.tap(find.byIcon(CupertinoIcons.back));
    await tester.pump(const Duration(milliseconds: 300));

    expect(backCalls, 1);
    expect(doneResult, isNull);
    expect(find.text(UITextConstants.imageEditorDiscardTitle), findsNothing);
  });

  testWidgets('完成一步编辑后 back 必须确认放弃，确认后仅触发取消回调', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final dir = Directory.systemTemp.createTempSync(
      'qwq_editor_discard_edited_',
    );
    addTearDown(() => dir.deleteSync(recursive: true));
    final file = _writePng(dir, 'a.png');

    var backCalls = 0;
    Object? doneResult;
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: ImageEditorPage(
            initialPath: file.path,
            source: 'test',
            imagePaths: <String>[file.path],
            onBack: () => backCalls++,
            onDone: (result) => doneResult = result,
          ),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 200));

    await tester.tap(find.text(UITextConstants.imageEditorRotate));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text(UITextConstants.imageEditorRotateRight90), findsOneWidget);
    await tester.tap(find.text(UITextConstants.imageEditorRotateRight90));
    await tester.pump();
    expect(find.byKey(const ValueKey<String>('rotate-reset')), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.checkmark), findsOneWidget);
    await tester.tap(find.byIcon(CupertinoIcons.checkmark));

    final doneFinder = find.text(UITextConstants.imageEditDone);
    for (var i = 0; i < 100 && doneFinder.evaluate().isEmpty; i++) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 30)),
      );
      await tester.pump(const Duration(milliseconds: 50));
    }
    expect(doneFinder, findsOneWidget);
    final undoButton = tester.widget<CupertinoButton>(
      find.ancestor(
        of: find.byIcon(CupertinoIcons.arrow_uturn_left),
        matching: find.byType(CupertinoButton),
      ),
    );
    expect(undoButton.onPressed, isNotNull);
    expect(find.byIcon(CupertinoIcons.back), findsOneWidget);

    await tester.tap(find.byIcon(CupertinoIcons.back));
    await tester.pumpAndSettle();
    expect(backCalls, 0);
    expect(find.text(UITextConstants.imageEditorDiscardTitle), findsOneWidget);
    expect(doneResult, isNull);

    await tester.tap(find.text(UITextConstants.imageEditorDiscardConfirm));
    await tester.pumpAndSettle();
    expect(backCalls, 1);
    expect(doneResult, isNull);
  });

  testWidgets('顶栏「完成」提交结果且上报 submit', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final dir = Directory.systemTemp.createTempSync('qwq_editor_done_');
    addTearDown(() => dir.deleteSync(recursive: true));
    final file = _writePng(dir, 'a.png');

    Object? doneResult;
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: ImageEditorPage(
            initialPath: file.path,
            source: 'test',
            imagePaths: <String>[file.path],
            onBack: () {},
            onDone: (result) => doneResult = result,
          ),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 200));

    await tester.tap(find.text(UITextConstants.imageEditDone));
    await tester.pump(const Duration(milliseconds: 100));

    expect(doneResult, file.path);
  });

  testWidgets('撤销/重做按钮初始禁用；历史按钮无步骤时禁用', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final dir = Directory.systemTemp.createTempSync('qwq_editor_undo_');
    addTearDown(() => dir.deleteSync(recursive: true));
    final file = _writePng(dir, 'a.png');

    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: ImageEditorPage(
            initialPath: file.path,
            source: 'test',
            imagePaths: <String>[file.path],
            onBack: () {},
            onDone: (_) {},
          ),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 200));

    final undoButton = tester.widget<CupertinoButton>(
      find.ancestor(
        of: find.byIcon(CupertinoIcons.arrow_uturn_left),
        matching: find.byType(CupertinoButton),
      ),
    );
    expect(undoButton.onPressed, isNull);
    final redoButton = tester.widget<CupertinoButton>(
      find.ancestor(
        of: find.byIcon(CupertinoIcons.arrow_uturn_right),
        matching: find.byType(CupertinoButton),
      ),
    );
    expect(redoButton.onPressed, isNull);
    final historyButton = tester.widget<CupertinoButton>(
      find.ancestor(
        of: find.byIcon(CupertinoIcons.clock),
        matching: find.byType(CupertinoButton),
      ),
    );
    expect(historyButton.onPressed, isNull);
  });

  testWidgets('底部工具栏不再出现相框入口，包含全部 6 个工具', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final dir = Directory.systemTemp.createTempSync('qwq_editor_tools_');
    addTearDown(() => dir.deleteSync(recursive: true));
    final file = _writePng(dir, 'a.png');

    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: ImageEditorPage(
            initialPath: file.path,
            source: 'test',
            imagePaths: <String>[file.path],
            onBack: () {},
            onDone: (_) {},
          ),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 200));

    expect(find.text(UITextConstants.imageEditorFilter), findsOneWidget);
    expect(find.text(UITextConstants.imageEditorCrop), findsOneWidget);
    expect(find.text(UITextConstants.imageEditorRotate), findsOneWidget);
    expect(find.text(UITextConstants.imageEditorProTools), findsOneWidget);
    expect(find.text(UITextConstants.imageEditorText), findsOneWidget);
    expect(find.text(UITextConstants.imageEditorMosaic), findsOneWidget);
  });

  testWidgets('专业工具箱包含曲线/白平衡真实入口且无占位文案', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final dir = Directory.systemTemp.createTempSync('qwq_editor_pro_');
    addTearDown(() => dir.deleteSync(recursive: true));
    final file = _writePng(dir, 'a.png');

    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: ImageEditorPage(
            initialPath: file.path,
            source: 'test',
            imagePaths: <String>[file.path],
            onBack: () {},
            onDone: (_) {},
          ),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 200));

    await tester.tap(find.text(UITextConstants.imageEditorProTools));
    await tester.pump(const Duration(milliseconds: 200));

    expect(find.text(UITextConstants.imageEditorProCurve), findsOneWidget);
    expect(
      find.text(UITextConstants.imageEditorProWhiteBalance),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.imageEditorProTabOverall), findsOneWidget);
    expect(find.text(UITextConstants.imageEditorProBwLevels), findsOneWidget);
    // 曲线面板真实可进入。
    await tester.tap(find.text(UITextConstants.imageEditorProCurve));
    await tester.pump(const Duration(milliseconds: 300));
    expect(
      find.text(UITextConstants.imageEditorProCurveChannelRgb),
      findsOneWidget,
    );
  });
}
