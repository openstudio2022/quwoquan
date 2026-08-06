import 'package:quwoquan_app/runtime/transport/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_operation_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

enum HomepageQuerySurface { detail, introduction, search }

typedef HomepageQueryInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      HomepageQuerySurface surface, {
      CloudOperationCancellationSignal? cancellation,
      DateTime? deadlineAt,
    });

/// Homepage 对象 generated 查询的唯一 production owner。
final class RemoteHomepageQueryAdapter
    implements HomepageQueryFacet, HomepageIntroductionQuery {
  const RemoteHomepageQueryAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final HomepageQueryInvocationContextFactory invocationContext;

  @override
  Future<HomepageSearchSlice> searchHomepages(
    HomepageSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) {
    return client.entityHomepageSearchHomepages(
      query,
      context: invocationContext(
        EntityRequestPageIds.searchHomepages,
        HomepageQuerySurface.search,
        cancellation: cancellation,
        deadlineAt: deadlineAt,
      ),
    );
  }

  @override
  Future<HomepageDetailView> getHomepageDetail(String homepageId) {
    return client.entityHomepageGetHomepageDetail(
      HomepageByIdQuery(homepageId: homepageId),
      context: invocationContext(
        EntityRequestPageIds.getHomepageDetail,
        HomepageQuerySurface.detail,
      ),
    );
  }

  @override
  Future<HomepageShellView> getHomepageShell(String homepageId) {
    return client.entityHomepageGetHomepageShell(
      HomepageByIdQuery(homepageId: homepageId),
      context: invocationContext(
        EntityRequestPageIds.getHomepageShell,
        HomepageQuerySurface.detail,
      ),
    );
  }

  @override
  Future<HomepageIntroduction> getHomepageIntroduction(
    String homepageId, {
    CloudOperationCancellationSignal? cancellation,
  }) {
    return client.entityHomepageGetHomepageIntroduction(
      HomepageByIdQuery(homepageId: homepageId),
      context: invocationContext(
        EntityRequestPageIds.getHomepageIntroduction,
        HomepageQuerySurface.introduction,
        cancellation: cancellation,
      ),
    );
  }

  @override
  Future<ObjectPageBundle> getObjectPageBundle(
    HomepageObjectPageBundleQuery query,
  ) {
    return client.entityHomepageGetObjectPageBundle(
      query,
      context: invocationContext(
        EntityRequestPageIds.getObjectPageBundle,
        HomepageQuerySurface.detail,
      ),
    );
  }

  @override
  Future<HomepageReviewSummaryView> getHomepageReviewSummary(
    String homepageId,
  ) {
    return client.entityHomepageGetHomepageReviewSummary(
      HomepageByIdQuery(homepageId: homepageId),
      context: invocationContext(
        EntityRequestPageIds.getHomepageReviewSummary,
        HomepageQuerySurface.detail,
      ),
    );
  }

  @override
  Future<EntityImpactSummary> getEntityImpact(String homepageId) {
    return client.entityHomepageGetEntityImpact(
      HomepageByIdQuery(homepageId: homepageId),
      context: invocationContext(
        EntityRequestPageIds.getEntityImpact,
        HomepageQuerySurface.detail,
      ),
    );
  }

  @override
  Future<HomepageRelatedGroupSummaryView> getHomepageRelatedGroups(
    String homepageId,
  ) {
    return client.entityHomepageGetHomepageRelatedGroups(
      HomepageByIdQuery(homepageId: homepageId),
      context: invocationContext(
        EntityRequestPageIds.getHomepageRelatedGroups,
        HomepageQuerySurface.detail,
      ),
    );
  }
}
