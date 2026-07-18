part of 'content_repository.dart';

PostBaseDto _postBaseDtoFromContentWire(Map<String, dynamic> obj) {
  final nested = obj['post'];
  if (nested is Map) {
    return postBaseDtoFromMap(Map<String, dynamic>.from(nested));
  }
  return postBaseDtoFromMap(obj);
}

class RemoteContentRepository
    implements
        ContentReadRepository,
        ContentWriteRepository,
        ContentEngagementRepository,
        ContentConfigRepository {
  RemoteContentRepository({CloudHttpClient? httpClient, String? baseUrl})
    : _httpClient = httpClient ?? CloudHttpClient(),
      _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: queryParameters);
  }

  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
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
  }) async {
    final resolvedIdentity = identity ?? _mapCategoryToIdentity(category);
    final resolvedType = _normalizeFeedType(
      type ?? _mapCategoryToFeedType(category),
    );
    final query = <String, String>{};
    final keys = GeneratedPostRuntimeMetadata.feedQueryParams;
    if (keys.contains('identity') &&
        resolvedIdentity != null &&
        resolvedIdentity.isNotEmpty) {
      query['identity'] = resolvedIdentity;
    }
    if (keys.contains('type') &&
        resolvedType != null &&
        resolvedType.isNotEmpty &&
        !(resolvedIdentity == 'moment' && (type == null || type.isEmpty))) {
      query['type'] = resolvedType;
    }
    if (keys.contains('cursor') && cursor?.isNotEmpty == true) {
      query['cursor'] = cursor!;
    }
    if (keys.contains('sort') && sort.trim().isNotEmpty) {
      query['sort'] = sort.trim();
    }
    if (keys.contains('limit')) {
      query['limit'] = '$limit';
    }
    if (keys.contains('subCategory') && subCategory?.isNotEmpty == true) {
      query['subCategory'] = subCategory!;
    }
    if (sessionId?.isNotEmpty == true) {
      query['sessionId'] = sessionId!;
    }
    if (feedRequestId?.isNotEmpty == true) {
      query['feedRequestId'] = feedRequestId!;
    }
    final uri = _uri(ContentApiMetadata.getFeedPath, queryParameters: query);
    final decoded = cancellation == null
        ? await _httpClient.getJson(
            uri,
            headers: CloudRequestHeaders.forPage(ContentRequestPageIds.getFeed),
          )
        : await _httpClient.getJsonAbortable(
            uri,
            gatewayOrigin: Uri.parse(_baseUrl),
            headers: CloudRequestHeaders.forPage(ContentRequestPageIds.getFeed),
            cancellation: cancellation,
          );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.getFeed,
    );
    final rawPage = CloudResponseDecoder.asCursorPage(
      obj,
      context: ContentRequestPageIds.getFeed,
    );
    final dtoItems = rawPage.items
        .map(postBaseDtoFromMap)
        .toList(growable: false);
    return DiscoveryFeedPage(
      items: dtoItems,
      nextCursor: rawPage.nextCursor,
      feedRequestId: obj['feedRequestId']?.toString(),
      rankingVersion: obj['rankingVersion']?.toString(),
      reasonVersion: obj['reasonVersion']?.toString(),
    );
  }

  @override
  Future<List<PostBaseDto>> listDiscoveryFeed({
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
  Future<ContentPostDetailPayload> getPost({required String postId}) async {
    throw UnsupportedError(
      'GetPost must use ContentPostDetailReader / GeneratedCloudOperationClient',
    );
  }

  @override
  Future<CursorPage<PostBaseDto>> listUserPosts({
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
  Future<void> deletePost({required String postId}) async {
    final uri = _uri(ContentApiMetadata.deletePostPath(postId: postId));
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.deletePost),
    );
  }

  @override
  Future<PostBaseDto> updatePostSettings({
    required String postId,
    required UpdatePostSettingsRequestWire body,
  }) async {
    final uri = _uri(ContentApiMetadata.updatePostSettingsPath(postId: postId));
    final decoded = await _httpClient.patchJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.updatePostSettings,
      ),
      body: body.toWire(),
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.updatePostSettings,
    );
    return _postBaseDtoFromContentWire(obj);
  }

  @override
  Future<PostBaseDto> promotePostToWork({
    required String postId,
    required PromotePostToWorkRequestWire body,
  }) async {
    final uri = _uri(ContentApiMetadata.promotePostToWorkPath(postId: postId));
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.promotePostToWork,
      ),
      body: body.toWire(),
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.promotePostToWork,
    );
    return _postBaseDtoFromContentWire(obj);
  }

  String? _mapCategoryToFeedType(String category) {
    return GeneratedPostRuntimeMetadata.feedCategoryToRequestType[category];
  }

  String? _mapCategoryToIdentity(String category) {
    switch (category.trim()) {
      case 'moment':
      case 'recommended':
      case 'following':
        return 'moment';
      case 'work':
      case 'works':
      case 'photo':
      case 'images':
      case 'video':
      case 'article':
        return 'work';
      default:
        return null;
    }
  }

  String? _normalizeFeedType(String? type) {
    final normalized = (type ?? '').trim().toLowerCase();
    switch (normalized) {
      case '':
        return null;
      case 'photo':
        return 'image';
      case 'note':
        return 'article';
      default:
        return normalized;
    }
  }

  @override
  bool get requiresResolvedPersonaForMutations => true;

  @override
  bool get usesEmbeddedContentCatalog => false;

  @override
  bool get usesCloudAssistantEdgeSync => true;

  @override
  DiscoveryPresentationWire? discoveryPresentationWireForPost(String postId) =>
      null;

  @override
  List<PostBaseDto> embeddedDiscoveryArticlePostsForFollowingMix() =>
      const <PostBaseDto>[];
}
