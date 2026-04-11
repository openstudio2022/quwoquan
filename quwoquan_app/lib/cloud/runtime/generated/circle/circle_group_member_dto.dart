/// 群组成员 / 入群申请 DTO。
///
/// 字段对齐：contracts/metadata/social/circle/fields.yaml CircleGroupMember
class CircleGroupMemberDto {
  final String id;
  final String groupId;
  final String circleId;
  final String userId;
  final String role;
  final String status;
  final DateTime? joinedAt;
  final String? invitedByUserId;
  final DateTime? decidedAt;
  final DateTime createdAt;
  final DateTime updatedAt;

  const CircleGroupMemberDto({
    required this.id,
    required this.groupId,
    required this.circleId,
    required this.userId,
    required this.role,
    required this.status,
    this.joinedAt,
    this.invitedByUserId,
    this.decidedAt,
    required this.createdAt,
    required this.updatedAt,
  });

  factory CircleGroupMemberDto.fromMap(Map<String, dynamic> m) {
    final id = (m['_id'] ?? m['id'] ?? '').toString();
    return CircleGroupMemberDto(
      id: id,
      groupId: (m['groupId'] ?? '').toString(),
      circleId: (m['circleId'] ?? '').toString(),
      userId: (m['userId'] ?? '').toString(),
      role: (m['role'] ?? 'member').toString(),
      status: (m['status'] ?? 'pending').toString(),
      joinedAt: _tryParseDateTime(m['joinedAt']),
      invitedByUserId: m['invitedByUserId']?.toString(),
      decidedAt: _tryParseDateTime(m['decidedAt']),
      createdAt: _parseDateTime(m['createdAt']),
      updatedAt: _parseDateTime(m['updatedAt']),
    );
  }

  Map<String, dynamic> toMap() => {
        'id': id,
        '_id': id,
        'groupId': groupId,
        'circleId': circleId,
        'userId': userId,
        'role': role,
        'status': status,
        if (joinedAt != null) 'joinedAt': joinedAt!.toIso8601String(),
        if (invitedByUserId != null) 'invitedByUserId': invitedByUserId,
        if (decidedAt != null) 'decidedAt': decidedAt!.toIso8601String(),
        'createdAt': createdAt.toIso8601String(),
        'updatedAt': updatedAt.toIso8601String(),
      };

  static DateTime _parseDateTime(dynamic v) {
    if (v is DateTime) return v;
    if (v is String) return DateTime.tryParse(v) ?? DateTime.now();
    return DateTime.now();
  }

  static DateTime? _tryParseDateTime(dynamic v) {
    if (v == null) return null;
    if (v is DateTime) return v;
    if (v is String) return DateTime.tryParse(v);
    return null;
  }
}
