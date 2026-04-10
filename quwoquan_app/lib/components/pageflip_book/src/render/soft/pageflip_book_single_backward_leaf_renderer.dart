import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/components/pageflip_book/src/render/soft/pageflip_book_single_backward_soft_renderer.dart';
import 'package:quwoquan_app/components/pageflip_book/src/render/soft/pageflip_book_single_backward_soft_scene.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_renderer.dart';

class PageflipBookSingleBackwardLeafRenderer extends StatelessWidget {
  const PageflipBookSingleBackwardLeafRenderer.mesh({
    super.key,
    required ArticlePageCurlRenderScene scene,
  }) : _meshScene = scene,
       _softScene = null;

  const PageflipBookSingleBackwardLeafRenderer.soft({
    super.key,
    required PageflipBookSingleBackwardSoftScene scene,
  }) : _meshScene = null,
       _softScene = scene;

  final ArticlePageCurlRenderScene? _meshScene;
  final PageflipBookSingleBackwardSoftScene? _softScene;

  @override
  Widget build(BuildContext context) {
    final softScene = _softScene;
    if (softScene != null) {
      return PageflipBookSingleBackwardSoftRenderer(scene: softScene);
    }
    return ArticlePageCurlRenderer(scene: _meshScene!);
  }
}
