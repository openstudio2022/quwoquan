import 'package:quwoquan_app/cloud/runtime/generated/content/post_read_presentation.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_read_surface_id.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/cloud/runtime/models/post_read_presentation_mapper.dart';

/// 页面边界三元组：wire DTO + 只读投影 + 表面（P2 SurfaceSpec 数据化）。
///
/// 投影统一经 [PostReadPresentationMapper.fromViewData]（DTO + wire 单一真相源）；
/// [surface] 仅标注「本帧 UI 所服务的表面」，不改变字段映射。
class PostReadUiBundle {
  const PostReadUiBundle({
    required this.post,
    required this.presentation,
    required this.surface,
  });

  final ContentPostViewData post;
  final PostReadPresentation presentation;
  final PostReadSurfaceId surface;

  factory PostReadUiBundle.fromPost(
    ContentPostViewData post,
    PostReadSurfaceId surface, {
    Map<String, dynamic>? wire,
  }) {
    return PostReadUiBundle(
      post: post,
      presentation: PostReadPresentationMapper.fromViewData(post, wire: wire),
      surface: surface,
    );
  }
}
