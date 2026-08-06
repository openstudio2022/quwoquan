import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/domain/intersection_statement_synthesizer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 返回最强可展示证据组的稳定 kind，供跨页面高亮意图复用。
String? primaryIntersectionReasonKind(
  List<IntersectionReason>? reasons, {
  IntersectionTarget? contextObjectTarget,
}) {
  if (reasons == null || reasons.isEmpty) return null;
  final first = displayReadyIntersectionReason(
    reasons.first,
    contextObjectTarget: contextObjectTarget,
  );
  if (first == null) return null;
  final kind = resolvedIntersectionReasonKind(first).trim();
  return kind.isEmpty ? null : kind;
}
