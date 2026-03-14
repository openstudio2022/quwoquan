import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_section_config_dto.dart';

/// 圈子聚合根 DTO。
///
/// 字段对齐：contracts/metadata/social/circle/fields.yaml Circle
class CircleDto {
  final String id;
  final String name;
  final String? description;
  final String? coverUrl;
  final String ownerId;
  final String? category;
  final List<String> tags;
  final int memberCount;
  final int postCount;
  final int weeklyActiveCount;
  final String status;
  final String visibility;
  final String joinPolicy;
  final String? conversationId;
  final bool autoSyncChat;
  final List<CircleSectionConfigDto> sectionConfig;
  final int storageUsedBytes;
  final int storageQuotaBytes;
  final String? domainId;
  final String? subCategory;
  final DateTime createdAt;
  final DateTime updatedAt;

  const CircleDto({
    required this.id,
    required this.name,
    this.description,
    this.coverUrl,
    required this.ownerId,
    this.category,
    this.tags = const [],
    this.memberCount = 0,
    this.postCount = 0,
    this.weeklyActiveCount = 0,
    this.status = 'active',
    this.visibility = 'public',
    this.joinPolicy = 'open',
    this.conversationId,
    this.autoSyncChat = true,
    this.sectionConfig = const [],
    this.storageUsedBytes = 0,
    this.storageQuotaBytes = 1073741824,
    this.domainId,
    this.subCategory,
    required this.createdAt,
    required this.updatedAt,
  });

  factory CircleDto.fromMap(Map<String, dynamic> m) {
    return CircleDto(
      id: (m['_id'] ?? m['id'] ?? '').toString(),
      name: (m['name'] ?? '').toString(),
      description: m['description'] as String?,
      coverUrl: (m['coverUrl'] ?? m['cover']) as String?,
      ownerId: (m['ownerId'] ?? '').toString(),
      category: m['category'] ?? m['categoryId'] as String?,
      tags: (m['tags'] as List<dynamic>?)?.map((e) => e.toString()).toList() ??
          const [],
      memberCount: (m['memberCount'] as num?)?.toInt() ?? 0,
      postCount: (m['postCount'] as num?)?.toInt() ?? 0,
      weeklyActiveCount: (m['weeklyActiveCount'] as num?)?.toInt() ?? 0,
      status: (m['status'] ?? 'active').toString(),
      visibility: (m['visibility'] ?? 'public').toString(),
      joinPolicy: (m['joinPolicy'] ?? 'open').toString(),
      conversationId: m['conversationId'] as String?,
      autoSyncChat: m['autoSyncChat'] as bool? ?? true,
      sectionConfig: (m['sectionConfig'] as List<dynamic>?)
              ?.whereType<Map<String, dynamic>>()
              .map(CircleSectionConfigDto.fromMap)
              .toList() ??
          const [],
      storageUsedBytes: (m['storageUsedBytes'] as num?)?.toInt() ?? 0,
      storageQuotaBytes:
          (m['storageQuotaBytes'] as num?)?.toInt() ?? 1073741824,
      domainId: m['domainId'] as String?,
      subCategory: m['subCategory'] as String?,
      createdAt: _parseDateTime(m['createdAt']),
      updatedAt: _parseDateTime(m['updatedAt']),
    );
  }

  Map<String, dynamic> toMap() => {
        'id': id,
        'name': name,
        if (description != null) 'description': description,
        if (coverUrl != null) 'coverUrl': coverUrl,
        'ownerId': ownerId,
        if (category != null) 'category': category,
        'tags': tags,
        'memberCount': memberCount,
        'postCount': postCount,
        'weeklyActiveCount': weeklyActiveCount,
        'status': status,
        'visibility': visibility,
        'joinPolicy': joinPolicy,
        if (conversationId != null) 'conversationId': conversationId,
        'autoSyncChat': autoSyncChat,
        'sectionConfig': sectionConfig.map((s) => s.toMap()).toList(),
        'storageUsedBytes': storageUsedBytes,
        'storageQuotaBytes': storageQuotaBytes,
        if (domainId != null) 'domainId': domainId,
        if (subCategory != null) 'subCategory': subCategory,
        'createdAt': createdAt.toIso8601String(),
        'updatedAt': updatedAt.toIso8601String(),
      };

  static DateTime _parseDateTime(dynamic v) {
    if (v is DateTime) return v;
    if (v is String) return DateTime.tryParse(v) ?? DateTime.now();
    return DateTime.now();
  }

  CircleDto copyWith({
    String? id,
    String? name,
    String? description,
    String? coverUrl,
    String? ownerId,
    String? category,
    List<String>? tags,
    int? memberCount,
    int? postCount,
    int? weeklyActiveCount,
    String? status,
    String? visibility,
    String? joinPolicy,
    String? conversationId,
    bool? autoSyncChat,
    List<CircleSectionConfigDto>? sectionConfig,
    int? storageUsedBytes,
    int? storageQuotaBytes,
    String? domainId,
    String? subCategory,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) {
    return CircleDto(
      id: id ?? this.id,
      name: name ?? this.name,
      description: description ?? this.description,
      coverUrl: coverUrl ?? this.coverUrl,
      ownerId: ownerId ?? this.ownerId,
      category: category ?? this.category,
      tags: tags ?? this.tags,
      memberCount: memberCount ?? this.memberCount,
      postCount: postCount ?? this.postCount,
      weeklyActiveCount: weeklyActiveCount ?? this.weeklyActiveCount,
      status: status ?? this.status,
      visibility: visibility ?? this.visibility,
      joinPolicy: joinPolicy ?? this.joinPolicy,
      conversationId: conversationId ?? this.conversationId,
      autoSyncChat: autoSyncChat ?? this.autoSyncChat,
      sectionConfig: sectionConfig ?? this.sectionConfig,
      storageUsedBytes: storageUsedBytes ?? this.storageUsedBytes,
      storageQuotaBytes: storageQuotaBytes ?? this.storageQuotaBytes,
      domainId: domainId ?? this.domainId,
      subCategory: subCategory ?? this.subCategory,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
    );
  }
}
