import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/render/mesh/pageflip_book_mesh_builder.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_renderer.dart';

class PageflipBookIsolatedMeshRenderer extends StatelessWidget {
  const PageflipBookIsolatedMeshRenderer({
    super.key,
    required this.scene,
    this.lightingProgram,
    this.backfaceProgram,
  });

  final PageflipBookIsolatedMeshRenderScene scene;
  final ui.FragmentProgram? lightingProgram;
  final ui.FragmentProgram? backfaceProgram;

  @override
  Widget build(BuildContext context) {
    return KeyedSubtree(
      key: PageflipBookIsolatedTestKeys.meshLayer,
      child: ArticlePageCurlRenderer(
        scene: scene.legacyScene,
        lightingProgram: lightingProgram,
        backfaceProgram: backfaceProgram,
      ),
    );
  }
}
