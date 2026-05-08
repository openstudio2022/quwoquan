part of 'circle_repository.dart';

class RemoteCircleRepository implements CircleRepository {
  RemoteCircleRepository({http.Client? client, String? baseUrl})
    : _client = client ?? http.Client(),
      _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final http.Client _client;
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

    final uri = _uri(CircleApiMetadata.listCirclesPath, queryParameters: query);
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.listCircles),
    );
    return _decodeList(resp).map(CircleDto.fromMap).toList(growable: false);
  }

  @override
  Future<CircleSearchResultView> searchCircles({
    required String query,
    String? categoryId,
    String? subCategory,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final resp = await _client.get(
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
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.searchCircles),
    );
    return CircleSearchResultView.fromMap(_decodeObject(resp));
  }

  @override
  Future<CircleDetailPayload> getCircle(String circleId) async {
    final uri = _uri(CircleApiMetadata.getCirclePath(circleId: circleId));
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.getCircle),
    );
    return CircleDetailPayload.fromWire(_decodeObject(resp));
  }

  @override
  Future<CircleDto> createCircle(CircleCreateWireDto data) async {
    final uri = _uri(CircleApiMetadata.createCirclePath);
    final resp = await _client.post(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.createCircle),
        'Content-Type': 'application/json',
      },
      body: json.encode(data.toRequestMap()),
    );
    return CircleDto.fromMap(_decodeObject(resp));
  }

  @override
  Future<CircleDto> updateCircle(
    String circleId,
    CircleUpdateWireDto data,
  ) async {
    final uri = _uri(CircleApiMetadata.updateCirclePath(circleId: circleId));
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.updateCircle),
        'Content-Type': 'application/json',
      },
      body: json.encode(data.toMap()),
    );
    return CircleDto.fromMap(_decodeObject(resp));
  }

  @override
  Future<void> archiveCircle(String circleId) async {
    final uri = _uri(CircleApiMetadata.archiveCirclePath(circleId: circleId));
    final resp = await _client.delete(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.archiveCircle),
    );
    _ensureSuccess(resp);
  }

  // -- Membership ------------------------------------------------------------

  @override
  Future<void> joinCircle(
    String circleId, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  }) async {
    final uri = _uri(CircleApiMetadata.joinCirclePath(circleId: circleId));
    final resp = await _client.post(
      uri,
      headers: CloudRequestHeaders.withOwnerSubAccountContext(
        CloudRequestHeaders.forPage(CircleRequestPageIds.joinCircle),
        ownerUserId: ownerUserId,
        subAccountId: subAccountId,
        subAccountContextVersion: subAccountContextVersion,
      ),
    );
    _ensureSuccess(resp);
  }

  @override
  Future<void> leaveCircle(
    String circleId, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  }) async {
    final uri = _uri(CircleApiMetadata.leaveCirclePath(circleId: circleId));
    final resp = await _client.post(
      uri,
      headers: CloudRequestHeaders.withOwnerSubAccountContext(
        CloudRequestHeaders.forPage(CircleRequestPageIds.leaveCircle),
        ownerUserId: ownerUserId,
        subAccountId: subAccountId,
        subAccountContextVersion: subAccountContextVersion,
      ),
    );
    _ensureSuccess(resp);
  }

  @override
  Future<List<CircleMemberRosterItemDto>> listMembers(
    String circleId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (cursor != null) query['cursor'] = cursor;

    final uri = _uri(
      CircleApiMetadata.listCircleMembersPath(circleId: circleId),
      queryParameters: query,
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.listCircleMembers,
      ),
    );
    return _decodeList(resp)
        .map((m) => CircleMemberRosterItemDto.fromMap(m, circleId: circleId))
        .toList(growable: false);
  }

  @override
  Future<void> updateMemberRole(
    String circleId,
    String userId,
    String role,
  ) async {
    final uri = _uri(
      CircleApiMetadata.updateMemberRolePath(
        circleId: circleId,
        userId: userId,
      ),
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.updateMemberRole),
        'Content-Type': 'application/json',
      },
      body: json.encode({'role': role}),
    );
    _ensureSuccess(resp);
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
    final uri = _uri(
      CircleApiMetadata.listCircleGroupsPath(circleId: circleId),
      queryParameters: query,
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.listCircleGroups,
      ),
    );
    return _decodeList(
      resp,
    ).map(CircleGroupDto.fromMap).toList(growable: false);
  }

  @override
  Future<List<CircleGroupDto>> searchCircleGroups(
    String circleId, {
    required String query,
    String? visibility,
    String? groupType,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final uri = _uri(
      CircleApiMetadata.searchCircleGroupsPath(circleId: circleId),
      queryParameters: <String, String>{
        'query': query,
        if (visibility != null && visibility.isNotEmpty)
          'visibility': visibility,
        if (groupType != null && groupType.isNotEmpty) 'groupType': groupType,
        'limit': '$limit',
      },
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.searchCircleGroups,
      ),
    );
    return _decodeList(
      resp,
    ).map(CircleGroupDto.fromMap).toList(growable: false);
  }

  @override
  Future<CircleGroupDto> getCircleGroup(String circleId, String groupId) async {
    final uri = _uri(
      CircleApiMetadata.getCircleGroupPath(
        circleId: circleId,
        groupId: groupId,
      ),
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.getCircleGroup),
    );
    return CircleGroupDto.fromMap(_decodeObject(resp));
  }

  @override
  Future<CircleGroupDto> createCircleGroup(
    String circleId,
    CircleGroupCreateWireDto data,
  ) async {
    final uri = _uri(
      CircleApiMetadata.createCircleGroupPath(circleId: circleId),
    );
    final resp = await _client.post(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.createCircleGroup),
        'Content-Type': 'application/json',
      },
      body: json.encode(data.toMap()),
    );
    return CircleGroupDto.fromMap(_decodeObject(resp));
  }

  @override
  Future<CircleGroupDto> updateCircleGroup(
    String circleId,
    String groupId,
    CircleGroupUpdateWireDto data,
  ) async {
    final uri = _uri(
      CircleApiMetadata.updateCircleGroupPath(
        circleId: circleId,
        groupId: groupId,
      ),
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.updateCircleGroup),
        'Content-Type': 'application/json',
      },
      body: json.encode(data.toMap()),
    );
    return CircleGroupDto.fromMap(_decodeObject(resp));
  }

  @override
  Future<void> applyJoinCircleGroup(String circleId, String groupId) async {
    final uri = _uri(
      CircleApiMetadata.applyJoinCircleGroupPath(
        circleId: circleId,
        groupId: groupId,
      ),
    );
    final resp = await _client.post(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.applyJoinCircleGroup,
      ),
    );
    _ensureSuccess(resp);
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
    final uri = _uri(
      CircleApiMetadata.listCircleGroupMembersPath(
        circleId: circleId,
        groupId: groupId,
      ),
      queryParameters: query,
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.listCircleGroupMembers,
      ),
    );
    return _decodeList(
      resp,
    ).map(CircleGroupMemberDto.fromMap).toList(growable: false);
  }

  @override
  Future<void> approveCircleGroupMember(
    String circleId,
    String groupId,
    String userId,
  ) async {
    final uri = _uri(
      CircleApiMetadata.approveCircleGroupMemberPath(
        circleId: circleId,
        groupId: groupId,
        userId: userId,
      ),
    );
    final resp = await _client.post(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.approveCircleGroupMember,
      ),
    );
    _ensureSuccess(resp);
  }

  @override
  Future<void> rejectCircleGroupMember(
    String circleId,
    String groupId,
    String userId,
  ) async {
    final uri = _uri(
      CircleApiMetadata.rejectCircleGroupMemberPath(
        circleId: circleId,
        groupId: groupId,
        userId: userId,
      ),
    );
    final resp = await _client.post(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.rejectCircleGroupMember,
      ),
    );
    _ensureSuccess(resp);
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

    final uri = _uri(
      CircleApiMetadata.getCircleFeedPath(circleId: circleId),
      queryParameters: query,
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.getCircleFeed),
    );
    return _decodeCircleFeedMaps(_decodeList(resp));
  }

  @override
  Future<void> pinPost(
    String circleId,
    String postId, {
    required bool pinned,
  }) async {
    final uri = _uri(
      CircleApiMetadata.pinCirclePostPath(circleId: circleId, postId: postId),
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.pinCirclePost),
        'Content-Type': 'application/json',
      },
      body: json.encode({'pinned': pinned}),
    );
    _ensureSuccess(resp);
  }

  @override
  Future<void> featurePost(
    String circleId,
    String postId, {
    required bool featured,
  }) async {
    final uri = _uri(
      CircleApiMetadata.featureCirclePostPath(
        circleId: circleId,
        postId: postId,
      ),
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.featureCirclePost),
        'Content-Type': 'application/json',
      },
      body: json.encode({'featured': featured}),
    );
    _ensureSuccess(resp);
  }

  // -- Stats -----------------------------------------------------------------

  @override
  Future<CircleStatsWireDto> getCircleStats(String circleId) async {
    final uri = _uri(CircleApiMetadata.getCircleStatsPath(circleId: circleId));
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.getCircleStats),
    );
    return CircleStatsWireDto.fromMap(_decodeObject(resp));
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

    final uri = _uri(
      CircleApiMetadata.listCircleFilesPath(circleId: circleId),
      queryParameters: query,
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.listCircleFiles,
      ),
    );
    return _decodeList(resp)
        .map((m) => CircleFileDto.fromMap({...m, 'circleId': circleId}))
        .toList(growable: false);
  }

  @override
  Future<CircleFileDto> createFile(
    String circleId,
    CircleFileCreateWireDto data,
  ) async {
    final uri = _uri(
      CircleApiMetadata.createCircleFilePath(circleId: circleId),
    );
    final resp = await _client.post(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.createCircleFile),
        'Content-Type': 'application/json',
      },
      body: json.encode(data.toMap()),
    );
    return CircleFileDto.fromMap({
      ..._decodeObject(resp),
      'circleId': circleId,
    });
  }

  @override
  Future<CircleFileDto> getFile(String circleId, String fileId) async {
    final uri = _uri(
      CircleApiMetadata.getCircleFilePath(circleId: circleId, fileId: fileId),
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.getCircleFile),
    );
    return CircleFileDto.fromMap({
      ..._decodeObject(resp),
      'circleId': circleId,
    });
  }

  @override
  Future<CircleFileDto> updateFile(
    String circleId,
    String fileId,
    CircleFileUpdateWireDto data,
  ) async {
    final uri = _uri(
      CircleApiMetadata.updateCircleFilePath(
        circleId: circleId,
        fileId: fileId,
      ),
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.updateCircleFile),
        'Content-Type': 'application/json',
      },
      body: json.encode(data.toMap()),
    );
    return CircleFileDto.fromMap({
      ..._decodeObject(resp),
      'circleId': circleId,
    });
  }

  @override
  Future<void> deleteFile(String circleId, String fileId) async {
    final uri = _uri(
      CircleApiMetadata.deleteCircleFilePath(
        circleId: circleId,
        fileId: fileId,
      ),
    );
    final resp = await _client.delete(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.deleteCircleFile,
      ),
    );
    _ensureSuccess(resp);
  }

  // -- Sections --------------------------------------------------------------

  @override
  Future<void> updateSections(
    String circleId,
    List<CircleSectionConfigDto> sections,
  ) async {
    final uri = _uri(
      CircleApiMetadata.updateCircleSectionsPath(circleId: circleId),
    );
    final payload = sections.map((s) => s.toMap()).toList(growable: false);
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(
          CircleRequestPageIds.updateCircleSections,
        ),
        'Content-Type': 'application/json',
      },
      body: json.encode({'sections': payload}),
    );
    _ensureSuccess(resp);
  }

  // -- Behavior --------------------------------------------------------------

  @override
  Future<void> reportBehavior(CircleBehaviorReportWireDto report) async {
    final uri = _uri(CircleApiMetadata.reportCircleBehaviorPath);
    final resp = await _client.post(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(
          CircleRequestPageIds.reportCircleBehavior,
        ),
        'Content-Type': 'application/json',
      },
      body: json.encode(report.toMap()),
    );
    _ensureSuccess(resp);
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

    final uri = _uri(
      CircleApiMetadata.listUserCirclesPath(userId: userId),
      queryParameters: query,
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.listUserCircles,
      ),
    );
    return _decodeList(resp).map(CircleDto.fromMap).toList(growable: false);
  }

  // -- Helpers ---------------------------------------------------------------

  void _ensureSuccess(http.Response resp) {
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw Exception('Circle API error ${resp.statusCode}: ${resp.body}');
    }
  }

  Map<String, dynamic> _decodeObject(http.Response resp) {
    _ensureSuccess(resp);
    final decoded = json.decode(resp.body);
    if (decoded is Map<String, dynamic>) {
      return (decoded['data'] as Map<String, dynamic>?) ?? decoded;
    }
    throw FormatException('Expected JSON object, got ${decoded.runtimeType}');
  }

  List<Map<String, dynamic>> _decodeList(http.Response resp) {
    _ensureSuccess(resp);
    final decoded = json.decode(resp.body);
    if (decoded is Map<String, dynamic>) {
      final items = decoded['data'] ?? decoded['items'] ?? [];
      return (items as List).cast<Map<String, dynamic>>();
    }
    if (decoded is List) {
      return decoded.cast<Map<String, dynamic>>();
    }
    throw FormatException('Expected JSON list, got ${decoded.runtimeType}');
  }
}
