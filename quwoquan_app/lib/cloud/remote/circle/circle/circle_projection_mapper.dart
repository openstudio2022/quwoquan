import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_section_config_dto.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Circle pure-Dart 投影到 App DTO 的强类型防腐边界。
final class CircleProjectionMapper {
  const CircleProjectionMapper();

  static final DateTime _epochUtc = DateTime.fromMillisecondsSinceEpoch(
    0,
    isUtc: true,
  );

  CircleDto toDto(CircleProjection projection) {
    final createdAt = projection.createdAt ?? _epochUtc;
    return CircleDto(
      id: projection.circleId,
      name: projection.name,
      description: projection.description,
      rulesText: projection.rulesText,
      welcomeMessage: projection.welcomeMessage,
      coverUrl: projection.coverUrl,
      iconUrl: projection.iconUrl,
      ownerId: projection.ownerId,
      category: projection.category,
      tags: projection.tags,
      memberCount: projection.memberCount,
      postCount: projection.postCount,
      weeklyActiveCount: projection.weeklyActiveCount,
      status: projection.status,
      visibility: projection.visibility,
      joinPolicy: projection.joinPolicy,
      kind: projection.kind,
      displaySubjectType: projection.displaySubjectType,
      followEnabled: projection.followEnabled,
      defaultPublicGroupId: projection.defaultPublicGroupId,
      conversationId: projection.conversationId,
      autoSyncChat: projection.autoSyncChat,
      sectionConfig: projection.sectionConfig
          .map(
            (section) => CircleSectionConfigDto(
              sectionType: section.sectionType,
              visible: section.visible,
              order: section.order,
              customTitle: section.customTitle,
            ),
          )
          .toList(growable: false),
      storageUsedBytes: projection.storageUsedBytes,
      storageQuotaBytes: projection.storageQuotaBytes,
      domainId: projection.domainId,
      subCategory: projection.subCategory,
      createdAt: createdAt,
      updatedAt: projection.updatedAt ?? createdAt,
    );
  }
}
