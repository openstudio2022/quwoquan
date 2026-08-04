part of 'content_repository.dart';

class RemoteContentRepository implements ContentReadRepository {
  RemoteContentRepository({required this._discoveryFeedQuery});

  final ContentDiscoveryFeedQuery _discoveryFeedQuery;

  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) {
    return _discoveryFeedQuery.listDiscoveryFeedPage(
      category: category,
      channelId: channelId,
      identity: identity,
      type: type,
      subCategory: subCategory,
      limit: limit,
      cursor: cursor,
      sort: sort,
      sessionId: sessionId,
      feedRequestId: feedRequestId,
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
  }

  @override
  Future<List<ContentPostViewData>> listDiscoveryFeed({
    required String category,
    String? identity,
    String? type,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
  }) async {
    final page = await listDiscoveryFeedPage(
      category: category,
      identity: identity,
      type: type,
      subCategory: subCategory,
      limit: limit,
      cursor: cursor,
      sort: sort,
    );
    return page.items;
  }

  @override
  Future<ContentPostDetailPayload> getPost({
    required String postId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    throw UnsupportedError(
      'GetPost must use ContentPostDetailReader / GeneratedCloudOperationClient',
    );
  }

  @override
  Future<CursorPage<ContentPostViewData>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    throw UnsupportedError(
      'ListUserPosts must use ContentAuthorPostsReader / GeneratedCloudOperationClient',
    );
  }
}
