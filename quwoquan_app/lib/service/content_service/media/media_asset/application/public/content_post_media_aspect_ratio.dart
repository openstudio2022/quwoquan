import 'package:quwoquan_app/service/content_service/media/media_asset/domain/media_aspect_ratio.dart';

/// Content 卡片消费媒体宽高比时使用的稳定边界。
double clampContentPostMediaAspectRatio(
  double value, {
  required double min,
  required double max,
}) {
  return clampDisplayAspectRatioValue(value, min: min, max: max);
}
