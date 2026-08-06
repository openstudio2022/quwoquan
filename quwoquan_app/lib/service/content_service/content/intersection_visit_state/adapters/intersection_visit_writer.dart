import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef IntersectionVisitInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// IntersectionVisitState 对象的 canonical typed 写面
/// （quwoquan_service/services/content-service/contracts/content/intersection_visit_state/operations.yaml）。
///
/// 推进「我的交集」已读水位并清零未读红点；[dimension] 为空推进全部维度。
/// 服务端水位以 $max 单调合并，任意重放自然收敛（无需 Idempotency-Key）。
abstract interface class IntersectionVisitWriter {
  Future<void> markIntersectionsVisited({IntersectionDimension? dimension});
}

final class RemoteIntersectionVisitWriter implements IntersectionVisitWriter {
  const RemoteIntersectionVisitWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final IntersectionVisitInvocationContextFactory invocationContext;

  @override
  Future<void> markIntersectionsVisited({
    IntersectionDimension? dimension,
  }) async {
    await client.contentIntersectionVisitStateMarkIntersectionsVisited(
      MarkIntersectionsVisitedRequest(dimension: dimension),
      context: invocationContext(
        ContentRequestPageIds.markIntersectionsVisited,
      ),
    );
  }
}
