import 'package:quwoquan_app/core/constants/app_strings.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

/// 内容时间展示统一口径（创作时间 / 更新时间）。
///
/// 唯一真相源：[ContentSurfaceView.createdAt] / [updatedAt]（来自服务端 Post
/// 的真实 createdAt/updatedAt，不再以 publishedAt 借壳）。
///
/// 产品规则：更新时间与创作时间相等或更早，只展示创作时间；更新时间更晚，才同时
/// 展示「创作 + 更新」。容忍秒级抖动（差值 <= 1s 视为未更新），由 [_isUpdated]
/// 统一判定，避免端各处重复实现产生口径漂移（13-coding-discipline R25）。
class ContentTimeLabel {
  const ContentTimeLabel._();

  static bool _isUpdated(DateTime createdAt, DateTime? updatedAt) {
    if (updatedAt == null) {
      return false;
    }
    return updatedAt.difference(createdAt).inSeconds > 1;
  }

  /// 相对时间（"刚刚 / N分钟前 / N小时前 / N天前 / M月d"）。
  static String relative(DateTime time) {
    try {
      final diff = DateTime.now().difference(time);
      if (diff.inMinutes < 1) {
        return AppStrings.justNow;
      }
      if (diff.inMinutes < 60) {
        return '${diff.inMinutes}${AppStrings.minutesAgo}';
      }
      if (diff.inHours < 24) {
        return '${diff.inHours}${AppStrings.hoursAgo}';
      }
      if (diff.inDays < 7) {
        return '${diff.inDays}${AppStrings.daysAgo}';
      }
      return absolute(time);
    } catch (_) {
      return AppStrings.justNow;
    }
  }

  /// 绝对日期（"M月d日"，跨年补"yyyy年"）。
  static String absolute(DateTime time) {
    final local = time.toLocal();
    final monthDay = '${local.month}${AppStrings.monthDay}${local.day}日';
    if (local.year != DateTime.now().year) {
      return '${local.year}年$monthDay';
    }
    return monthDay;
  }

  /// 紧凑卡片元信息：创作相对时间；若发生实质更新追加「· 已编辑」。
  static String cardLabel({required DateTime createdAt, DateTime? updatedAt}) {
    final base = relative(createdAt);
    if (_isUpdated(createdAt, updatedAt)) {
      return '$base · ${UITextConstants.contentEditedSuffix}';
    }
    return base;
  }

  /// 文章阅读器/详情时间行：「创作于 X」；若发生实质更新，追加「· 更新于 Y」。
  static String readerLine({required DateTime createdAt, DateTime? updatedAt}) {
    final created =
        '${UITextConstants.contentCreatedAtPrefix} ${absolute(createdAt)}';
    if (updatedAt != null && _isUpdated(createdAt, updatedAt)) {
      return '$created · ${UITextConstants.contentUpdatedAtPrefix} ${absolute(updatedAt)}';
    }
    return created;
  }
}
