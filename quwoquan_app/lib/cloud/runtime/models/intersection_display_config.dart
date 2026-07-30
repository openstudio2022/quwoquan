/// 交集展示控制配置（应用级，来自 `GET /config/app`）。
///
/// 设计约束（必读要求 1 / 接口剖离）：
/// - 展示控制（就地展开几行、推荐候选窗）是应用骨架级系统配置，下沉到 /config/app，
///   交集列表接口只回数据，禁止把展示控制混进列表契约。
/// - 解析失败 / 缺失 → 回落端默认值，启动一次加载、全局共享。
class IntersectionDisplayConfig {
  const IntersectionDisplayConfig({
    this.inlineExpandCount = defaultInlineExpandCount,
    this.maxCandidateWindow = defaultMaxCandidateWindow,
  });

  /// 对象页交集卡默认就地展开的证据组行数。
  final int inlineExpandCount;

  /// 首页/频道推荐候选窗上限（看过保留但降权，最多取这么多）。
  final int maxCandidateWindow;

  static const int defaultInlineExpandCount = 3;
  static const int defaultMaxCandidateWindow = 20;

  static const IntersectionDisplayConfig fallback = IntersectionDisplayConfig();

  /// 从 `/config/app` 响应根（wireRoot）解析 `intersection` 子节点；
  /// 仅消费 metadata 声明的 canonical snake_case wire key；缺失字段回落默认值。
  factory IntersectionDisplayConfig.fromAppConfigRoot(
    Map<String, Object?> root,
  ) {
    final content = (root['content'] as Map?)?.cast<String, Object?>();
    final raw = (content?['intersection'] as Map?)?.cast<String, Object?>();
    if (raw == null) return fallback;
    return IntersectionDisplayConfig(
      inlineExpandCount:
          _asPositiveInt(raw['inline_expand_count']) ??
          defaultInlineExpandCount,
      maxCandidateWindow:
          _asPositiveInt(raw['max_candidate_window']) ??
          defaultMaxCandidateWindow,
    );
  }

  static int? _asPositiveInt(Object? value) {
    if (value is! int || value <= 0) return null;
    return value;
  }
}
