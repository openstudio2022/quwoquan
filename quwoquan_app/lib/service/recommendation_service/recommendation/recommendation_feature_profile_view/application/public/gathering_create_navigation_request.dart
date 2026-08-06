import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;

final class GatheringCreateSourceReference {
  const GatheringCreateSourceReference({
    required this.sourceRef,
    required this.objectId,
    required this.objectKind,
    required this.routeId,
  });

  final String sourceRef;
  final String objectId;
  final String objectKind;
  final String routeId;
}

final class GatheringCreateTargetObject {
  const GatheringCreateTargetObject({
    required this.objectId,
    required this.objectKind,
    required this.objectName,
    required this.routeId,
  });

  final String objectId;
  final String objectKind;
  final String objectName;
  final String routeId;
}

final class GatheringCreateIntersectionContext {
  const GatheringCreateIntersectionContext({
    required this.intersectionId,
    required this.dimension,
    required this.intersectionClass,
  });

  final String intersectionId;
  final String dimension;
  final String intersectionClass;
}

final class GatheringCreateEvidenceContext {
  const GatheringCreateEvidenceContext({
    required this.evidenceId,
    required this.sourceRef,
    required this.tagRefs,
  });

  final String evidenceId;
  final String sourceRef;
  final List<String> tagRefs;
}

/// Recommendation 发起 Gathering 时交给 Circle composer 的 typed 导航请求。
///
/// 只携带 canonical reference 与归因，不创建 Gathering 或普通 Conversation。
final class GatheringCreateNavigationRequest {
  const GatheringCreateNavigationRequest({
    required this.actionKey,
    required this.actionLabel,
    required this.sourceRefs,
    required this.targetObject,
    required this.intersection,
    required this.evidence,
    required this.referralSource,
  });

  final String actionKey;
  final String actionLabel;
  final List<GatheringCreateSourceReference> sourceRefs;
  final GatheringCreateTargetObject targetObject;
  final GatheringCreateIntersectionContext intersection;
  final GatheringCreateEvidenceContext evidence;
  final ReferralSource referralSource;
}
