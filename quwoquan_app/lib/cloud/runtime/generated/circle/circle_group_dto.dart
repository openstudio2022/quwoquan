/// 圈内群组 / 组织节点 DTO。
///
/// 字段对齐：contracts/metadata/social/circle/fields.yaml CircleGroup
/// `circleName` 为搜索/快照等场景的展示扩展字段，非持久化实体列。
class CircleGroupDto {
  final String id;
  final String circleId;
  final String? parentGroupId;
  final String groupType;
  final String? nodeType;
  final String name;
  final String? description;
  final String visibility;
  final String joinPolicy;
  final String ownerUserId;
  final List<String> managerIds;
  final int memberCount;
  final String? conversationId;
  final bool storageEnabled;
  final bool noticeEnabled;
  final bool isDefaultPublicGroup;
  final DateTime? lastActiveAt;
  final String status;
  final DateTime createdAt;
  final DateTime updatedAt;

  /// 可选：圈子名称（wire 富集 / 本地快照搜索文案）。
  final String? circleName;

  const CircleGroupDto({
    required this.id,
    required this.circleId,
    this.parentGroupId,
    required this.groupType,
    this.nodeType,
    required this.name,
    this.description,
    required this.visibility,
    required this.joinPolicy,
    required this.ownerUserId,
    this.managerIds = const [],
    this.memberCount = 0,
    this.conversationId,
    this.storageEnabled = true,
    this.noticeEnabled = true,
    this.isDefaultPublicGroup = false,
    this.lastActiveAt,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
    this.circleName,
  });

  factory CircleGroupDto.fromMap(Map<String, dynamic> m) {
    final id = (m['_id'] ?? m['id'] ?? '').toString();
    return CircleGroupDto(
      id: id,
      circleId: (m['circleId'] ?? '').toString(),
      parentGroupId: m['parentGroupId']?.toString(),
      groupType: (m['groupType'] ?? 'public_group').toString(),
      nodeType: m['nodeType']?.toString(),
      name: (m['name'] ?? '').toString(),
      description: m['description'] as String?,
      visibility: (m['visibility'] ?? 'public').toString(),
      joinPolicy: (m['joinPolicy'] ?? 'apply_only').toString(),
      ownerUserId: (m['ownerUserId'] ?? '').toString(),
      managerIds: (m['managerIds'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList(growable: false) ??
          const [],
      memberCount: (m['memberCount'] as num?)?.toInt() ?? 0,
      conversationId: m['conversationId']?.toString(),
      storageEnabled: m['storageEnabled'] as bool? ?? true,
      noticeEnabled: m['noticeEnabled'] as bool? ?? true,
      isDefaultPublicGroup: m['isDefaultPublicGroup'] as bool? ?? false,
      lastActiveAt: _tryParseDateTime(m['lastActiveAt']),
      status: (m['status'] ?? 'active').toString(),
      createdAt: _parseDateTime(m['createdAt']),
      updatedAt: _parseDateTime(m['updatedAt']),
      circleName: m['circleName'] as String?,
    );
  }

  Map<String, dynamic> toMap() => {
        'id': id,
        '_id': id,
        'groupId': id,
        'circleId': circleId,
        if (parentGroupId != null) 'parentGroupId': parentGroupId,
        'groupType': groupType,
        if (nodeType != null) 'nodeType': nodeType,
        'name': name,
        if (description != null) 'description': description,
        'visibility': visibility,
        'joinPolicy': joinPolicy,
        'ownerUserId': ownerUserId,
        'managerIds': managerIds,
        'memberCount': memberCount,
        if (conversationId != null) 'conversationId': conversationId,
        'storageEnabled': storageEnabled,
        'noticeEnabled': noticeEnabled,
        'isDefaultPublicGroup': isDefaultPublicGroup,
        if (lastActiveAt != null)
          'lastActiveAt': lastActiveAt!.toIso8601String(),
        'status': status,
        'createdAt': createdAt.toIso8601String(),
        'updatedAt': updatedAt.toIso8601String(),
        if (circleName != null) 'circleName': circleName,
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
