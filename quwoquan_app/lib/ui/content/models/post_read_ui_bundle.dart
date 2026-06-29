import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';

/// 页面边界三元组：wire DTO + 只读投影 + 表面（P2 SurfaceSpec 数据化）。
///
/// 投影统一经 [PostReadPresentation.fromPostBase]（DTO + wire 单一真相源）；
/// [surface] 仅标注「本帧 UI 所服务的表面」，不改变字段映射。
class PostReadUiBundle {
  const PostReadUiBundle({
    required this.post,
    required this.presentation,
    required this.surface,
  });

  final PostBaseDto post;
  final PostReadPresentation presentation;
  final PostReadSurfaceId surface;

  factory PostReadUiBundle.fromPost(
    PostBaseDto post,
    PostReadSurfaceId surface, {
    Map<String, dynamic>? wire,
  }) {
    return PostReadUiBundle(
      post: post,
      presentation: PostReadPresentation.fromPostBase(post, wire: wire),
      surface: surface,
    );
  }
}
