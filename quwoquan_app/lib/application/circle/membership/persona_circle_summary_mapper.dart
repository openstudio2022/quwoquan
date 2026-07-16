import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// PersonaCircleReader projection 到页面只读模型的单向映射。
CircleDto circleDtoFromPersonaCircleSummary(PersonaCircleSummary summary) =>
    CircleDto(
      id: summary.circleId,
      name: summary.name,
      description: summary.description,
      coverUrl: summary.coverUrl,
      iconUrl: summary.iconUrl,
      ownerId: summary.ownerPersonaId,
      category: summary.category,
      tags: summary.tags,
      memberCount: summary.memberCount,
      postCount: summary.postCount,
      weeklyActiveCount: summary.weeklyActiveCount,
      status: summary.state,
      visibility: summary.visibility,
      joinPolicy: summary.joinPolicy,
      kind: summary.kind,
      displaySubjectType: summary.displaySubjectType,
      followEnabled: summary.followEnabled,
      defaultPublicGroupId: summary.defaultPublicGroupId,
      subCategory: summary.subCategory,
      createdAt: summary.createdAt,
      updatedAt: summary.updatedAt,
    );
