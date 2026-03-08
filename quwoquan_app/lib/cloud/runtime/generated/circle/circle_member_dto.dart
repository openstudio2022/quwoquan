/// 圈子成员 DTO。
///
/// 字段对齐：contracts/metadata/social/circle/fields.yaml CircleMember
class CircleMemberDto {
  final String id;
  final String circleId;
  final String userId;
  final String role;
  final DateTime joinedAt;
  final DateTime? lastActiveAt;
  final int contribution;

  const CircleMemberDto({
    required this.id,
    required this.circleId,
    required this.userId,
    required this.role,
    required this.joinedAt,
    this.lastActiveAt,
    this.contribution = 0,
  });

  factory CircleMemberDto.fromMap(Map<String, dynamic> m) {
    return CircleMemberDto(
      id: (m['_id'] ?? m['id'] ?? '').toString(),
      circleId: (m['circleId'] ?? '').toString(),
      userId: (m['userId'] ?? '').toString(),
      role: (m['role'] ?? 'member').toString(),
      joinedAt: _parseDateTime(m['joinedAt']),
      lastActiveAt: m['lastActiveAt'] != null
          ? _parseDateTime(m['lastActiveAt'])
          : null,
      contribution: (m['contribution'] as num?)?.toInt() ?? 0,
    );
  }

  Map<String, dynamic> toMap() => {
        'id': id,
        'circleId': circleId,
        'userId': userId,
        'role': role,
        'joinedAt': joinedAt.toIso8601String(),
        if (lastActiveAt != null)
          'lastActiveAt': lastActiveAt!.toIso8601String(),
        'contribution': contribution,
      };

  static DateTime _parseDateTime(dynamic v) {
    if (v is DateTime) return v;
    if (v is String) return DateTime.tryParse(v) ?? DateTime.now();
    return DateTime.now();
  }
}
