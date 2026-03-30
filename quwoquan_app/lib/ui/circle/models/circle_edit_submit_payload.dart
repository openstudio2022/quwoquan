import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_section_config_dto.dart';

/// 圈子编辑页提交体；仅在调用 Repository 时转为 wire map。
class CircleEditSubmitPayload {
  const CircleEditSubmitPayload({
    required this.name,
    required this.description,
    required this.tags,
    required this.visibility,
    required this.joinPolicy,
    required this.autoSyncChat,
    required this.coverUrl,
    required this.avatarUrl,
    this.categoryId,
    required this.sectionConfig,
  });

  final String name;
  final String description;
  final List<String> tags;
  final String visibility;
  final String joinPolicy;
  final bool autoSyncChat;
  final String coverUrl;
  final String avatarUrl;
  final String? categoryId;
  final List<CircleSectionConfigDto> sectionConfig;

  Map<String, dynamic> toWire() {
    return <String, dynamic>{
      'name': name,
      'description': description,
      'tags': tags,
      'visibility': visibility,
      'joinPolicy': joinPolicy,
      'autoSyncChat': autoSyncChat,
      'coverUrl': coverUrl,
      'cover': coverUrl,
      'avatarUrl': avatarUrl,
      'avatar': avatarUrl,
      if (categoryId != null && categoryId!.isNotEmpty) 'categoryId': categoryId,
      if (categoryId != null && categoryId!.isNotEmpty) 'category': categoryId,
      'sectionConfig': sectionConfig.map((s) => s.toMap()).toList(growable: false),
    };
  }
}
