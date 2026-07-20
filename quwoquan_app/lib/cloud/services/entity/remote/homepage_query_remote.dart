import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

enum HomepageQuerySurface { picker, detail, introduction }

typedef HomepageQueryInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      HomepageQuerySurface surface, {
      CloudOperationCancellationSignal? cancellation,
      DateTime? deadlineAt,
    });

/// 实体主页全部 commercial-ready 查询的唯一远端适配器。
final class RemoteHomepageQueryAdapter {
  const RemoteHomepageQueryAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final HomepageQueryInvocationContextFactory invocationContext;

  Future<HomepageSearchSlice> searchHomepages(
    HomepageSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) {
    return client.entityHomepageSearchHomepages(
      query,
      context: invocationContext(
        EntityRequestPageIds.searchHomepages,
        HomepageQuerySurface.picker,
        cancellation: cancellation,
        deadlineAt: deadlineAt,
      ),
    );
  }

  Future<HomepageDetailProjection> getHomepageDetail(String homepageId) {
    return client.entityHomepageGetHomepageDetail(
      HomepageByIdQuery(homepageId: homepageId),
      context: invocationContext(
        EntityRequestPageIds.getHomepageDetail,
        HomepageQuerySurface.detail,
      ),
    );
  }

  Future<HomepageShellProjection> getHomepageShell(String homepageId) {
    return client.entityHomepageGetHomepageShell(
      HomepageByIdQuery(homepageId: homepageId),
      context: invocationContext(
        EntityRequestPageIds.getHomepageShell,
        HomepageQuerySurface.detail,
      ),
    );
  }

  Future<HomepageIntroductionProjection> getHomepageIntroduction(
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

  Future<HomepageObjectPageBundleProjection> getObjectPageBundle(
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

  Future<HomepageReviewSummaryProjection> getHomepageReviewSummary(
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

  Future<HomepageImpactSummaryProjection> getEntityImpact(String homepageId) {
    return client.entityHomepageGetEntityImpact(
      HomepageByIdQuery(homepageId: homepageId),
      context: invocationContext(
        EntityRequestPageIds.getEntityImpact,
        HomepageQuerySurface.detail,
      ),
    );
  }

  Future<HomepageRelatedGroupsSlice> getHomepageRelatedGroups(
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
