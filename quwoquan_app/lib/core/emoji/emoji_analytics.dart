import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/core/emoji/emoji_repository.dart';

/// 每日 emoji 使用量埋点：每天首次上报自上次以来的增量
class EmojiAnalytics {
  /// 尝试执行每日一次上报；由调用方在「当日首次登录/启动」后调用
  static Future<void> tryReportDaily(EmojiRepository repo, AnalyticsService analytics) async {
    final today = _todayString();
    final last = repo.getLastReportDate();
    if (last == today) return;

    final incremental = repo.getIncrementalForReport();
    final totalUses = incremental.values.fold<int>(0, (a, b) => a + b);
    final emojiCount = incremental.length;

    final items = incremental.entries
        .map((e) => {'emoji_id': e.key, 'count': e.value})
        .toList();

    try {
      await analytics.trackEvent(AnalyticsEvent(
        eventType: 'emoji_daily_report',
        eventName: 'Emoji每日使用上报',
        properties: {
          'report_date': today,
          'last_report_date': last ?? '',
          'total_emoji_uses': totalUses,
          'emoji_count': emojiCount,
          'items': items,
        },
      ));
      await repo.setLastReportDate(today);
      await repo.clearIncremental();
    } catch (_) {
      // 失败保留增量，下次再试
    }
  }

  static String _todayString() {
    final n = DateTime.now();
    return '${n.year}-${n.month.toString().padLeft(2, '0')}-${n.day.toString().padLeft(2, '0')}';
  }
}
