import 'package:meta/meta.dart';

/// 评论计数可解释增量（GetCommentCountsDelta 响应）。
///
/// 语义为半开区间 `(since, watermark]`：
/// - [createdSinceCount]：`createdAt ∈ (since, watermark]` 的评论数（不论其后是否被删除）；
/// - [deletedSinceCount]：`status=deleted` 且 `deletedAt ∈ (since, watermark]` 的评论数；
/// - [currentTotal]：权威「当前非删」评论总数；
/// - [watermark]：本次查询时刻，作为下次 `since` 基线，保证相邻 delta 不重不漏；
/// - [since]：本次查询下界；为 null 表示首同步（无下界）。
///
/// 端侧据此向用户解释「较上次基线 新增 N 条 / 删除 M 条」，避免计数默默跳变。
@immutable
class CommentCountsDelta {
  const CommentCountsDelta({
    required this.createdSinceCount,
    required this.deletedSinceCount,
    required this.currentTotal,
    required this.watermark,
    this.since,
  });

  final int createdSinceCount;
  final int deletedSinceCount;
  final int currentTotal;
  final DateTime watermark;
  final DateTime? since;

  /// 区间内是否存在可解释变化（新增或删除任一非零）。
  bool get hasChanges => createdSinceCount > 0 || deletedSinceCount > 0;

  /// 净变化量（新增 - 删除），可为负，用于展示与诊断。
  int get netChange => createdSinceCount - deletedSinceCount;

  factory CommentCountsDelta.fromMap(Map<String, dynamic> m) {
    int n(Object? v) => (v is num) ? v.toInt() : int.tryParse('$v') ?? 0;
    DateTime? parseTime(Object? v) {
      final raw = v?.toString();
      if (raw == null || raw.isEmpty) return null;
      return DateTime.tryParse(raw);
    }

    return CommentCountsDelta(
      createdSinceCount: n(m['createdSinceCount']),
      deletedSinceCount: n(m['deletedSinceCount']),
      currentTotal: n(m['currentTotal']),
      // watermark 由服务端权威下发；缺失时退化为本地时刻，保证字段非空。
      watermark: parseTime(m['watermark']) ?? DateTime.now().toUtc(),
      since: parseTime(m['since']),
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is CommentCountsDelta &&
          runtimeType == other.runtimeType &&
          createdSinceCount == other.createdSinceCount &&
          deletedSinceCount == other.deletedSinceCount &&
          currentTotal == other.currentTotal &&
          watermark == other.watermark &&
          since == other.since;

  @override
  int get hashCode => Object.hash(
        createdSinceCount,
        deletedSinceCount,
        currentTotal,
        watermark,
        since,
      );
}
