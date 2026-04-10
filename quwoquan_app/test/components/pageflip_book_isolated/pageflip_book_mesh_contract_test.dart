import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/pageflip_book.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_light_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('PageflipBookIsolatedMeshBuilder', () {
    test(
      'builds backward mesh scene without soft or legacy contracts',
      () async {
        final controller = PageflipBookIsolatedController(
          pageCount: 4,
          initialPage: 1,
        );
        const stageSize = Size(900, 1200);
        const pageSize = Size(420, 584);
        controller.updateViewport(stageSize: stageSize, pageSize: pageSize);

        expect(controller.start(const Offset(320, 600)), isTrue);
        controller.fold(const Offset(440, 620));

        final scene = controller.sceneForStage(stageSize);
        expect(scene, isNotNull);
        expect(scene!.sheetBinding, isNotNull);

        final bundle = ArticlePageTextureBundle(
          recto: await _snapshotForColor(const Color(0xFFECD3B1), pageSize),
          verso: await _snapshotForColor(const Color(0xFFB7D1F1), pageSize),
          bottom: await _snapshotForColor(const Color(0xFFD8EBC5), pageSize),
        );

        final renderScene = const PageflipBookIsolatedMeshBuilder().build(
          scene: scene,
          textures: bundle,
          lightConfig: _lightConfig,
        );

        expect(renderScene, isNotNull);
        expect(renderScene!.meshFrame.frontSurface, isNotNull);
        expect(renderScene.meshFrame.backSurface, isNotNull);
        expect(renderScene.legacyScene.direction.name, 'back');

        bundle.recto.dispose();
        bundle.verso.dispose();
        bundle.bottom.dispose();
      },
    );
  });
}

const _lightConfig = ArticlePageCurlLightConfig(
  shadowColor: Color(0x5C000000),
  highlightColor: Color(0x45FFFFFF),
  paperTintColor: Color(0xFFFBF7EF),
  ambientOcclusionColor: Color(0x26000000),
);

Future<ArticlePageTextureSnapshot> _snapshotForColor(
  Color color,
  Size pageSize,
) async {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  canvas.drawRect(
    Rect.fromLTWH(0, 0, pageSize.width, pageSize.height),
    Paint()..color = color,
  );
  final picture = recorder.endRecording();
  final image = await picture.toImage(
    pageSize.width.round(),
    pageSize.height.round(),
  );
  return ArticlePageTextureSnapshot(
    image: image,
    logicalSize: pageSize,
    pixelRatio: 1,
  );
}
