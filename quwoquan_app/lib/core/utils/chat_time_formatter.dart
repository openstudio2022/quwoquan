/// 聊天时间格式化 — 云端 UTC+8 → 设备本地时区展示
///
/// 统一格式："{日期标签} 上午/下午H:mm"
///
/// 日期标签规则：
/// - 今天 → "今天"
/// - 昨天 → "昨天"
/// - 本周（2~6天前）→ "周X"
/// - 同年 → "MM/dd"
/// - 跨年 → "yy/MM/dd"（两位年，如 26/01/09）
class ChatTimeFormatter {
  ChatTimeFormatter._();

  static const _weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

  /// 完整格式："{日期标签} 上午/下午H:mm"
  static String format(DateTime serverTime) {
    final local = serverTime.toLocal();
    return '${_dayLabel(local)} ${_timeLabel(local)}';
  }

  /// 仅日期标签（今天/昨天/周X/MM-dd/yy-MM-dd）
  static String formatDateOnly(DateTime serverTime) {
    return _dayLabel(serverTime.toLocal());
  }

  /// 仅时间部分（上午/下午H:mm）
  static String formatTimeOnly(DateTime serverTime) {
    return _timeLabel(serverTime.toLocal());
  }

  /// 从 ISO 8601 字符串解析，失败时返回 null（不回退到本地时钟）
  static DateTime? tryParseServerTime(String? iso) {
    if (iso == null || iso.isEmpty) return null;
    return DateTime.tryParse(iso);
  }

  static String _dayLabel(DateTime local) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final msgDay = DateTime(local.year, local.month, local.day);
    final diff = today.difference(msgDay).inDays;

    if (diff == 0) return '今天';
    if (diff == 1) return '昨天';
    if (diff >= 2 && diff <= 6) return _weekdays[local.weekday - 1];

    final mm = local.month.toString().padLeft(2, '0');
    final dd = local.day.toString().padLeft(2, '0');
    if (local.year != now.year) {
      final yy = (local.year % 100).toString().padLeft(2, '0');
      return '$yy/$mm/$dd';
    }
    return '$mm/$dd';
  }

  static String _timeLabel(DateTime local) {
    final h = local.hour;
    final m = local.minute.toString().padLeft(2, '0');
    if (h == 0) return '上午12:$m';
    if (h < 12) return '上午$h:$m';
    if (h == 12) return '下午12:$m';
    return '下午${h - 12}:$m';
  }
}
