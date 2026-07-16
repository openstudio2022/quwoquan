part of 'user_profile_repository.dart';

class RemoteUserProfileRepository extends UserProfileRepository {
  RemoteUserProfileRepository({CloudHttpClient? httpClient, String? baseUrl})
    : _httpClient = httpClient ?? CloudHttpClient(),
      _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();
  final CloudHttpClient _httpClient;
  final String _baseUrl;
  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: queryParameters);
  }

  List<Map<String, dynamic>> _decodeItems(http.Response resp, String context) {
    final decoded = json.decode(resp.body);
    final obj = CloudResponseDecoder.asObject(decoded, context: context);
    return CloudResponseDecoder.mapList(obj, 'items');
  }

  List<T> _decodeItemsAs<T>(
    http.Response resp,
    String context,
    T Function(Map<String, dynamic> m) map,
  ) {
    return _decodeItems(resp, context).map(map).toList(growable: false);
  }

  Map<String, dynamic> _decodeObject(http.Response resp, String context) {
    final data = CloudResponseDecoder.asObject(
      json.decode(resp.body),
      context: context,
    );
    final payload = data['data'];
    if (payload is Map<String, dynamic>) {
      return payload;
    }
    if (payload is Map) {
      return Map<String, dynamic>.from(payload);
    }
    return data;
  }

  Never _throwStatus(http.Response resp, String path) {
    throw CloudErrorMapper.fromStatusCode(
      resp.statusCode,
      body: resp.body,
      requestPath: path,
    );
  }

  // ── 档案 ──────────────────────────────────────────────────────────────────
  @override
  Future<SubAccountProfileViewData> getUserProfile(String userId) async {
    if (userId == 'me') {
      final meUrl = _uri(UserApiMetadata.getMeProfilePath);
      final meResp = await _httpClient.get(
        meUrl,
        headers: CloudRequestHeaders.forPage(UserRequestPageIds.getMeProfile),
      );
      if (meResp.statusCode == 200) {
        final map = CloudResponseDecoder.asObject(
          json.decode(meResp.body),
          context: UserRequestPageIds.getMeProfile,
        );
        return SubAccountProfileViewData.fromSubAccountProfileWire(
          SubAccountProfileWireDto.fromMap(map),
        );
      }
    }
    final subjectUrl = _uri(
      UserApiMetadata.getSubAccountProfilePath(subAccountId: userId),
    );
    final subjectResp = await _httpClient.get(
      subjectUrl,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.getSubAccountProfile,
      ),
    );
    if (subjectResp.statusCode == 200) {
      final map = CloudResponseDecoder.asObject(
        json.decode(subjectResp.body),
        context: UserRequestPageIds.getSubAccountProfile,
      );
      return SubAccountProfileViewData.fromSubAccountProfileWire(
        SubAccountProfileWireDto.fromMap(map),
      );
    }
    throw Exception('getUserProfile failed: subject=${subjectResp.statusCode}');
  }

  @override
  Future<UserHomepageBundleViewData> getUserHomepageBundle(
    String subAccountId,
  ) async {
    final url = _uri(
      UserApiMetadata.getUserHomepageBundlePath(subAccountId: subAccountId),
    );
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.getUserHomepageBundle,
      ),
    );
    if (resp.statusCode != 200) {
      throw Exception('getUserHomepageBundle failed: ${resp.statusCode}');
    }
    final data = CloudResponseDecoder.asObject(
      json.decode(resp.body),
      context: UserRequestPageIds.getUserHomepageBundle,
    );
    return UserHomepageBundleViewData.fromUserHomepageBundleWire(
      UserHomepageBundleWireDto.fromMap(data),
    );
  }

  @override
  Future<ProfileEditSnapshotData> getProfileEditSnapshot() async {
    final url = _uri(UserApiMetadata.getProfileEditSnapshotPath);
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.getProfileEditSnapshot,
      ),
    );
    if (resp.statusCode != 200) {
      _throwStatus(resp, UserApiMetadata.getProfileEditSnapshotPath);
    }
    return ProfileEditSnapshotData.fromWire(
      ProfileEditSnapshotWireDto.fromMap(
        _decodeObject(resp, UserRequestPageIds.getProfileEditSnapshot),
      ),
    );
  }

  @override
  Future<ProfileQrCardData> getProfileQrCard() async {
    final url = _uri(UserApiMetadata.getProfileQrCardPath);
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.getProfileQrCard),
    );
    if (resp.statusCode != 200) {
      _throwStatus(resp, UserApiMetadata.getProfileQrCardPath);
    }
    return ProfileQrCardData.fromWire(
      ProfileQrCardWireDto.fromMap(
        _decodeObject(resp, UserRequestPageIds.getProfileQrCard),
      ),
    );
  }

  @override
  Future<ProfileQrResolveWireDto> resolveProfileQrToken({
    required String token,
    String handle = '',
  }) async {
    final normalizedToken = token.trim();
    if (normalizedToken.isEmpty) {
      throw ArgumentError.value(token, 'token', 'qr token required');
    }
    final query = <String, String>{'qr': normalizedToken};
    final normalizedHandle = handle.trim();
    if (normalizedHandle.isNotEmpty) {
      query['handle'] = normalizedHandle;
    }
    final url = _uri(
      UserApiMetadata.resolveProfileQrTokenPath,
      queryParameters: query,
    );
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.resolveProfileQrToken,
      ),
    );
    if (resp.statusCode != 200) {
      _throwStatus(resp, UserApiMetadata.resolveProfileQrTokenPath);
    }
    return ProfileQrResolveWireDto.fromMap(
      _decodeObject(resp, UserRequestPageIds.resolveProfileQrToken),
    );
  }

  @override
  Future<void> updateProfile(ProfileEditUpdatePayload data) async {
    final url = _uri(UserApiMetadata.updateUserProfilePath);
    final resp = await _httpClient.patch(
      url,
      headers: {
        ...CloudRequestHeaders.forPage(UserRequestPageIds.updateUserProfile),
        'Content-Type': 'application/json',
      },
      body: json.encode(data.toRepositoryMap()),
    );
    if (resp.statusCode != 200) {
      _throwStatus(resp, UserApiMetadata.updateUserProfilePath);
    }
  }

  // ── 主页 Tab 数据 ─────────────────────────────────────────────────────────

  @override
  Future<List<PostBaseDto>> listUserPosts(
    String userId, {
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final url = _uri(
      ContentApiMetadata.listUserPostsPath(subAccountId: userId),
      queryParameters: <String, String>{'limit': '$limit'},
    );
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.listUserPosts),
    );
    if (resp.statusCode != 200) {
      throw Exception('listUserPosts failed: ${resp.statusCode}');
    }
    final data = CloudResponseDecoder.asObject(
      json.decode(resp.body),
      context: ContentRequestPageIds.listUserPosts,
    );
    final items = CloudResponseDecoder.mapList(data, 'items');
    return items.map(postBaseDtoFromMap).toList();
  }

  @override
  Future<List<UserWorkItem>> listUserWorks(String userId) async {
    final url = _uri(UserApiMetadata.listUserWorksPath(userId: userId));
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listUserWorks),
    );
    if (resp.statusCode != 200) {
      throw Exception('listUserWorks failed: ${resp.statusCode}');
    }
    final data = CloudResponseDecoder.asObject(
      json.decode(resp.body),
      context: UserRequestPageIds.listUserWorks,
    );
    final items = CloudResponseDecoder.mapList(data, 'items');
    return items.map(_workItemFromMap).toList();
  }

  @override
  Future<List<UserLifeItem>> listUserLifeItems(String userId) async {
    final url = _uri(UserApiMetadata.listUserLifeItemsPath(userId: userId));
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.listUserLifeItems,
      ),
    );
    if (resp.statusCode != 200) {
      throw Exception('listUserLifeItems failed: ${resp.statusCode}');
    }
    final data = CloudResponseDecoder.asObject(
      json.decode(resp.body),
      context: UserRequestPageIds.listUserLifeItems,
    );
    final items = CloudResponseDecoder.mapList(data, 'items');
    return items.map(_lifeItemFromMap).toList();
  }

  @override
  Future<UserProfileStatsViewData> getUserStats(String userId) async {
    final profile = await getUserProfile(userId);
    return UserProfileStatsViewData.fromProfile(profile);
  }

  @override
  Future<AuthorImpactSummary> getAuthorImpact(String userId) async {
    final url = _uri(
      ContentApiMetadata.getAuthorImpactPath(subAccountId: userId),
      queryParameters: const <String, String>{'limit': '12'},
    );
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.getAuthorImpact,
      ),
    );
    if (resp.statusCode != 200) {
      throw Exception('getAuthorImpact failed: ${resp.statusCode}');
    }
    return AuthorImpactSummary.fromMap(
      _decodeObject(resp, ContentRequestPageIds.getAuthorImpact),
    );
  }

  @override
  Future<AuthorImpactEvidencePage> listAuthorImpactEvidence({
    required String subAccountId,
    required String impactId,
    String evidenceSnapshotId = '',
    String cursor = '',
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'impactId': impactId, 'limit': '$limit'};
    if (evidenceSnapshotId.trim().isNotEmpty) {
      query['evidenceSnapshotId'] = evidenceSnapshotId.trim();
    }
    if (cursor.trim().isNotEmpty) {
      query['cursor'] = cursor.trim();
    }
    final url = _uri(
      ContentApiMetadata.listAuthorImpactEvidencePath(
        subAccountId: subAccountId,
      ),
      queryParameters: query,
    );
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.listAuthorImpactEvidence,
      ),
    );
    if (resp.statusCode != 200) {
      throw Exception('listAuthorImpactEvidence failed: ${resp.statusCode}');
    }
    return AuthorImpactEvidencePage.fromMap(
      _decodeObject(resp, ContentRequestPageIds.listAuthorImpactEvidence),
    );
  }

  @override
  Future<List<SocialRelationSearchItemView>> searchSocialRelations({
    required String query,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final url = _uri(
      UserApiMetadata.searchSocialRelationsPath,
      queryParameters: <String, String>{'query': query, 'limit': '$limit'},
    );
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.searchSocialRelations,
      ),
    );
    if (resp.statusCode != 200) {
      throw Exception('searchSocialRelations failed: ${resp.statusCode}');
    }
    return _decodeItemsAs(resp, UserRequestPageIds.searchSocialRelations, (m) {
      final w = SocialRelationSearchItemWireDto.fromMap(m);
      return SocialRelationSearchItemView.fromSocialRelationSearchItemWire(
        w,
        m,
      );
    });
  }

  @override
  Future<List<RecentSearchEntryView>> listRecentSearches() async {
    final url = _uri(SearchApiMetadata.listRecentSearchesPath);
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(
        SearchRequestPageIds.listRecentSearches,
      ),
    );
    if (resp.statusCode != 200) {
      throw Exception('listRecentSearches failed: ${resp.statusCode}');
    }
    return _decodeItemsAs(
      resp,
      SearchRequestPageIds.listRecentSearches,
      (m) => RecentSearchEntryView.fromRecentSearchEntryWire(
        RecentSearchEntryWireDto.fromMap(m),
      ),
    );
  }

  @override
  Future<RecentSearchEntryView> upsertRecentSearch({
    required String query,
    required SearchScope scope,
    String? facet,
  }) async {
    final scopeValue = scope.wireValue;
    final seed = '$scopeValue|${facet ?? ''}|${query.trim().toLowerCase()}';
    final entryId = 'recent_${seed.hashCode.abs().toRadixString(16)}';
    final url = _uri(
      SearchApiMetadata.upsertRecentSearchPath(entryId: entryId),
    );
    final resp = await _httpClient.put(
      url,
      headers: {
        ...CloudRequestHeaders.forPage(SearchRequestPageIds.upsertRecentSearch),
        'Content-Type': 'application/json',
      },
      body: json.encode(<String, dynamic>{
        'query': query,
        'scope': scopeValue,
        'facet': facet,
        'updatedAt': DateTime.now().toIso8601String(),
      }),
    );
    if (resp.statusCode != 200 && resp.statusCode != 201) {
      throw Exception('upsertRecentSearch failed: ${resp.statusCode}');
    }
    return RecentSearchEntryView.fromRecentSearchEntryWire(
      RecentSearchEntryWireDto.fromMap(
        _decodeObject(resp, SearchRequestPageIds.upsertRecentSearch),
      ),
    );
  }

  @override
  Future<void> deleteRecentSearch(String entryId) async {
    final url = _uri(
      SearchApiMetadata.deleteRecentSearchPath(entryId: entryId),
    );
    final resp = await _httpClient.delete(
      url,
      headers: CloudRequestHeaders.forPage(
        SearchRequestPageIds.deleteRecentSearch,
      ),
    );
    if (resp.statusCode != 200 && resp.statusCode != 204) {
      throw Exception('deleteRecentSearch failed: ${resp.statusCode}');
    }
  }

  @override
  Future<void> clearRecentSearches() async {
    final url = _uri(SearchApiMetadata.clearRecentSearchesPath);
    final resp = await _httpClient.delete(
      url,
      headers: CloudRequestHeaders.forPage(
        SearchRequestPageIds.clearRecentSearches,
      ),
    );
    if (resp.statusCode != 200 && resp.statusCode != 204) {
      throw Exception('clearRecentSearches failed: ${resp.statusCode}');
    }
  }

  // ── 关注 / 粉丝 ──────────────────────────────────────────────────────────

  @override
  Future<void> followUser(
    String targetUserId, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  }) async {
    final url = _uri(
      UserApiMetadata.followUserPath(targetSubAccountId: targetUserId),
    );
    final resp = await _httpClient.post(
      url,
      headers: CloudRequestHeaders.withOwnerSubAccountContext(
        CloudRequestHeaders.forPage(UserRequestPageIds.followUser),
        ownerUserId: ownerUserId,
        subAccountId: subAccountId,
        subAccountContextVersion: subAccountContextVersion,
      ),
    );
    if (resp.statusCode != 200 && resp.statusCode != 201) {
      throw Exception('followUser failed: ${resp.statusCode}');
    }
  }

  @override
  Future<void> unfollowUser(
    String targetUserId, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  }) async {
    final url = _uri(
      UserApiMetadata.unfollowUserPath(targetSubAccountId: targetUserId),
    );
    final resp = await _httpClient.delete(
      url,
      headers: CloudRequestHeaders.withOwnerSubAccountContext(
        CloudRequestHeaders.forPage(UserRequestPageIds.unfollowUser),
        ownerUserId: ownerUserId,
        subAccountId: subAccountId,
        subAccountContextVersion: subAccountContextVersion,
      ),
    );
    if (resp.statusCode != 200 && resp.statusCode != 204) {
      throw Exception('unfollowUser failed: ${resp.statusCode}');
    }
  }

  @override
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowingPage(
    String userId, {
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if ((query ?? '').trim().isNotEmpty) {
      params['query'] = query!.trim();
    }
    if ((cursor ?? '').trim().isNotEmpty) {
      params['cursor'] = cursor!.trim();
    }
    final url = _uri(
      UserApiMetadata.listFollowingPath(subAccountId: userId),
      queryParameters: params,
    );
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listFollowing),
    );
    if (resp.statusCode != 200) {
      throw Exception('listFollowing failed: ${resp.statusCode}');
    }
    final page = CloudResponseDecoder.asCursorPage(
      json.decode(resp.body),
      context: UserRequestPageIds.listFollowing,
    );
    return CursorPage<ProfileSocialRelationRowViewData>(
      items: page.items
          .map(_normalizeRelationshipItem)
          .map(
            (m) =>
                ProfileSocialRelationRowViewData.fromProfileSocialRelationRowWire(
                  ProfileSocialRelationRowWireDto.fromMap(m),
                ),
          )
          .toList(growable: false),
      nextCursor: page.nextCursor,
      totalCount: page.totalCount,
    );
  }

  @override
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowersPage(
    String userId, {
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if ((query ?? '').trim().isNotEmpty) {
      params['query'] = query!.trim();
    }
    if ((cursor ?? '').trim().isNotEmpty) {
      params['cursor'] = cursor!.trim();
    }
    final url = _uri(
      UserApiMetadata.listFollowersPath(subAccountId: userId),
      queryParameters: params,
    );
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listFollowers),
    );
    if (resp.statusCode != 200) {
      throw Exception('listFollowers failed: ${resp.statusCode}');
    }
    final page = CloudResponseDecoder.asCursorPage(
      json.decode(resp.body),
      context: UserRequestPageIds.listFollowers,
    );
    return CursorPage<ProfileSocialRelationRowViewData>(
      items: page.items
          .map(_normalizeRelationshipItem)
          .map(
            (m) =>
                ProfileSocialRelationRowViewData.fromProfileSocialRelationRowWire(
                  ProfileSocialRelationRowWireDto.fromMap(m),
                ),
          )
          .toList(growable: false),
      nextCursor: page.nextCursor,
      totalCount: page.totalCount,
    );
  }

  @override
  Future<RelationshipViewData> getRelationship(String userId) async {
    final url = _uri(UserApiMetadata.getRelationshipPath(subAccountId: userId));
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.getRelationship),
    );
    if (resp.statusCode != 200) {
      throw Exception('getRelationship failed: ${resp.statusCode}');
    }
    final data = CloudResponseDecoder.asObject(
      json.decode(resp.body),
      context: UserRequestPageIds.getRelationship,
    );
    return RelationshipViewData.fromRelationshipNormalizedWire(
      _relationshipNormalizedFromRaw(data),
    );
  }

  @override
  Future<List<ProfileUserLikeRowViewData>> listUserLikes(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if (cursor != null) params['cursor'] = cursor;
    final url = _uri(
      UserApiMetadata.listUserLikesPath(userId: userId),
      queryParameters: params,
    );
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listUserLikes),
    );
    if (resp.statusCode != 200) {
      throw Exception('listUserLikes failed: ${resp.statusCode}');
    }
    final data = CloudResponseDecoder.asObject(
      json.decode(resp.body),
      context: UserRequestPageIds.listUserLikes,
    );
    final items = CloudResponseDecoder.mapList(data, 'items');
    return items
        .map(
          (m) => ProfileUserLikeRowViewData.fromProfileUserLikeRowWire(
            ProfileUserLikeRowWireDto.fromMap(m),
          ),
        )
        .toList(growable: false);
  }

  @override
  Future<List<ProfileInteractionActivityViewData>> listUserInteractionReceived(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if (cursor != null) params['cursor'] = cursor;
    final url = _uri(
      ContentApiMetadata.listProfileInteractionActivitiesReceivedPath(
        subAccountId: userId,
      ),
      queryParameters: params,
    );
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.listProfileInteractionActivitiesReceived,
      ),
    );
    if (resp.statusCode != 200) {
      _throwStatus(resp, url.path);
    }
    return _decodeItemsAs(
      resp,
      ContentRequestPageIds.listProfileInteractionActivitiesReceived,
      (m) =>
          ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
            ProfileInteractionActivityWireDto.fromMap(m),
          ),
    );
  }

  @override
  Future<List<ProfileInteractionActivityViewData>> listUserInteractionSent(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if (cursor != null) params['cursor'] = cursor;
    final url = _uri(
      ContentApiMetadata.listProfileInteractionActivitiesSentPath(
        subAccountId: userId,
      ),
      queryParameters: params,
    );
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.listProfileInteractionActivitiesSent,
      ),
    );
    if (resp.statusCode != 200) {
      _throwStatus(resp, url.path);
    }
    return _decodeItemsAs(
      resp,
      ContentRequestPageIds.listProfileInteractionActivitiesSent,
      (m) =>
          ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
            ProfileInteractionActivityWireDto.fromMap(m),
          ),
    );
  }

  @override
  Future<CursorPage<ProfileInteractionActivityViewData>>
  listProfileShareInteractions(
    String subAccountId, {
    required String direction,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final isReceived = direction == 'received';
    final path = isReceived
        ? ContentApiMetadata.listProfileInteractionActivitiesReceivedPath(
            subAccountId: subAccountId,
          )
        : ContentApiMetadata.listProfileInteractionActivitiesSentPath(
            subAccountId: subAccountId,
          );
    final context = isReceived
        ? ContentRequestPageIds.listProfileInteractionActivitiesReceived
        : ContentRequestPageIds.listProfileInteractionActivitiesSent;
    final params = <String, String>{'type': 'share', 'limit': '$limit'};
    if (cursor != null && cursor.trim().isNotEmpty) {
      params['cursor'] = cursor.trim();
    }
    final response = await _httpClient.get(
      _uri(path, queryParameters: params),
      headers: CloudRequestHeaders.forPage(context),
    );
    if (response.statusCode != 200) {
      _throwStatus(response, path);
    }
    final payload = CloudResponseDecoder.asObject(
      json.decode(response.body),
      context: context,
    );
    final items = CloudResponseDecoder.mapList(payload, 'items')
        .map(
          (item) =>
              ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
                ProfileInteractionActivityWireDto.fromMap(item),
              ),
        )
        .toList(growable: false);
    final nextCursor = payload['nextCursor']?.toString().trim();
    return CursorPage<ProfileInteractionActivityViewData>(
      items: items,
      nextCursor: nextCursor == null || nextCursor.isEmpty ? null : nextCursor,
    );
  }

  @override
  Future<void> markProfileShareInteractionState(
    String subAccountId,
    String interactionId, {
    required String state,
  }) async {
    final path = ContentApiMetadata.updateProfileInteractionStatePath(
      subAccountId: subAccountId,
      interactionId: interactionId,
    );
    final response = await _httpClient.patch(
      _uri(path, queryParameters: <String, String>{'state': state}),
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.updateProfileInteractionState,
      ),
    );
    if (response.statusCode != 204) {
      _throwStatus(response, path);
    }
  }

  // ── 分身 ──────────────────────────────────────────────────────────────────

  @override
  Future<List<PersonaManagementItemWireDto>> listPersonas() async {
    final url = _uri(UserApiMetadata.listPersonasPath);
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listPersonas),
    );
    if (resp.statusCode != 200) {
      throw Exception('listPersonas failed: ${resp.statusCode}');
    }
    final data = CloudResponseDecoder.asObject(
      json.decode(resp.body),
      context: UserRequestPageIds.listPersonas,
    );
    final items = CloudResponseDecoder.mapList(data, 'items');
    return items.map(_personaDtoFromWire).toList(growable: false);
  }

  @override
  Future<PersonaManagementItemWireDto> createPersona(
    PersonaCreateRequestDto request,
  ) async {
    final url = _uri(UserApiMetadata.createPersonaPath);
    final bodyMap = _omitNullMapValues(request.toMap());
    final resp = await _httpClient.post(
      url,
      headers: {
        ...CloudRequestHeaders.forPage(UserRequestPageIds.createPersona),
        'Content-Type': 'application/json',
      },
      body: json.encode(bodyMap),
    );
    if (resp.statusCode != 200 && resp.statusCode != 201) {
      throw Exception('createPersona failed: ${resp.statusCode}');
    }
    final body = json.decode(resp.body);
    final map = CloudResponseDecoder.asObject(
      body,
      context: UserRequestPageIds.createPersona,
    );
    return _personaDtoFromWire(map);
  }

  @override
  Future<void> updatePersona(
    String subAccountId,
    PersonaUpdateRequestDto request,
  ) async {
    final url = _uri(
      UserApiMetadata.updatePersonaPath(subAccountId: subAccountId),
    );
    final bodyMap = _omitNullMapValues(request.toMap());
    final resp = await _httpClient.patch(
      url,
      headers: {
        ...CloudRequestHeaders.forPage(UserRequestPageIds.updatePersona),
        'Content-Type': 'application/json',
      },
      body: json.encode(bodyMap),
    );
    if (resp.statusCode != 200) {
      throw Exception('updatePersona failed: ${resp.statusCode}');
    }
  }

  @override
  Future<void> deletePersona(String subAccountId) async {
    final url = _uri(
      UserApiMetadata.deleteEmptyPersonaPath(subAccountId: subAccountId),
    );
    final resp = await _httpClient.delete(
      url,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.deleteEmptyPersona,
      ),
    );
    if (resp.statusCode != 200 && resp.statusCode != 204) {
      throw Exception('deletePersona failed: ${resp.statusCode}');
    }
  }

  @override
  Future<void> activatePersona(String subAccountId) async {
    final url = _uri(
      UserApiMetadata.activatePersonaPath(subAccountId: subAccountId),
    );
    final resp = await _httpClient.post(
      url,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.activatePersona),
    );
    if (resp.statusCode != 200) {
      throw Exception('activatePersona failed: ${resp.statusCode}');
    }
  }

  // ── Private helpers ───────────────────────────────────────────────────────

  static UserWorkItem _workItemFromMap(Map<String, dynamic> m) {
    return UserWorkItem(
      id: m['id']?.toString() ?? '',
      type: m['type']?.toString() ?? '',
      title: m['title']?.toString() ?? '',
      coverUrl: m['coverUrl']?.toString() ?? '',
      likeCount: (m['likeCount'] as num?)?.toInt() ?? 0,
      date: m['date']?.toString() ?? '',
      desc: m['desc']?.toString() ?? '',
    );
  }

  static UserLifeItem _lifeItemFromMap(Map<String, dynamic> m) {
    return UserLifeItem(
      id: m['id']?.toString() ?? '',
      category: m['category']?.toString() ?? '',
      title: m['title']?.toString() ?? '',
      subtitle: m['subtitle']?.toString() ?? '',
      imageUrl: m['imageUrl']?.toString() ?? '',
      refId: m['refId']?.toString() ?? '',
    );
  }
}
