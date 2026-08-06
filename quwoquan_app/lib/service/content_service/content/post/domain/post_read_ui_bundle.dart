import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/post_read_surface_id.g.dart';

/// 页面边界二元组：canonical Post 只读投影 + 表面（P2 SurfaceSpec 数据化）。
///
/// [presentation] 直接复用 generated `ContentPostProjection` 解码所得的
/// [ContentPostViewData]，不再建立第二套 presentation DTO；[surface] 仅标注
/// 「本帧 UI 所服务的表面」，不改变字段映射。
class PostReadUiBundle {
  const PostReadUiBundle({
    required this.post,
    required this.presentation,
    required this.surface,
  });

  final ContentPostViewData post;
  final ContentPostViewData presentation;
  final PostReadSurfaceId surface;

  factory PostReadUiBundle.fromPost(
    ContentPostViewData post,
    PostReadSurfaceId surface,
  ) {
    return PostReadUiBundle(post: post, presentation: post, surface: surface);
  }
}
