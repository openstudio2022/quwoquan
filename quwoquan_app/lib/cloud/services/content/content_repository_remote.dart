part of 'content_repository.dart';

class RemoteContentRepository
    implements
        ContentReadRepository,
        ContentWriteRepository,
        ContentEngagementRepository,
        ContentConfigRepository {
  RemoteContentRepository({
    required this._discoveryFeedQuery,
    CloudHttpClient? httpClient,
    String? baseUrl,
  }) : _httpClient = httpClient ?? CloudHttpClient(),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;
  final ContentDiscoveryFeedQuery _discoveryFeedQuery;

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: queryParameters);
  }

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

  @override
  Future<ContentAppConfigWire> getAppConfig() async {
    final uri = _uri(ContentApiMetadata.getAppConfigPath);
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.getAppConfig),
    );
    return ContentAppConfigWire.fromResponseObject(
      CloudResponseDecoder.asObject(
        decoded,
        context: ContentRequestPageIds.getAppConfig,
      ),
    );
  }

  @override
  Future<void> reportBehaviors({
    required List<ContentBehaviorBatchEventDto> events,
  }) async {
    final uri = _uri(ContentApiMetadata.reportBehaviorsPath);
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.reportBehaviors,
      ),
      body: <String, dynamic>{
        'events': events.map((e) => e.toRequestMap()).toList(growable: false),
      },
    );
  }

  @override
  Future<PostEngagementCounters> getCounters({required String postId}) async {
    final uri = _uri(ContentApiMetadata.getCountersPath(postId: postId));
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.getCounters),
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.getCounters,
    );
    return PostEngagementCounters.fromMap(obj);
  }

  @override
  Future<void> deletePost({
    required String postId,
    required String idempotencyKey,
  }) async {
    final normalizedPostId = postId.trim();
    final normalizedIdempotencyKey = idempotencyKey.trim();
    if (normalizedPostId.isEmpty || normalizedIdempotencyKey.isEmpty) {
      throw ArgumentError(
        'DeletePost requires postId and caller-owned idempotencyKey',
      );
    }
    final uri = _uri(
      ContentApiMetadata.deletePostPath(postId: normalizedPostId),
    );
    await _httpClient.deleteJson(
      uri,
      headers: <String, String>{
        ...CloudRequestHeaders.forPage(ContentRequestPageIds.deletePost),
        'Idempotency-Key': normalizedIdempotencyKey,
      },
    );
  }

  @override
  bool get requiresResolvedPersonaForMutations => true;
}
