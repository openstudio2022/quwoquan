part of 'circle_repository.dart';

/// Circle 聚合读投影的远端实现。
/// 写命令不在此仓库：生命周期/板块命令经 generated client 的
/// `RemoteCircleLifecycleFacet` 提交。
class RemoteCircleRepository implements CircleRepository {
  factory RemoteCircleRepository({
    required CloudHttpClient httpClient,
    String? baseUrl,
  }) {
    return RemoteCircleRepository._(
      httpClient,
      (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim(),
    );
  }

  RemoteCircleRepository._(this._httpClient, this._baseUrl);

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: queryParameters);
  }

  Map<String, String> _headers(
    AppUiSurface surface, {
    required String operationId,
    required String clientPageId,
  }) {
    return CloudRequestHeaders.forSurfaceOperation(
      surfaceId: surface.id,
      routeId: surface.routeId,
      operationId: operationId,
      clientPageId: clientPageId,
    );
  }

  // -- Circles ---------------------------------------------------------------

  @override
  Future<List<CircleDto>> listCircles({
    String? category,
    String? subCategory,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? sort,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (category != null) query['category'] = category;
    if (subCategory != null) query['subCategory'] = subCategory;
    if (domainId != null) query['domainId'] = domainId;
    if (recommendFor != null) query['recommendFor'] = recommendFor;
    if (cursor != null) query['cursor'] = cursor;
    if (sort != null) query['sort'] = sort;

    final list = await _getList(
      _uri(CircleApiMetadata.listCirclesPath, queryParameters: query),
      _headers(
        AppUiSurfaces.circlesList,
        operationId: CircleApiMetadata.listCirclesOperation,
        clientPageId: CircleRequestPageIds.listCircles,
      ),
    );
    return list.map(CircleDto.fromMap).toList(growable: false);
  }

  @override
  Future<CircleSearchResultView> searchCircles({
    required String query,
    String? categoryId,
    String? subCategory,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final obj = await _getObject(
      _uri(
        CircleApiMetadata.searchCirclesPath,
        queryParameters: <String, String>{
          'query': query,
          if (categoryId != null && categoryId.isNotEmpty)
            'categoryId': categoryId,
          if (subCategory != null && subCategory.isNotEmpty)
            'subCategory': subCategory,
          'limit': '$limit',
        },
      ),
      _headers(
        AppUiSurfaces.circlesList,
        operationId: CircleApiMetadata.searchCirclesOperation,
        clientPageId: CircleRequestPageIds.searchCircles,
      ),
    );
    return CircleSearchResultView.fromMap(obj);
  }

  @override
  Future<CircleDetailPayload> getCircle(String circleId) async {
    final obj = await _getObject(
      _uri(CircleApiMetadata.getCirclePath(circleId: circleId)),
      _headers(
        AppUiSurfaces.circleDetail,
        operationId: CircleApiMetadata.getCircleOperation,
        clientPageId: CircleRequestPageIds.getCircle,
      ),
    );
    return CircleDetailPayload.fromWire(obj);
  }

  // -- Feed ------------------------------------------------------------------

  @override
  Future<List<PostBaseDto>> getCircleFeed(
    String circleId, {
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String sort = 'latest',
  }) async {
    final query = <String, String>{'limit': '$limit', 'sort': sort};
    if (cursor != null) query['cursor'] = cursor;
    if (identity != null && identity.isNotEmpty) query['identity'] = identity;
    final normalizedType = _normalizeCircleFeedType(type);
    if (normalizedType != null && normalizedType.isNotEmpty) {
      query['type'] = normalizedType;
    }

    final list = await _getList(
      _uri(
        CircleApiMetadata.getCircleFeedPath(circleId: circleId),
        queryParameters: query,
      ),
      _headers(
        AppUiSurfaces.circleDetail,
        operationId: CircleApiMetadata.getCircleFeedOperation,
        clientPageId: CircleRequestPageIds.getCircleFeed,
      ),
    );
    return _decodeCircleFeedMaps(list);
  }

  // -- Stats -----------------------------------------------------------------

  @override
  Future<CircleStatsWireDto> getCircleStats(String circleId) async {
    final obj = await _getObject(
      _uri(CircleApiMetadata.getCircleStatsPath(circleId: circleId)),
      _headers(
        AppUiSurfaces.circleDetail,
        operationId: CircleApiMetadata.getCircleStatsOperation,
        clientPageId: CircleRequestPageIds.getCircleStats,
      ),
    );
    return CircleStatsWireDto.fromMap(obj);
  }

  @override
  Future<CircleImpactSummary> getCircleImpact(String circleId) async {
    final obj = await _getObject(
      _uri(CircleApiMetadata.getCircleImpactPath(circleId: circleId)),
      _headers(
        AppUiSurfaces.circleDetail,
        operationId: CircleApiMetadata.getCircleImpactOperation,
        clientPageId: CircleRequestPageIds.getCircleImpact,
      ),
    );
    return CircleImpactSummary.fromMap(obj);
  }

  @override
  Future<List<PostBaseDto>> listHomeCircleDiscoveryFeed({
    int limit = kHomeCircleDiscoveryFeedDefaultLimit,
  }) async {
    final circles = await listCircles(limit: limit);
    final out = <PostBaseDto>[];
    for (final circle in circles) {
      if (out.length >= limit) break;
      final remaining = limit - out.length;
      final feed = await getCircleFeed(circle.id, limit: remaining);
      out.addAll(feed);
    }
    return out.take(limit).toList(growable: false);
  }

  // -- HTTP pipeline (统一走 CloudHttpClient + CloudErrorMapper) ----------------
  //
  // 所有请求经 CloudHttpClient 的 *Json 方法：非 2xx 由 CloudErrorMapper.fromStatusCode
  // 抛出结构化 CloudException（携带 runtimeFailure/recovery），不再有裸 Exception 旁路。
  // 解码沿用 circle 既往 data/items 语义（cursor-page 列表落在 data 或 items），
  // 类型不符经 CloudResponseDecoder.asObject 统一抛 invalidResponse。

  Future<Map<String, dynamic>> _getObject(
    Uri uri,
    Map<String, String> headers,
  ) async {
    final decoded = await _httpClient.getJson(uri, headers: headers);
    return _unwrapObject(decoded, uri.path);
  }

  Future<List<Map<String, dynamic>>> _getList(
    Uri uri,
    Map<String, String> headers,
  ) async {
    final decoded = await _httpClient.getJson(uri, headers: headers);
    return _unwrapList(decoded, uri.path);
  }

  Map<String, dynamic> _unwrapObject(Object? decoded, String path) {
    final obj = CloudResponseDecoder.asObject(decoded, context: path);
    final data = obj['data'];
    if (data is Map) {
      return Map<String, dynamic>.from(data);
    }
    return obj;
  }

  List<Map<String, dynamic>> _unwrapList(Object? decoded, String path) {
    if (decoded is List) {
      return decoded
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: false);
    }
    final obj = CloudResponseDecoder.asObject(decoded, context: path);
    final raw = obj['items'];
    if (raw is List) {
      return raw
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: false);
    }
    return const <Map<String, dynamic>>[];
  }
}
