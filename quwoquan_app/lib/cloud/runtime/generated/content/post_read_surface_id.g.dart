// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: contracts/metadata/content/post/projections/read_presentation_surfaces.yaml
// Regenerate: make codegen-app

/// 帖子只读投影所挂靠的 UI 表面（与 post-projection-pipeline-inventory / gap 清单一致）。
enum PostReadSurfaceId {
  /// 关注流 / 发现列表卡片（MediaPostCard 等）
  feedCard,
  /// 文章详情阅读态
  detailArticle,
  /// 图文详情
  detailPhoto,
  /// 视频详情
  detailVideo,
  /// 沉浸滑卡 / 统一媒体浏览器
  immersive,
  /// 搜索结果内容命中卡片
  searchCard,
  /// 圈子作品区 / hub 流
  circleWorks,
  /// 个人主页作品栅格
  profileWorks,
  /// 个人主页微趣列表
  profileMoments,
  /// 创作预览（Draft → ReadPresentation）
  draftPreview,
}
