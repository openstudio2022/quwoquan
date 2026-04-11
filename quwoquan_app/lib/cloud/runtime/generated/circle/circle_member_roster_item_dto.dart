/// 圈子成员列表行投影（ListCircleMembers / Mock 富集字段）。
/// 合约：`quwoquan_service/contracts/metadata/social/circle/projections/circle_member_roster_row.yaml`
///
/// 对齐 [circleStatsMemberRowFromWireMap] 所读键，并保留 CircleMember 实体常见键。
class CircleMemberRosterItemDto {
  const CircleMemberRosterItemDto({
    required this.membershipId,
    required this.circleId,
    required this.userId,
    required this.role,
    required this.joinedAt,
    this.displayName,
    this.avatarUrl,
    this.worksCountLabel,
    this.fansCountLabel,
    this.likesCountLabel,
    this.isFollowed = false,
    this.lastActiveAt,
    this.contribution = 0,
  });

  final String membershipId;
  final String circleId;
  final String userId;
  final String role;
  final DateTime joinedAt;
  final String? displayName;
  final String? avatarUrl;
  final String? worksCountLabel;
  final String? fansCountLabel;
  final String? likesCountLabel;
  final bool isFollowed;
  final DateTime? lastActiveAt;
  final int contribution;

  factory CircleMemberRosterItemDto.fromMap(
    Map<String, dynamic> m, {
    String circleId = '',
  }) {
    final uid =
        (m['userId'] ?? m['id'] ?? m['_id'] ?? '').toString();
    final memId = (m['_id'] ?? m['id'] ?? uid).toString();
    return CircleMemberRosterItemDto(
      membershipId: memId.isNotEmpty ? memId : uid,
      circleId: (m['circleId'] ?? circleId).toString(),
      userId: uid,
      role: (m['role'] ?? 'member').toString(),
      joinedAt: _parseDateTime(m['joinedAt']),
      displayName: m['displayName'] as String? ?? m['name'] as String?,
      avatarUrl: m['avatarUrl'] as String? ?? m['avatar'] as String?,
      worksCountLabel: _label(m['worksCountLabel'], m['worksCount']),
      fansCountLabel: _label(m['fansCountLabel'], m['fansCount']),
      likesCountLabel: _label(m['likesCountLabel'], m['likesCount']),
      isFollowed: m['isFollowed'] as bool? ?? false,
      lastActiveAt: m['lastActiveAt'] != null
          ? _parseDateTime(m['lastActiveAt'])
          : null,
      contribution: (m['contribution'] as num?)?.toInt() ?? 0,
    );
  }

  Map<String, dynamic> toMap() => {
        'id': membershipId,
        'circleId': circleId,
        'userId': userId,
        'role': role,
        'joinedAt': joinedAt.toIso8601String(),
        if (displayName != null) 'displayName': displayName,
        if (avatarUrl != null) 'avatarUrl': avatarUrl,
        if (worksCountLabel != null) 'worksCountLabel': worksCountLabel,
        if (fansCountLabel != null) 'fansCountLabel': fansCountLabel,
        if (likesCountLabel != null) 'likesCountLabel': likesCountLabel,
        'isFollowed': isFollowed,
        if (lastActiveAt != null)
          'lastActiveAt': lastActiveAt!.toIso8601String(),
        'contribution': contribution,
      };

  static String? _label(dynamic a, dynamic b) {
    if (a != null) return a.toString();
    if (b != null) return b.toString();
    return null;
  }

  static DateTime _parseDateTime(dynamic v) {
    if (v is DateTime) return v;
    if (v is String) return DateTime.tryParse(v) ?? DateTime.now();
    return DateTime.now();
  }
}
