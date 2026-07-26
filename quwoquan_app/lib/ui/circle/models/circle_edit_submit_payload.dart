import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_section_config_dto.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 圈子编辑页强类型提交体；页面不接触动态 wire map。
class CircleEditSubmitPayload {
  const CircleEditSubmitPayload({
    required this.name,
    required this.description,
    required this.rulesText,
    required this.welcomeMessage,
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
  final String rulesText;
  final String welcomeMessage;
  final List<String> tags;
  final String visibility;
  final String joinPolicy;
  final bool autoSyncChat;
  final String coverUrl;
  final String avatarUrl;
  final String? categoryId;
  final List<CircleSectionConfigDto> sectionConfig;

  CreateCircleCommand toCreateCommand() => CreateCircleCommand(
    name: name,
    description: description,
    rulesText: rulesText,
    welcomeMessage: welcomeMessage,
    coverUrl: coverUrl,
    iconUrl: avatarUrl,
    category: categoryId,
    tags: tags,
    visibility: visibility,
    joinPolicy: joinPolicy,
    autoSyncChat: autoSyncChat,
  );

  UpdateCircleCommand toUpdateCommand(String circleId) => UpdateCircleCommand(
    circleId: circleId,
    name: name,
    description: description,
    rulesText: rulesText,
    welcomeMessage: welcomeMessage,
    coverUrl: coverUrl,
    iconUrl: avatarUrl,
    category: categoryId,
    tags: tags,
    visibility: visibility,
    joinPolicy: joinPolicy,
    autoSyncChat: autoSyncChat,
  );

  UpdateCircleSectionsCommand toSectionsCommand(String circleId) =>
      UpdateCircleSectionsCommand(
        circleId: circleId,
        sections: sectionConfig
            .map(
              (section) => CircleSectionConfigInput(
                sectionType: section.sectionType,
                visible: section.visible,
                order: section.order,
                customTitle: section.customTitle,
              ),
            )
            .toList(growable: false),
      );
}
