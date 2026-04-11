import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';

/// 帖子只读投影统一入口（metadata `post_read_presentation` + 表面枚举）。
///
/// [PostReadSurfaceId] 目前不改变 [PostReadPresentation] 的字段映射（均由 DTO+wire 决定），
/// 供页面/组件显式标注「本帧 UI 所服务的表面」，满足 P2 SurfaceSpec 数据化。
class PostReadProjectionFacade {
  PostReadProjectionFacade._();

  static PostReadPresentation presentationFor(
    PostBaseDto post,
    PostReadSurfaceId surface, {
    Map<String, dynamic>? wire,
  }) {
    switch (surface) {
      case PostReadSurfaceId.feedCard:
      case PostReadSurfaceId.detailArticle:
      case PostReadSurfaceId.detailPhoto:
      case PostReadSurfaceId.detailVideo:
      case PostReadSurfaceId.immersive:
      case PostReadSurfaceId.searchCard:
      case PostReadSurfaceId.circleWorks:
      case PostReadSurfaceId.profileWorks:
      case PostReadSurfaceId.profileMoments:
      case PostReadSurfaceId.draftPreview:
        return PostReadPresentation.fromPostBase(post, wire: wire);
    }
  }
}

/// 页面边界三元组：wire DTO + 只读投影 + 表面。
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
      presentation: PostReadProjectionFacade.presentationFor(
        post,
        surface,
        wire: wire,
      ),
      surface: surface,
    );
  }
}
