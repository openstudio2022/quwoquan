import 'package:quwoquan_app/runtime/transport/cloud_api_query_defaults.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/application/public/intersection_lifecycle_filter.dart';

typedef IntersectionInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// IntersectionVisitState 读面。production 组合根只装配
/// [RemoteIntersectionRepository]；
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

  static const int _maxInboxPages = 20;

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
    final normalizedDimension = dimension?.trim();
    final normalizedFilter = filter?.trim();
    final normalizedSourceRef = sourceRef?.trim();
    final normalizedTimeBucket = timeBucket?.trim();
    var nextCursor = cursor?.trim() ?? '';
    final seenCursors = <String>{if (nextCursor.isNotEmpty) nextCursor};
    final seenIntersectionIds = <String>{};
    final items = <IntersectionReason>[];

    for (var pageIndex = 0; pageIndex < _maxInboxPages; pageIndex += 1) {
      final page = await client
          .contentIntersectionVisitStateListMyIntersections(
            ListMyIntersectionsQuery(
              dimension: normalizedDimension?.isEmpty == true
                  ? null
                  : normalizedDimension,
              filter: normalizedFilter?.isEmpty == true
                  ? null
                  : normalizedFilter,
              sourceRef: normalizedSourceRef?.isEmpty == true
                  ? null
                  : normalizedSourceRef,
              timeBucket: normalizedTimeBucket?.isEmpty == true
                  ? null
                  : normalizedTimeBucket,
              cursor: nextCursor.isEmpty ? null : nextCursor,
              limit: limit,
            ),
            context: myIntersectionsInvocationContext(
              ContentRequestPageIds.listMyIntersections,
            ),
          );
      for (final item in filterDefaultInboxLifecycle(page.items)) {
        final identity = item.intersectionId.trim();
        if (identity.isEmpty || !seenIntersectionIds.add(identity)) {
          throw StateError(
            'ListMyIntersections returned an empty or duplicate identity',
          );
        }
        items.add(item);
      }
      if (!page.hasMore) {
        return List<IntersectionReason>.unmodifiable(items);
      }
      final candidate = page.nextCursor?.trim() ?? '';
      if (candidate.isEmpty || !seenCursors.add(candidate)) {
        throw StateError(
          'ListMyIntersections returned an invalid cursor progression',
        );
      }
      nextCursor = candidate;
    }
    throw StateError(
      'ListMyIntersections exceeded the bounded pagination window',
    );
  }

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = CloudApiQueryDefaults.objectIntersectionsLimit,
  }) async {
    final page = await client
        .contentIntersectionVisitStateGetObjectIntersections(
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
