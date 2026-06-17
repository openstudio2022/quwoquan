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

  // -- Membership ------------------------------------------------------------

  @override
  Future<void> joinCircle(
    String circleId, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  }) async {
    await _postVoid(
      _uri(CircleApiMetadata.joinCirclePath(circleId: circleId)),
      CloudRequestHeaders.withOwnerSubAccountContext(
        CloudRequestHeaders.forPage(CircleRequestPageIds.joinCircle),
        ownerUserId: ownerUserId,
        subAccountId: subAccountId,
        subAccountContextVersion: subAccountContextVersion,
      ),
    );
  }

  @override
  Future<void> leaveCircle(
    String circleId, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  }) async {
    await _postVoid(
      _uri(CircleApiMetadata.leaveCirclePath(circleId: circleId)),
      CloudRequestHeaders.withOwnerSubAccountContext(
        CloudRequestHeaders.forPage(CircleRequestPageIds.leaveCircle),
        ownerUserId: ownerUserId,
        subAccountId: subAccountId,
        subAccountContextVersion: subAccountContextVersion,
      ),
    );
  }

  @override
  Future<List<CircleMemberRosterItemDto>> listMembers(
    String circleId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (cursor != null) query['cursor'] = cursor;

    final list = await _getList(
      _uri(
        CircleApiMetadata.listCircleMembersPath(circleId: circleId),
        queryParameters: query,
      ),
      CloudRequestHeaders.forPage(CircleRequestPageIds.listCircleMembers),
    );
    return list
        .map((m) => CircleMemberRosterItemDto.fromMap(m, circleId: circleId))
        .toList(growable: false);
  }

  @override
  Future<void> updateMemberRole(
    String circleId,
    String userId,
    String role,
  ) async {
    await _patchVoid(
      _uri(
        CircleApiMetadata.updateMemberRolePath(
          circleId: circleId,
          userId: userId,
        ),
      ),
      CloudRequestHeaders.forPage(CircleRequestPageIds.updateMemberRole),
      <String, dynamic>{'role': role},
    );
  }

  // -- Circle Groups ----------------------------------------------------------

  @override
  Future<List<CircleGroupDto>> listCircleGroups(
    String circleId, {
    String? groupType,
    String? visibility,
    String? parentGroupId,
    String? nodeType,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (groupType != null && groupType.isNotEmpty) {
      query['groupType'] = groupType;
    }
    if (visibility != null && visibility.isNotEmpty) {
      query['visibility'] = visibility;
    }
    if (parentGroupId != null && parentGroupId.isNotEmpty) {
      query['parentGroupId'] = parentGroupId;
    }
    if (nodeType != null && nodeType.isNotEmpty) query['nodeType'] = nodeType;
    if (cursor != null && cursor.isNotEmpty) query['cursor'] = cursor;
    final list = await _getList(
      _uri(
        CircleApiMetadata.listCircleGroupsPath(circleId: circleId),
        queryParameters: query,
      ),
      CloudRequestHeaders.forPage(CircleRequestPageIds.listCircleGroups),
    );
    return list.map(CircleGroupDto.fromMap).toList(growable: false);
  }

  @override
  Future<List<CircleGroupDto>> searchCircleGroups(
    String circleId, {
    required String query,
    String? visibility,
    String? groupType,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final list = await _getList(
      _uri(
        CircleApiMetadata.searchCircleGroupsPath(circleId: circleId),
        queryParameters: <String, String>{
          'query': query,
          if (visibility != null && visibility.isNotEmpty)
            'visibility': visibility,
          if (groupType != null && groupType.isNotEmpty) 'groupType': groupType,
          'limit': '$limit',
        },
      ),
      CloudRequestHeaders.forPage(CircleRequestPageIds.searchCircleGroups),
    );
    return list.map(CircleGroupDto.fromMap).toList(growable: false);
  }

  @override
  Future<CircleGroupDto> getCircleGroup(String circleId, String groupId) async {
    final obj = await _getObject(
      _uri(
        CircleApiMetadata.getCircleGroupPath(
          circleId: circleId,
          groupId: groupId,
        ),
      ),
      CloudRequestHeaders.forPage(CircleRequestPageIds.getCircleGroup),
    );
    return CircleGroupDto.fromMap(obj);
  }

  @override
  Future<CircleGroupDto> createCircleGroup(
    String circleId,
    CircleGroupCreateWireDto data,
  ) async {
    final obj = await _postObject(
      _uri(CircleApiMetadata.createCircleGroupPath(circleId: circleId)),
      CloudRequestHeaders.forPage(CircleRequestPageIds.createCircleGroup),
      data.toMap(),
    );
    return CircleGroupDto.fromMap(obj);
  }

  @override
  Future<CircleGroupDto> updateCircleGroup(
    String circleId,
    String groupId,
    CircleGroupUpdateWireDto data,
  ) async {
    final obj = await _patchObject(
      _uri(
        CircleApiMetadata.updateCircleGroupPath(
          circleId: circleId,
          groupId: groupId,
        ),
      ),
      CloudRequestHeaders.forPage(CircleRequestPageIds.updateCircleGroup),
      data.toMap(),
    );
    return CircleGroupDto.fromMap(obj);
  }

  @override
  Future<void> applyJoinCircleGroup(String circleId, String groupId) async {
    await _postVoid(
      _uri(
        CircleApiMetadata.applyJoinCircleGroupPath(
          circleId: circleId,
          groupId: groupId,
        ),
      ),
      CloudRequestHeaders.forPage(CircleRequestPageIds.applyJoinCircleGroup),
    );
  }

  @override
  Future<List<CircleGroupMemberDto>> listCircleGroupMembers(
    String circleId,
    String groupId, {
    String? status,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (status != null && status.isNotEmpty) query['status'] = status;
    if (cursor != null && cursor.isNotEmpty) query['cursor'] = cursor;
    final list = await _getList(
      _uri(
        CircleApiMetadata.listCircleGroupMembersPath(
          circleId: circleId,
          groupId: groupId,
        ),
        queryParameters: query,
      ),
      CloudRequestHeaders.forPage(CircleRequestPageIds.listCircleGroupMembers),
    );
    return list.map(CircleGroupMemberDto.fromMap).toList(growable: false);
  }

  @override
  Future<void> approveCircleGroupMember(
    String circleId,
    String groupId,
    String userId,
  ) async {
    await _postVoid(
      _uri(
        CircleApiMetadata.approveCircleGroupMemberPath(
          circleId: circleId,
          groupId: groupId,
          userId: userId,
        ),
      ),
      CloudRequestHeaders.forPage(CircleRequestPageIds.approveCircleGroupMember),
    );
  }

  @override
  Future<void> rejectCircleGroupMember(
    String circleId,
    String groupId,
    String userId,
  ) async {
    await _postVoid(
      _uri(
        CircleApiMetadata.rejectCircleGroupMemberPath(
          circleId: circleId,
          groupId: groupId,
          userId: userId,
        ),
      ),
      CloudRequestHeaders.forPage(CircleRequestPageIds.rejectCircleGroupMember),
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

  @override
  Future<void> pinPost(
    String circleId,
    String postId, {
    required bool pinned,
  }) async {
    await _patchVoid(
      _uri(
        CircleApiMetadata.pinCirclePostPath(circleId: circleId, postId: postId),
      ),
      CloudRequestHeaders.forPage(CircleRequestPageIds.pinCirclePost),
      <String, dynamic>{'pinned': pinned},
    );
  }

  @override
  Future<void> featurePost(
    String circleId,
    String postId, {
    required bool featured,
  }) async {
    await _patchVoid(
      _uri(
        CircleApiMetadata.featureCirclePostPath(
          circleId: circleId,
          postId: postId,
        ),
      ),
      CloudRequestHeaders.forPage(CircleRequestPageIds.featureCirclePost),
      <String, dynamic>{'featured': featured},
    );
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

  // -- Files -----------------------------------------------------------------

  @override
  Future<List<CircleFileDto>> listFiles(
    String circleId, {
    String? parentId,
    String? sort,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (parentId != null) query['parentId'] = parentId;
    if (sort != null) query['sort'] = sort;
    if (cursor != null) query['cursor'] = cursor;

    final list = await _getList(
      _uri(
        CircleApiMetadata.listCircleFilesPath(circleId: circleId),
        queryParameters: query,
      ),
      CloudRequestHeaders.forPage(CircleRequestPageIds.listCircleFiles),
    );
    return list
        .map((m) => CircleFileDto.fromMap({...m, 'circleId': circleId}))
        .toList(growable: false);
  }

  @override
  Future<CircleFileDto> createFile(
    String circleId,
    CircleFileCreateWireDto data,
  ) async {
    final obj = await _postObject(
      _uri(CircleApiMetadata.createCircleFilePath(circleId: circleId)),
      CloudRequestHeaders.forPage(CircleRequestPageIds.createCircleFile),
      data.toMap(),
    );
    return CircleFileDto.fromMap({...obj, 'circleId': circleId});
  }

  @override
  Future<CircleFileDto> getFile(String circleId, String fileId) async {
    final obj = await _getObject(
      _uri(
        CircleApiMetadata.getCircleFilePath(circleId: circleId, fileId: fileId),
      ),
      CloudRequestHeaders.forPage(CircleRequestPageIds.getCircleFile),
    );
    return CircleFileDto.fromMap({...obj, 'circleId': circleId});
  }

  @override
  Future<CircleFileDto> updateFile(
    String circleId,
    String fileId,
    CircleFileUpdateWireDto data,
  ) async {
    final obj = await _patchObject(
      _uri(
        CircleApiMetadata.updateCircleFilePath(
          circleId: circleId,
          fileId: fileId,
        ),
      ),
      CloudRequestHeaders.forPage(CircleRequestPageIds.updateCircleFile),
      data.toMap(),
    );
    return CircleFileDto.fromMap({...obj, 'circleId': circleId});
  }

  @override
  Future<void> deleteFile(String circleId, String fileId) async {
    await _deleteVoid(
      _uri(
        CircleApiMetadata.deleteCircleFilePath(
          circleId: circleId,
          fileId: fileId,
        ),
      ),
      CloudRequestHeaders.forPage(CircleRequestPageIds.deleteCircleFile),
    );
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

  // -- Behavior --------------------------------------------------------------

  @override
  Future<void> reportBehavior(CircleBehaviorReportWireDto report) async {
    await _postVoid(
      _uri(CircleApiMetadata.reportCircleBehaviorPath),
      CloudRequestHeaders.forPage(CircleRequestPageIds.reportCircleBehavior),
      report.toMap(),
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
    return CircleCategoryTabsLoader.loadFromAsset();
  }

  // -- User Circles ----------------------------------------------------------

  @override
  Future<List<CircleDto>> listUserCircles(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (cursor != null) query['cursor'] = cursor;

    final list = await _getList(
      _uri(
        CircleApiMetadata.listUserCirclesPath(userId: userId),
        queryParameters: query,
      ),
      CloudRequestHeaders.forPage(CircleRequestPageIds.listUserCircles),
    );
    return list.map(CircleDto.fromMap).toList(growable: false);
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
    final decoded = await _httpClient.postJson(uri, headers: headers, body: body);
    return _unwrapObject(decoded, uri.path);
  }

  Future<void> _postVoid(
    Uri uri,
    Map<String, String> headers, [
    Map<String, dynamic> body = const <String, dynamic>{},
  ]) async {
    await _httpClient.postJson(uri, headers: headers, body: body);
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
