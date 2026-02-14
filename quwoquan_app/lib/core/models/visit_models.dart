// 浏览信息模型：VisitTarget（访问对象）与 VisitRecord（单条访问记录）。
// 用于小趣基线：本地存储与 experienceLevel 派生，见 assistant-baseline spec。

/// 访问对象类型：页面型（如发现某 tab）或实体型（作者/圈子）。
enum VisitTargetType {
  page,
  entity,
}

/// 实体型访问对象的子类型。
enum VisitEntityKind {
  author,
  circle,
}

/// 被访问对象。支持页面型与实体型，具有唯一 [targetKey]。
class VisitTarget {
  const VisitTarget.page(String pageId)
      : type = VisitTargetType.page,
        pageId = pageId,
        entityKind = null,
        entityId = null;

  const VisitTarget.entity({
    required VisitEntityKind kind,
    required String id,
  })  : type = VisitTargetType.entity,
        pageId = null,
        entityKind = kind,
        entityId = id;

  final VisitTargetType type;
  final String? pageId;
  final VisitEntityKind? entityKind;
  final String? entityId;

  /// 唯一键：页面型为 `page_<id>`，实体型为 `entity_<kind>_<id>`。
  String get targetKey {
    if (type == VisitTargetType.page && pageId != null) {
      return 'page_$pageId';
    }
    if (type == VisitTargetType.entity &&
        entityKind != null &&
        entityId != null &&
        entityId!.isNotEmpty) {
      final kindStr = entityKind == VisitEntityKind.author ? 'author' : 'circle';
      return 'entity_${kindStr}_$entityId';
    }
    throw StateError('VisitTarget: missing pageId or entityKind/entityId');
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is VisitTarget && runtimeType == other.runtimeType && targetKey == other.targetKey;

  @override
  int get hashCode => targetKey.hashCode;
}

/// 单条访问记录，用于持久化与 experienceLevel 派生。
class VisitRecord {
  const VisitRecord({
    required this.targetKey,
    required this.firstSeenAt,
    required this.lastSeenAt,
    required this.visitCount,
    required this.count7d,
    required this.count30d,
    this.lastSeenTimestamps = const [],
  });

  final String targetKey;
  final DateTime firstSeenAt;
  final DateTime lastSeenAt;
  final int visitCount;
  /// 最近 7 天内访问次数（由写入时从 lastSeenTimestamps 维护）。
  final int count7d;
  /// 最近 30 天内访问次数。
  final int count30d;
  /// 最近若干次访问时间（ISO8601），用于派生 count7d/count30d，最多保留 [kMaxTimestamps] 条。
  final List<String> lastSeenTimestamps;

  static const int kMaxTimestamps = 30;

  VisitRecord copyWith({
    String? targetKey,
    DateTime? firstSeenAt,
    DateTime? lastSeenAt,
    int? visitCount,
    int? count7d,
    int? count30d,
    List<String>? lastSeenTimestamps,
  }) {
    return VisitRecord(
      targetKey: targetKey ?? this.targetKey,
      firstSeenAt: firstSeenAt ?? this.firstSeenAt,
      lastSeenAt: lastSeenAt ?? this.lastSeenAt,
      visitCount: visitCount ?? this.visitCount,
      count7d: count7d ?? this.count7d,
      count30d: count30d ?? this.count30d,
      lastSeenTimestamps: lastSeenTimestamps ?? this.lastSeenTimestamps,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
        'targetKey': targetKey,
        'firstSeenAt': firstSeenAt.toIso8601String(),
        'lastSeenAt': lastSeenAt.toIso8601String(),
        'visitCount': visitCount,
        'count7d': count7d,
        'count30d': count30d,
        'lastSeenTimestamps': lastSeenTimestamps,
      };

  factory VisitRecord.fromJson(Map<String, dynamic> json) {
    final list = json['lastSeenTimestamps'];
    return VisitRecord(
      targetKey: json['targetKey'] as String,
      firstSeenAt: DateTime.parse(json['firstSeenAt'] as String),
      lastSeenAt: DateTime.parse(json['lastSeenAt'] as String),
      visitCount: json['visitCount'] as int,
      count7d: json['count7d'] as int? ?? 0,
      count30d: json['count30d'] as int? ?? 0,
      lastSeenTimestamps: list is List<dynamic>
          ? list.map((e) => e as String).toList()
          : <String>[],
    );
  }
}

/// 体验等级：首次、再次、常用。由 VisitRecord 的 visitCount / count7d / count30d 派生。
enum ExperienceLevel {
  firstTime,
  returning,
  frequent,
}
