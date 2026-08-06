class CloudApiQueryDefaults {
  const CloudApiQueryDefaults._();

  static const int commentRepliesLimit = 10;
  static const int intersectionListLimit = 50;

  /// 交集发现区云侧候选窗：单屏 4~4.5 张 + 端内「换一批」轮转，
  /// 候选窗须大于单批展示窗（windowSize=6）。
  static const int intersectionFeedLimit = 12;
  static const int objectIntersectionsLimit = 8;
}
