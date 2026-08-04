import 'package:quwoquan_app/cloud/runtime/cloud_api_query_defaults.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/domain/intersection_fact_items.dart';

typedef IntersectionInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// 交集读面。production 组合根只装配 [RemoteIntersectionRepository]；
/// alpha/test adapter 位于独立 runner，不进入生产可达图。
abstract class IntersectionRepository {
  Future<IntersectionInboxSummary> getMyIntersectionSummary();

  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = CloudApiQueryDefaults.intersectionListLimit,
  });

  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = CloudApiQueryDefaults.objectIntersectionsLimit,
  });
}

class RemoteIntersectionRepository implements IntersectionRepository {
  const RemoteIntersectionRepository({
    required this.client,
    required this.myIntersectionsInvocationContext,
    required this.objectIntersectionsInvocationContext,
  });

  final GeneratedCloudOperationClient client;
  final IntersectionInvocationContextFactory myIntersectionsInvocationContext;
  final IntersectionInvocationContextFactory
  objectIntersectionsInvocationContext;

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    return client.contentIntersectionVisitStateGetMyIntersectionSummary(
      const GetMyIntersectionSummaryQuery(),
      context: myIntersectionsInvocationContext(
        ContentRequestPageIds.getMyIntersectionSummary,
      ),
    );
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = CloudApiQueryDefaults.intersectionListLimit,
  }) async {
    final page = await client.contentIntersectionVisitStateListMyIntersections(
      ListMyIntersectionsQuery(
        dimension: dimension?.trim().isEmpty == true ? null : dimension?.trim(),
        filter: filter?.trim().isEmpty == true ? null : filter?.trim(),
        sourceRef: sourceRef?.trim().isEmpty == true ? null : sourceRef?.trim(),
        timeBucket: timeBucket?.trim().isEmpty == true
            ? null
            : timeBucket?.trim(),
        cursor: cursor?.trim().isEmpty == true ? null : cursor?.trim(),
        limit: limit,
      ),
      context: myIntersectionsInvocationContext(
        ContentRequestPageIds.listMyIntersections,
      ),
    );
    return filterDefaultInboxLifecycle(page.items);
  }

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = CloudApiQueryDefaults.objectIntersectionsLimit,
  }) async {
    final page = await client.contentIntersectionVisitStateGetObjectIntersections(
      GetObjectIntersectionsQuery(
        objectId: objectId.trim(),
        objectType: objectType.trim().isEmpty ? null : objectType.trim(),
        limit: limit,
      ),
      context: objectIntersectionsInvocationContext(
        ContentRequestPageIds.getObjectIntersections,
      ),
    );
    return page.items;
  }
}
