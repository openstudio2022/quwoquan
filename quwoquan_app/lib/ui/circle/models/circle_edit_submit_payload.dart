import 'package:quwoquan_cloud_contracts/generated/circle_contracts.dart';

/// 圈子板块编辑值；只承载页面编辑状态，不承担 wire 解码。
final class CircleSectionEditValue {
  const CircleSectionEditValue({
    required this.sectionType,
    required this.visible,
    required this.order,
    this.customTitle,
  });

  factory CircleSectionEditValue.fromWire(CircleSectionConfig wire) =>
      CircleSectionEditValue(
        sectionType: wire.sectionType,
        visible: wire.visible,
        order: wire.order,
        customTitle: wire.customTitle,
      );

  final CircleSectionType sectionType;
  final bool visible;
  final int order;
  final String? customTitle;

  CircleSectionEditValue copyWith({
    CircleSectionType? sectionType,
    bool? visible,
    int? order,
    String? customTitle,
  }) => CircleSectionEditValue(
    sectionType: sectionType ?? this.sectionType,
    visible: visible ?? this.visible,
    order: order ?? this.order,
    customTitle: customTitle ?? this.customTitle,
  );
}

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
  final CircleVisibility visibility;
  final CircleJoinPolicy joinPolicy;
  final bool autoSyncChat;
  final String coverUrl;
  final String avatarUrl;
  final String? categoryId;
  final List<CircleSectionEditValue> sectionConfig;

  CreateCircleCommand toCreateCommand() => CreateCircleCommand(
    name: name,
    description: description,
    rulesText: rulesText,
    welcomeMessage: welcomeMessage,
    coverUrl: coverUrl,
    iconUrl: avatarUrl,
    category: categoryId,
    tags: tags,
    visibility: visibility.wireName,
    joinPolicy: joinPolicy.wireName,
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
    visibility: visibility.wireName,
    joinPolicy: joinPolicy.wireName,
    autoSyncChat: autoSyncChat,
  );

  UpdateCircleSectionsCommand toSectionsCommand(String circleId) =>
      UpdateCircleSectionsCommand(
        circleId: circleId,
        sections: sectionConfig
            .map(
              (section) => CircleSectionConfig(
                sectionType: section.sectionType,
                visible: section.visible,
                order: section.order,
                customTitle: section.customTitle,
              ),
            )
            .toList(growable: false),
      );
}
