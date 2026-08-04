import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

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

  /// 从 generated `ContentAppConfig` 读取 `intersection` 子节点；
  /// 缺失字段回落默认值。
  factory IntersectionDisplayConfig.fromAppConfig(ContentAppConfig config) {
    final raw = config.intersection;
    if (raw == null) return fallback;
    return IntersectionDisplayConfig(
      inlineExpandCount: raw.inlineExpandCount ?? defaultInlineExpandCount,
      maxCandidateWindow: raw.maxCandidateWindow ?? defaultMaxCandidateWindow,
    );
  }
}
