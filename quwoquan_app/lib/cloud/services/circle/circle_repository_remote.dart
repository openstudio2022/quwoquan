part of 'circle_repository.dart';

class RemoteCircleRepository implements CircleRepository {
  RemoteCircleRepository({CloudHttpClient? httpClient, String? baseUrl})
    : _httpClient = httpClient ?? CloudHttpClient(),
      _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: queryParameters);
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
      CloudRequestHeaders.forPage(CircleRequestPageIds.listCircles),
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
      CloudRequestHeaders.forPage(CircleRequestPageIds.searchCircles),
    );
    return CircleSearchResultView.fromMap(obj);
  }

  @override
  Future<CircleDetailPayload> getCircle(String circleId) async {
    final obj = await _getObject(
      _uri(CircleApiMetadata.getCirclePath(circleId: circleId)),
      CloudRequestHeaders.forPage(CircleRequestPageIds.getCircle),
    );
    return CircleDetailPayload.fromWire(obj);
  }

  @override
  Future<CircleDto> createCircle(CircleCreateWireDto data) async {
    final obj = await _postObject(
      _uri(CircleApiMetadata.createCirclePath),
      CloudRequestHeaders.forPage(CircleRequestPageIds.createCircle),
      data.toRequestMap(),
    );
    return CircleDto.fromMap(obj);
  }

  @override
  Future<CircleDto> updateCircle(
    String circleId,
    CircleUpdateWireDto data,
  ) async {
    final obj = await _patchObject(
      _uri(CircleApiMetadata.updateCirclePath(circleId: circleId)),
      CloudRequestHeaders.forPage(CircleRequestPageIds.updateCircle),
      data.toMap(),
    );
    return CircleDto.fromMap(obj);
  }

  @override
  Future<void> archiveCircle(String circleId) async {
    await _deleteVoid(
      _uri(CircleApiMetadata.archiveCirclePath(circleId: circleId)),
      CloudRequestHeaders.forPage(CircleRequestPageIds.archiveCircle),
    );
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
      CloudRequestHeaders.forPage(CircleRequestPageIds.getCircleFeed),
    );
    return _decodeCircleFeedMaps(list);
  }

  // -- Stats -----------------------------------------------------------------

  @override
  Future<CircleStatsWireDto> getCircleStats(String circleId) async {
    final obj = await _getObject(
      _uri(CircleApiMetadata.getCircleStatsPath(circleId: circleId)),
      CloudRequestHeaders.forPage(CircleRequestPageIds.getCircleStats),
    );
    return CircleStatsWireDto.fromMap(obj);
  }

  @override
  Future<CircleImpactSummary> getCircleImpact(String circleId) async {
    final obj = await _getObject(
      _uri(CircleApiMetadata.getCircleImpactPath(circleId: circleId)),
      CloudRequestHeaders.forPage(CircleRequestPageIds.getCircleImpact),
    );
    return CircleImpactSummary.fromMap(obj);
  }

  // -- Sections --------------------------------------------------------------

  @override
  Future<void> updateSections(
    String circleId,
    List<CircleSectionConfigDto> sections,
  ) async {
    final payload = sections.map((s) => s.toMap()).toList(growable: false);
    await _patchVoid(
      _uri(CircleApiMetadata.updateCircleSectionsPath(circleId: circleId)),
      CloudRequestHeaders.forPage(CircleRequestPageIds.updateCircleSections),
      <String, dynamic>{'sections': payload},
    );
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

  @override
  List<CircleDto> publishFlowRecommendedCircles() => const [];

  @override
  Future<Map<String, CircleCategoryTabConfigDto>>
  getCircleCategoryConfig() async {
    return Map<String, CircleCategoryTabConfigDto>.from(
      CircleCategoryTabDefaults.remoteStyleFallback,
    );
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

  Future<Map<String, dynamic>> _postObject(
    Uri uri,
    Map<String, String> headers, [
    Map<String, dynamic> body = const <String, dynamic>{},
  ]) async {
    final decoded = await _httpClient.postJson(
      uri,
      headers: headers,
      body: body,
    );
    return _unwrapObject(decoded, uri.path);
  }

  Future<Map<String, dynamic>> _patchObject(
    Uri uri,
    Map<String, String> headers,
    Map<String, dynamic> body,
  ) async {
    final decoded = await _httpClient.patchJson(
      uri,
      headers: headers,
      body: body,
    );
    return _unwrapObject(decoded, uri.path);
  }

  Future<void> _patchVoid(
    Uri uri,
    Map<String, String> headers,
    Map<String, dynamic> body,
  ) async {
    await _httpClient.patchJson(uri, headers: headers, body: body);
  }

  Future<void> _deleteVoid(Uri uri, Map<String, String> headers) async {
    await _httpClient.deleteJson(uri, headers: headers);
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
    final raw = obj['data'] ?? obj['items'];
    if (raw is List) {
      return raw
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: false);
    }
    return const <Map<String, dynamic>>[];
  }
}
