import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/pageflip_book.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/render/high_fidelity/pageflip_book_high_fidelity_facade.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_light_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('PageflipBookIsolatedV2', () {
    test(
      'high fidelity facade resolves isolated texture session from scene binding',
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

        final snapshots = <int, ArticlePageTextureSnapshot>{
          0: await _snapshotForColor(const Color(0xFFECD3B1), pageSize),
          1: await _snapshotForColor(const Color(0xFFB7D1F1), pageSize),
        };

        final highFidelityState = const PageflipBookIsolatedHighFidelityFacade()
            .resolve(
              scene: scene!,
              snapshots: snapshots,
              existingSession: null,
              supportsAdvancedPageCurl: true,
              freezeBinding: false,
            );

        expect(highFidelityState.usesMesh, isTrue);
        expect(highFidelityState.bundle, isNotNull);
        expect(highFidelityState.textureSession, isNotNull);
        expect(highFidelityState.textureSession!.binding.rectoPageIndex, 0);
        expect(highFidelityState.textureSession!.binding.versoPageIndex, 1);
        expect(highFidelityState.textureSession!.binding.bottomPageIndex, 0);

        for (final snapshot in snapshots.values) {
          snapshot.dispose();
        }
      },
    );

    test(
      'high fidelity facade keeps V2 mesh path even when shader effects are unavailable',
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

        final snapshots = <int, ArticlePageTextureSnapshot>{
          0: await _snapshotForColor(const Color(0xFFECD3B1), pageSize),
          1: await _snapshotForColor(const Color(0xFFB7D1F1), pageSize),
        };

        final highFidelityState = const PageflipBookIsolatedHighFidelityFacade()
            .resolve(
              scene: scene!,
              snapshots: snapshots,
              existingSession: null,
              supportsAdvancedPageCurl: false,
              freezeBinding: false,
            );

        expect(highFidelityState.usesMesh, isTrue);
        expect(highFidelityState.textureSession, isNotNull);
        expect(highFidelityState.shaderEffectsEnabled, isFalse);

        for (final snapshot in snapshots.values) {
          snapshot.dispose();
        }
      },
    );

    test(
      'builds backward mesh scene with shared leaf silhouette and covered-current underlay',
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
        expect(
          renderScene.renderScene.direction,
          PageflipBookIsolatedDirection.backward,
        );
        expect(renderScene.renderScene.drawCoveredCurrentUnderlay, isTrue);
        final exposureBounds = renderScene.meshFrame.bottomClipPath.getBounds();
        expect(exposureBounds.left, equals(scene.pageRect.left));
        expect(exposureBounds.right, lessThan(scene.pageRect.right));
        expect(
          renderScene.meshFrame.leafBounds.bottom,
          lessThanOrEqualTo(scene.pageRect.bottom),
        );

        bundle.recto.dispose();
        bundle.verso.dispose();
        bundle.bottom.dispose();
      },
    );

    test(
      'forward mesh derives bottom exposure from silhouette difference',
      () async {
        final controller = PageflipBookIsolatedController(
          pageCount: 4,
          initialPage: 1,
        );
        const stageSize = Size(900, 1200);
        const pageSize = Size(420, 584);
        controller.updateViewport(stageSize: stageSize, pageSize: pageSize);

        final scene = controller.sceneForStage(stageSize);
        expect(scene, isNotNull);
        final pageRect = scene!.pageRect;

        expect(
          controller.start(Offset(pageRect.right - 18, pageRect.bottom - 18)),
          isTrue,
        );
        controller.fold(Offset(pageRect.center.dx + 48, pageRect.center.dy));

        final activeScene = controller.sceneForStage(stageSize);
        expect(activeScene, isNotNull);
        expect(activeScene!.sheetBinding, isNotNull);
        expect(activeScene.sheetBinding!.rectoPageIndex, 1);
        expect(activeScene.sheetBinding!.versoPageIndex, 2);
        expect(activeScene.sheetBinding!.bottomPageIndex, 2);

        final snapshots = <int, ArticlePageTextureSnapshot>{
          1: await _snapshotForColor(const Color(0xFFB7D1F1), pageSize),
          2: await _snapshotForColor(const Color(0xFFD8EBC5), pageSize),
        };

        final highFidelityState = const PageflipBookIsolatedHighFidelityFacade()
            .resolve(
              scene: activeScene,
              snapshots: snapshots,
              existingSession: null,
              supportsAdvancedPageCurl: true,
              freezeBinding: false,
            );

        expect(highFidelityState.usesMesh, isTrue);
        expect(highFidelityState.bundle, isNotNull);

        final renderScene = const PageflipBookIsolatedMeshBuilder().build(
          scene: activeScene,
          textures: highFidelityState.bundle!,
          lightConfig: _lightConfig,
        );

        expect(renderScene, isNotNull);
        expect(
          renderScene!.renderScene.direction,
          PageflipBookIsolatedDirection.forward,
        );
        expect(renderScene.renderScene.drawCoveredCurrentUnderlay, isFalse);
        expect(renderScene.meshFrame.frontSurface, isNotNull);
        expect(renderScene.meshFrame.backSurface, isNotNull);
        final pageRectPath = ui.Path()..addRect(activeScene.pageRect);
        final derivedBottomClip = ui.Path.combine(
          ui.PathOperation.difference,
          pageRectPath,
          renderScene.meshFrame.leafClipPath,
        );
        final resolvedClipBounds = renderScene.meshFrame.bottomClipPath
            .getBounds();
        expect(resolvedClipBounds, equals(derivedBottomClip.getBounds()));
        expect(
          renderScene.meshFrame.leafBounds.bottom,
          lessThanOrEqualTo(activeScene.pageRect.bottom),
        );

        for (final snapshot in snapshots.values) {
          snapshot.dispose();
        }
      },
    );

    testWidgets('widget keeps V2 mesh renderer active once capture is warm', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Center(
            child: SizedBox(
              width: 900,
              height: 1200,
              child: PageflipBookIsolated(
                pageCount: 3,
                initialPage: 1,
                pageBuilder: (context, pageIndex, pageSize) {
                  return ColoredBox(
                    color: <Color>[
                      const Color(0xFFECD3B1),
                      const Color(0xFFB7D1F1),
                      const Color(0xFFD8EBC5),
                    ][pageIndex],
                  );
                },
              ),
            ),
          ),
        ),
      );

      for (var index = 0; index < 6; index += 1) {
        await tester.pump(const Duration(milliseconds: 24));
      }

      final stageFinder = find.byKey(PageflipBookIsolatedTestKeys.stage);
      expect(stageFinder, findsOneWidget);
      final stageRect = tester.getRect(stageFinder);
      final gesture = await tester.startGesture(
        Offset(stageRect.right - 20, stageRect.bottom - 40),
      );
      await tester.pump();
      await gesture.moveTo(
        Offset(stageRect.center.dx + 60, stageRect.center.dy),
      );
      await tester.pump(const Duration(milliseconds: 48));
      await tester.pump(const Duration(milliseconds: 48));

      expect(
        find.byKey(PageflipBookIsolatedTestKeys.meshRenderer),
        findsOneWidget,
      );

      await gesture.up();
      await tester.pumpAndSettle();
    });
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
