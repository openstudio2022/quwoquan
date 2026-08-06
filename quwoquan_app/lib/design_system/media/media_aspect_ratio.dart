import 'package:quwoquan_app/design_system/spacing/discovery_feed_spacing.dart';

/// 设计系统展示态媒体宽高比（width / height）安全护栏。
///
/// 统一收口首页 feed、内容卡、评论图片等处对异常宽高比的 clamp 逻辑（R25 横切提取）：
/// - 超宽横图被收到 [kDisplayMaxAspectRatio]（默认 16/9），避免破坏信息流节奏；
/// - 超长竖图被收到 [kDisplayMinAspectRatio]（默认 2/3），避免无限拉高页面。
///
/// 默认比例边界唯一来源于 [DiscoveryFeedSpacing]，禁止在 UI 内联重复 clamp。
/// 个别场景（如文章封面）若需要更宽的下界，可显式传入 [min] / [max] 覆盖，但仍应
/// 经由本工具，保证「异常宽高比 → 安全展示比例」的判定只有一份实现。
const double kDisplayMinAspectRatio =
    DiscoveryFeedSpacing.homeFeedMediaMinAspectRatio;

const double kDisplayMaxAspectRatio =
    DiscoveryFeedSpacing.homeFeedMediaMaxAspectRatio;

/// 无宽高信息时的安全占位比例（偏竖的方图，贴近多数图文）。
const double kDisplayFallbackAspectRatio = 4 / 3;

/// 视频缺省占位比例（横屏优先）。
const double kDisplayVideoFallbackAspectRatio = 16 / 9;

/// 由原始像素 [width] / [height] 计算受保护的展示宽高比。
///
/// 当宽高缺失或非法（<=0 / 非有限）时回退到 [fallback]，回退值同样会被 clamp 到
/// `[min, max]` 区间内，确保返回值永远是安全的展示比例。
double clampDisplayAspectRatio({
  double? width,
  double? height,
  double fallback = kDisplayFallbackAspectRatio,
  double min = kDisplayMinAspectRatio,
  double max = kDisplayMaxAspectRatio,
}) {
  if (width != null && height != null && width > 0 && height > 0) {
    return clampDisplayAspectRatioValue(
      width / height,
      fallback: fallback,
      min: min,
      max: max,
    );
  }
  return clampDisplayAspectRatioValue(
    fallback,
    fallback: fallback,
    min: min,
    max: max,
  );
}

/// 由已知宽高比 [ratio] clamp 到安全展示区间。
///
/// 非法比例（null / 非有限 / <=0）回退到 [fallback]。
double clampDisplayAspectRatioValue(
  double? ratio, {
  double fallback = kDisplayFallbackAspectRatio,
  double min = kDisplayMinAspectRatio,
  double max = kDisplayMaxAspectRatio,
}) {
  final candidate = (ratio != null && ratio.isFinite && ratio > 0)
      ? ratio
      : fallback;
  return _clampToRange(candidate, min, max);
}

double _clampToRange(double value, double min, double max) {
  if (!value.isFinite || value <= 0) {
    return min;
  }
  if (min > max) {
    return value;
  }
  return value.clamp(min, max).toDouble();
}
