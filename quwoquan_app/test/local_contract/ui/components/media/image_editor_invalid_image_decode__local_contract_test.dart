import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/image/editor/image_editor_page.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/image_editor_operation_panel.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  testWidgets('本地坏图进入编辑页和滤镜面板时不冒泡解码异常', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final dir = Directory.systemTemp.createTempSync(
      'qwq_image_editor_bad_image_',
    );
    addTearDown(() {
      if (dir.existsSync()) {
        dir.deleteSync(recursive: true);
      }
    });
    final first = File('${dir.path}/first.jpg')
      ..writeAsBytesSync(const <int>[0, 1, 2, 3, 4]);
    final second = File('${dir.path}/second.jpg')
      ..writeAsBytesSync(const <int>[5, 6, 7, 8, 9]);

    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: ImageEditorPage(
            initialPath: first.path,
            source: 'test',
            index: 0,
            total: 2,
            imagePaths: <String>[first.path, second.path],
            onDone: (_) {},
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 160));

    expect(tester.takeException(), isNull);
    expect(
      find.byKey(ValueKey<String>('image-editor-thumb-${first.path}')),
      findsOneWidget,
    );

    await tester.tap(find.text(MediaText.imageEditorFilter));
    for (var i = 0; i < 12; i++) {
      await tester.pump(const Duration(milliseconds: 80));
      if (find.byType(ImageEditorOperationPanel).evaluate().isNotEmpty &&
          find
              .text(MediaText.imageEditorFilterRecommended)
              .evaluate()
              .isNotEmpty) {
        break;
      }
    }
    for (var i = 0; i < 12; i++) {
      await tester.pump(const Duration(milliseconds: 80));
    }

    expect(find.byType(ImageEditorOperationPanel), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
