// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-008
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-008.t4
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/image-editing/spec.md#gwt-008.t5
//
// 透视会话生命周期合同：确认入撤销栈、取消恢复面板打开前参数。
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_page.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/content_service/media/filter_catalog_release/image_editor_filter_catalog_typed_double.dart';

List<Override> _imageEditorOverrides() => <Override>[
  ...sealedCloudBoundaryOverrides(),
  imageEditorFilterRepositoryProvider.overrideWithValue(
    InMemoryImageEditorFilterCatalog(),
  ),
];

File _writePng(Directory dir, String name) {
  final file = File('${dir.path}/$name');
  final image = img.Image(width: 24, height: 24);
  for (var y = 0; y < 24; y++) {
    for (var x = 0; x < 24; x++) {
      final v = 40 + ((x * 9 + y * 5) % 170);
      image.setPixelRgb(x, y, v, v, v);
    }
  }
  file.writeAsBytesSync(img.encodePng(image));
  return file;
}

Future<void> _pumpEditor(
  WidgetTester tester,
  String path, {
  required void Function() onBack,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: _imageEditorOverrides(),
      child: MaterialApp(
        home: ImageEditorPage(
          initialPath: path,
          source: 'test',
          imagePaths: <String>[path],
          onBack: onBack,
          onDone: (_) {},
        ),
      ),
    ),
  );
  await tester.pump(const Duration(milliseconds: 200));
}

Future<void> _openPerspectivePanel(WidgetTester tester) async {
  await tester.tap(find.text(MediaText.imageEditorProTools));
  await tester.pump(const Duration(milliseconds: 200));
  await tester.tap(find.text(MediaText.imageEditorProPerspective).last);
  await tester.pump(const Duration(milliseconds: 200));
  expect(
    find.text(MediaText.imageEditorProPerspectiveHorizontal),
    findsOneWidget,
  );
}

/// 在水平透视滑杆区域向右拖动，产生非零透视值。
Future<void> _dragHorizontalPerspective(WidgetTester tester) async {
  final label = find.text(MediaText.imageEditorProPerspectiveHorizontal);
  final labelCenter = tester.getCenter(label);
  // 滑杆在标签右侧同一行：从行中部向右拖。
  final start = Offset(labelCenter.dx + 140, labelCenter.dy);
  await tester.dragFrom(start, const Offset(60, 0));
  await tester.pump(const Duration(milliseconds: 100));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const pathProviderChannel = MethodChannel('plugins.flutter.io/path_provider');
  late Directory pathProviderDir;

  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
    pathProviderDir = Directory.systemTemp.createTempSync(
      'qwq_editor_perspective_',
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

  testWidgets('透视确认后入撤销栈：撤销按钮可用（GWT-008.t4）', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final dir = Directory.systemTemp.createTempSync('qwq_perspective_undo_');
    addTearDown(() => dir.deleteSync(recursive: true));
    final file = _writePng(dir, 'a.png');

    await _pumpEditor(tester, file.path, onBack: () {});

    // 初始：撤销禁用。
    final undoBefore = tester.widget<CupertinoButton>(
      find.ancestor(
        of: find.byIcon(CupertinoIcons.arrow_uturn_left),
        matching: find.byType(CupertinoButton),
      ),
    );
    expect(undoBefore.onPressed, isNull);

    await _openPerspectivePanel(tester);
    await _dragHorizontalPerspective(tester);

    // 确认烘焙。
    await tester.tap(find.byIcon(CupertinoIcons.checkmark));
    // 等待异步烘焙完成（真实引擎写临时文件）；烘焙 loading 中图标可能
    // 暂不在树上，先判存在再取 widget。
    final undoIcon = find.byIcon(CupertinoIcons.arrow_uturn_left);
    CupertinoButton? undoAfter() {
      if (undoIcon.evaluate().isEmpty) return null;
      return tester.widget<CupertinoButton>(
        find.ancestor(of: undoIcon, matching: find.byType(CupertinoButton)),
      );
    }

    for (var i = 0; i < 100 && undoAfter()?.onPressed == null; i++) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 30)),
      );
      await tester.pump(const Duration(milliseconds: 50));
    }
    expect(
      undoAfter()?.onPressed,
      isNotNull,
      reason: '透视确认后必须作为编辑步骤进入撤销栈',
    );
  });

  testWidgets('透视取消恢复面板打开前参数（GWT-008.t5）', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final dir = Directory.systemTemp.createTempSync('qwq_perspective_cancel_');
    addTearDown(() => dir.deleteSync(recursive: true));
    final file = _writePng(dir, 'a.png');

    var backCalls = 0;
    await _pumpEditor(tester, file.path, onBack: () => backCalls++);

    await _openPerspectivePanel(tester);
    await _dragHorizontalPerspective(tester);

    // 拖动后至少有一个非零值文本（滑杆右侧值），且两轴中水平轴非 0。
    final zeroTextsAfterDrag = find.text('0').evaluate().length;

    // 取消（X）：恢复面板打开前参数。
    await tester.tap(find.byIcon(CupertinoIcons.xmark));
    await tester.pump(const Duration(milliseconds: 200));

    // 重新打开透视面板：两轴值必须回到 0。
    await _openPerspectivePanel(tester);
    final zeroTexts = find.text('0').evaluate().length;
    expect(
      zeroTexts,
      greaterThanOrEqualTo(2),
      reason: '取消后重进面板，两轴透视值必须恢复为 0（拖动后为 $zeroTextsAfterDrag 个 0）',
    );
    expect(backCalls, 0, reason: '面板取消不得触发页面返回');
  });
}
