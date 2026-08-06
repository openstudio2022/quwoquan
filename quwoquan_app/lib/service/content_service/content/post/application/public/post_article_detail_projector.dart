import 'package:quwoquan_app/service/content_service/content/post/application/public/content_surface_view.dart';

/// Public typed seam for projecting a canonical post detail payload into the
/// article render model consumed by App surfaces.
abstract interface class PostArticleDetailProjector {
  ContentArticleRender project(
    Map<String, dynamic> raw, {
    required String fallbackArticleId,
  });
}
