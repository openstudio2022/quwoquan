import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/scene/pageflip_book_scene.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_light_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_mesh_builder.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_renderer.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';

@immutable
class PageflipBookIsolatedMeshRenderScene {
  const PageflipBookIsolatedMeshRenderScene({
    required this.legacyScene,
    required this.meshFrame,
  });

  final ArticlePageCurlRenderScene legacyScene;
  final ArticlePageCurlFrame meshFrame;
}

class PageflipBookIsolatedMeshBuilder {
  const PageflipBookIsolatedMeshBuilder({
    this.delegate = const ArticlePageCurlMeshBuilder(),
  });

  final ArticlePageCurlMeshBuilder delegate;

  PageflipBookIsolatedMeshRenderScene? build({
    required PageflipBookIsolatedScene scene,
    required ArticlePageTextureBundle textures,
    required ArticlePageCurlLightConfig lightConfig,
  }) {
    final direction = scene.direction;
    final corner = scene.corner;
    final renderFrame = scene.renderFrame;
    final dragPoint =
        renderFrame?.localPagePoint ?? scene.calculation?.getPosition();
    if (direction == null || corner == null || dragPoint == null) {
      return null;
    }
    final meshFrame = delegate.build(
      pageRect: scene.pageRect,
      pageSize: scene.pageSize,
      dragPoint: dragPoint,
      progress: renderFrame?.progress ?? 0,
      direction: direction,
      corner: corner,
      bottomClipPath: scene.buildBottomClipPath(),
      reversePose: scene.legacyScene.reversePose,
      renderFrame: renderFrame,
    );
    final timeline = renderFrame?.timeline;
    final lightState = resolveArticlePageCurlLightState(
      progress: meshFrame.progress,
      foldXNormalized: meshFrame.foldXNormalized,
      curlLift: meshFrame.curlLift,
      rollProgress: meshFrame.rollProgress,
      cylinderProgress: meshFrame.cylinderProgress,
      unfoldProgress: meshFrame.unfoldProgress,
      cylinderRadiusNormalized: timeline?.cylinderRadiusNormalized ?? 0,
      unrollWidthNormalized: timeline?.unrollWidthNormalized ?? 0,
      bottomGapNormalized: timeline?.bottomGapNormalized ?? 0,
      direction: direction,
      corner: corner,
    );
    return PageflipBookIsolatedMeshRenderScene(
      legacyScene: ArticlePageCurlRenderScene(
        stageSize: scene.stageSize,
        pageRect: scene.pageRect,
        textures: textures,
        meshFrame: meshFrame,
        lightConfig: lightConfig,
        lightState: lightState,
        direction: direction,
        corner: corner,
      ),
      meshFrame: meshFrame,
    );
  }
}
