import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_models.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_repository.dart';
import 'package:quwoquan_app/components/media/image/editor/image_editor_page.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/infrastructure/local/content/filter_catalog/verified_filter_catalog_store.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const pathProviderChannel = MethodChannel('plugins.flutter.io/path_provider');
  late Directory pathProviderDir;

  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
    pathProviderDir = Directory.systemTemp.createTempSync(
      'qwq_filter_catalog_path_provider_',
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

  testWidgets('catalog loading keeps filter panel explicit and non-blocking', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final imageFile = _writeImage();
    addTearDown(() => imageFile.parent.deleteSync(recursive: true));
    final catalog = Completer<ImageEditorFilterConfig>();
    final repository = ImageEditorFilterRepository(
      catalogLoader: () => catalog.future,
    );

    await tester.pumpWidget(_editor(imageFile, repository));
    await tester.pump(const Duration(milliseconds: 250));
    await tester.tap(find.text(UITextConstants.imageEditorFilter));
    await tester.pump();

    expect(
      find.byKey(const ValueKey<String>('image_editor_filter_catalog_loading')),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);

    catalog.complete(await _canonicalConfig());
    await tester.pumpAndSettle();
  });

  testWidgets(
    'catalog failure exposes retry and recovers to canonical presets',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(390, 844));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final imageFile = _writeImage();
      addTearDown(() => imageFile.parent.deleteSync(recursive: true));
      var attempts = 0;
      final repository = ImageEditorFilterRepository(
        catalogLoader: () async {
          attempts += 1;
          if (attempts == 1) throw StateError('catalog unavailable');
          return _canonicalConfig();
        },
      );

      await tester.pumpWidget(_editor(imageFile, repository));
      await tester.pump(const Duration(milliseconds: 250));
      await tester.tap(find.text(UITextConstants.imageEditorFilter));
      await tester.pumpAndSettle();

      expect(
        find.byKey(
          const ValueKey<String>('image_editor_filter_catalog_failure'),
        ),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.imageEditorFilterLoadFailed),
        findsOneWidget,
      );

      await tester.tap(find.text(UITextConstants.retry));
      await tester.pumpAndSettle();

      expect(attempts, 2);
      expect(
        find.byKey(
          const ValueKey<String>('image_editor_filter_catalog_failure'),
        ),
        findsNothing,
      );
    expect(
      find.byKey(
        const ValueKey<String>('image_editor_filter_catalog_loading'),
      ),
      findsNothing,
    );
      expect(tester.takeException(), isNull);
    },
  );
}

Widget _editor(File imageFile, ImageEditorFilterRepository filterRepository) {
  return ProviderScope(
    child: MaterialApp(
      home: ImageEditorPage(
        initialPath: imageFile.path,
        source: 'test',
        imagePaths: <String>[imageFile.path],
        filterRepository: filterRepository,
      ),
    ),
  );
}

File _writeImage() {
  final directory = Directory.systemTemp.createTempSync(
    'qwq_filter_catalog_editor_',
  );
  final file = File('${directory.path}/image.png');
  final image = img.Image(width: 16, height: 16);
  img.fill(image, color: img.ColorRgb8(128, 128, 128));
  file.writeAsBytesSync(img.encodePng(image));
  return file;
}

Future<ImageEditorFilterConfig> _canonicalConfig() async {
  final snapshot = await AlphaFilterCatalogQuery().getActiveFilterCatalog();
  return imageEditorFilterConfigFromSnapshot(snapshot);
}
