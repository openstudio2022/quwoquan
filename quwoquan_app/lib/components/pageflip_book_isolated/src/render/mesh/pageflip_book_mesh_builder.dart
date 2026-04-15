import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/scene/pageflip_book_scene.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/render_v2/leaf_mesh_builder_v2.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_light_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';

@immutable
class PageflipBookIsolatedMeshRenderScene {
  const PageflipBookIsolatedMeshRenderScene({
    required this.renderScene,
    required this.meshFrame,
  });

  final IsolatedLeafRenderSceneV2 renderScene;
  final LeafMeshFrameV2 meshFrame;
}

class PageflipBookIsolatedMeshBuilder {
  const PageflipBookIsolatedMeshBuilder({
    this.delegate = const LeafMeshBuilderV2(),
  });

  final LeafMeshBuilderV2 delegate;

  PageflipBookIsolatedMeshRenderScene? build({
    required PageflipBookIsolatedScene scene,
    required ArticlePageTextureBundle textures,
    required ArticlePageCurlLightConfig lightConfig,
  }) {
    if (!scene.isInteractive || scene.direction == null) {
      return null;
    }
    final meshFrame = delegate.build(scene: scene);
    return PageflipBookIsolatedMeshRenderScene(
      renderScene: IsolatedLeafRenderSceneV2(
        stageSize: scene.stageSize,
        pageRect: scene.pageRect,
        textures: textures,
        meshFrame: meshFrame,
        lightConfig: lightConfig,
        direction: scene.direction!,
        drawCoveredCurrentUnderlay: scene.drawsCoveredCurrentPage,
      ),
      meshFrame: meshFrame,
    );
  }
}
