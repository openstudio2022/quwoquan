// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/filter-catalog-release/spec.md#gwt-003

import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_models.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/adapters/image_editor_filter_repository.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_page.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/adapters/verified_filter_catalog_store.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../../../support/service/content_service/media/filter_catalog_release/filter_catalog_query_typed_double.dart';

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
    await tester.tap(find.text(MediaText.imageEditorFilter));
    await tester.pump();

    expect(
      find.byKey(const ValueKey<String>('image_editor_filter_catalog_loading')),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);

    catalog.complete(await _canonicalConfig());
    // loading 指示器为持续动画，pumpAndSettle 永不收敛；有限 pump 等待
    // 目录渲染完成即可。
    await _pumpUntil(
      tester,
      () => find
          .byKey(const ValueKey<String>('image_editor_filter_catalog_loading'))
          .evaluate()
          .isEmpty,
    );
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
      await tester.tap(find.text(MediaText.imageEditorFilter));
      await _pumpUntil(
        tester,
        () => find
            .byKey(
              const ValueKey<String>('image_editor_filter_catalog_failure'),
            )
            .evaluate()
            .isNotEmpty,
      );

      expect(
        find.byKey(
          const ValueKey<String>('image_editor_filter_catalog_failure'),
        ),
        findsOneWidget,
      );
      expect(find.text(MediaText.imageEditorFilterLoadFailed), findsOneWidget);

      await tester.tap(find.text(ContentText.tryAgain));
      await _pumpUntil(
        tester,
        () =>
            find
                .byKey(
                  const ValueKey<String>(
                    'image_editor_filter_catalog_failure',
                  ),
                )
                .evaluate()
                .isEmpty &&
            find
                .byKey(
                  const ValueKey<String>(
                    'image_editor_filter_catalog_loading',
                  ),
                )
                .evaluate()
                .isEmpty,
      );

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

/// 有限 pump 等待条件成立（loading 指示器是持续动画，禁用 pumpAndSettle）。
Future<void> _pumpUntil(
  WidgetTester tester,
  bool Function() condition,
) async {
  for (var i = 0; i < 100 && !condition(); i++) {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 30)),
    );
    await tester.pump(const Duration(milliseconds: 50));
  }
  expect(condition(), isTrue, reason: '等待条件在限次 pump 内未成立');
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
  final snapshot = await InMemoryFilterCatalogQuery().getActiveFilterCatalog();
  return imageEditorFilterConfigFromSnapshot(snapshot);
}
