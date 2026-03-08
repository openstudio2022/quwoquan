/// 一级 Tab — 与 ui_config.yaml profile_tabs 对齐
enum ProfileTab {
  creations,
  circles,
  interaction,
  lifestyle,
}

/// 创作二级 SubTab — contentType 与 discoveryTabs 对齐
enum CreationSubTab {
  all,
  micro,
  image,
  video,
  article,
}

/// 创作可见性过滤
enum CreationVisibility {
  all,
  public_,
  private_,
}

/// 互动子维度
enum InteractionSubTab {
  likes,
  comments,
}

/// 互动方向
enum InteractionDirection {
  received,
  sent,
}

/// 生活子分类
enum LifestyleSubTab {
  footprint,
  bookMovieMusic,
  taste,
  loveObject,
}
