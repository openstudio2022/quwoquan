import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/formatters/chat_time_formatter.dart';

void main() {
  // 与实现同源的星期表：断言的是「weekday-1 索引到中文星期」这条映射本身。
  const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

  /// 今天零点起算的当日时刻，避免用 Duration 做跨 DST 的日期算术。
  DateTime todayAt(int hour, int minute) {
    final now = DateTime.now();
    return DateTime(now.year, now.month, now.day, hour, minute);
  }

  DateTime daysAgoAt(int days, int hour, int minute) {
    final now = DateTime.now();
    return DateTime(now.year, now.month, now.day - days, hour, minute);
  }

  /// 与今天相距 6 天以上、但仍落在同一自然年内的日期。
  /// 上半年取当年 12/15（未来向），下半年取当年 1/15（过去向）——
  /// 两侧都不会命中「今天/昨天/前天/本周」分支，且年份恒等于 now.year。
  DateTime sameYearFarDay() {
    final now = DateTime.now();
    return now.month <= 6
        ? DateTime(now.year, 12, 15, 10, 30)
        : DateTime(now.year, 1, 15, 10, 30);
  }

  group('ChatTimeFormatter._timeLabel — 12 小时制上午/下午边界', () {
    test('零点归为「上午12」而非「上午0」', () {
      expect(ChatTimeFormatter.formatTimeOnly(todayAt(0, 7)), '上午12:07');
    });

    test('正午 12 点归为「下午12」，11 点仍为上午', () {
      expect(ChatTimeFormatter.formatTimeOnly(todayAt(11, 59)), '上午11:59');
      expect(ChatTimeFormatter.formatTimeOnly(todayAt(12, 0)), '下午12:00');
    });

    test('13 点后减 12 小时展示，分钟补零', () {
      expect(ChatTimeFormatter.formatTimeOnly(todayAt(13, 5)), '下午1:05');
      expect(ChatTimeFormatter.formatTimeOnly(todayAt(23, 30)), '下午11:30');
    });
  });

  group('ChatTimeFormatter._dayLabel — 日期标签降级链', () {
    test('今天/昨天使用相对词', () {
      expect(ChatTimeFormatter.formatDateOnly(todayAt(9, 0)), '今天');
      expect(ChatTimeFormatter.formatDateOnly(daysAgoAt(1, 9, 0)), '昨天');
    });

    test('2~6 天内使用中文星期', () {
      final day = daysAgoAt(3, 10, 30);
      expect(
        ChatTimeFormatter.formatDateOnly(day),
        weekdays[day.weekday - 1],
      );
    });

    test('超过 6 天但同年使用 MM/dd（月日补零）', () {
      final day = sameYearFarDay();
      final mm = day.month.toString().padLeft(2, '0');
      final dd = day.day.toString().padLeft(2, '0');
      expect(ChatTimeFormatter.formatDateOnly(day), '$mm/$dd');
    });

    test('跨年补两位年份 yy/MM/dd', () {
      final now = DateTime.now();
      final day = DateTime(now.year - 3, 5, 6, 10, 30);
      final yy = (day.year % 100).toString().padLeft(2, '0');
      expect(ChatTimeFormatter.formatDateOnly(day), '$yy/05/06');
    });
  });

  test('ChatTimeFormatter.format — 日期标签与时间标签以空格拼接', () {
    expect(ChatTimeFormatter.format(todayAt(14, 8)), '今天 下午2:08');
  });

  group('ChatTimeFormatter.formatForConversationList — 当日时段前缀', () {
    test('凌晨 [0,6)，其中零点显示为 12', () {
      expect(
        ChatTimeFormatter.formatForConversationList(todayAt(0, 15)),
        '凌晨12:15',
      );
      expect(
        ChatTimeFormatter.formatForConversationList(todayAt(5, 59)),
        '凌晨5:59',
      );
    });

    test('上午 [6,12)、中午恰好 12 点', () {
      expect(
        ChatTimeFormatter.formatForConversationList(todayAt(6, 0)),
        '上午6:00',
      );
      expect(
        ChatTimeFormatter.formatForConversationList(todayAt(12, 30)),
        '中午12:30',
      );
    });

    test('下午 (12,18)、晚上 [18,24)', () {
      expect(
        ChatTimeFormatter.formatForConversationList(todayAt(15, 4)),
        '下午3:04',
      );
      expect(
        ChatTimeFormatter.formatForConversationList(todayAt(21, 0)),
        '晚上9:00',
      );
    });

    test('昨天/前天只给相对词，不带时间', () {
      expect(
        ChatTimeFormatter.formatForConversationList(daysAgoAt(1, 23, 59)),
        '昨天',
      );
      expect(
        ChatTimeFormatter.formatForConversationList(daysAgoAt(2, 8, 0)),
        '前天',
      );
    });

    test('同年更早用「M月d日」，跨年补「y年」', () {
      final day = sameYearFarDay();
      expect(
        ChatTimeFormatter.formatForConversationList(day),
        '${day.month}月${day.day}日',
      );

      final now = DateTime.now();
      final older = DateTime(now.year - 2, 3, 9, 10, 30);
      expect(
        ChatTimeFormatter.formatForConversationList(older),
        '${older.year}年3月9日',
      );
    });
  });

  group('ChatTimeFormatter.tryParseServerTime — 缺席与失败不塌陷为本地时钟', () {
    test('null 与空串返回 null', () {
      expect(ChatTimeFormatter.tryParseServerTime(null), isNull);
      expect(ChatTimeFormatter.tryParseServerTime(''), isNull);
    });

    test('非法字符串返回 null，不回退到 DateTime.now()', () {
      expect(ChatTimeFormatter.tryParseServerTime('not-a-timestamp'), isNull);
    });

    test('合法 ISO 8601 保留 UTC 瞬时值', () {
      final parsed = ChatTimeFormatter.tryParseServerTime(
        '2026-02-03T04:05:06Z',
      );
      expect(parsed, isNotNull);
      expect(
        parsed!.toUtc(),
        DateTime.utc(2026, 2, 3, 4, 5, 6),
      );
    });
  });
}
