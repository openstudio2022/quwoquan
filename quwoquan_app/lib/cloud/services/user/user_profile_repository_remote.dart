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

  static String _normalizeRelationshipState(Map<String, dynamic> map) {
    final state = map['relationState']?.toString() ?? '';
    if (state.isNotEmpty) {
      return state;
    }
    final isFollowing = map['isFollowing'] == true;
    final isFollowedBy = map['isFollowedBy'] == true;
    if (isFollowing && isFollowedBy) return 'mutual';
    if (isFollowing) return 'following';
    if (isFollowedBy) return 'followed_by';
    return 'not_following';
  }

  static Map<String, dynamic> _normalizeRelationshipItem(
    Map<String, dynamic> raw,
  ) {
    final subAccountId =
        raw['subAccountId']?.toString() ??
        raw['targetSubAccountId']?.toString() ??
        raw['userId']?.toString() ??
        '';
    final displayName =
        raw['displayName']?.toString() ??
        raw['nickname']?.toString() ??
        subAccountId;
    final avatarUrl =
        raw['avatarUrl']?.toString() ??
        raw['avatarUrlSnapshot']?.toString() ??
        '';
    return <String, dynamic>{
      ...raw,
      'subAccountId': subAccountId,
      'userId': subAccountId,
      'displayName': displayName,
      'nickname': displayName,
      'avatarUrl': avatarUrl,
    };
  }

  static RelationshipNormalizedWireDto relationshipNormalizedFromRaw(
    Map<String, dynamic> raw,
  ) {
    final relationState = _normalizeRelationshipState(raw);
    final isMutual = relationState == 'mutual';
    final isFollowing = relationState == 'following' || isMutual;
    final isFollowedBy = relationState == 'followed_by' || isMutual;
    return RelationshipNormalizedWireDto(
      relationState: relationState,
      isFollowing: raw['isFollowing'] == true || isFollowing,
      isFollowedBy: raw['isFollowedBy'] == true || isFollowedBy,
      isMutual: raw['isMutual'] == true || isMutual,
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
      throw Exception('updateProfile failed: ${resp.statusCode}');
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
  Future<List<CircleDto>> listUserCircles(
    String userId, {
    int limit = CloudApiDefaults.userCirclesLimit,
  }) async {
    final url = _uri(
      CircleApiMetadata.listUserCirclesPath(userId: userId),
      queryParameters: <String, String>{'limit': '$limit'},
    );
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.listUserCircles,
      ),
    );
    if (resp.statusCode != 200) {
      throw Exception('listUserCircles failed: ${resp.statusCode}');
    }
    final data = CloudResponseDecoder.asObject(
      json.decode(resp.body),
      context: CircleRequestPageIds.listUserCircles,
    );
    final items = CloudResponseDecoder.mapList(data, 'items');
    return items.map(CircleDto.fromMap).toList(growable: false);
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
    final url = _uri(UserApiMetadata.listRecentSearchesPath);
    final resp = await _httpClient.get(
      url,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.listRecentSearches,
      ),
    );
    if (resp.statusCode != 200) {
      throw Exception('listRecentSearches failed: ${resp.statusCode}');
    }
    return _decodeItemsAs(
      resp,
      UserRequestPageIds.listRecentSearches,
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
    final url = _uri(UserApiMetadata.upsertRecentSearchPath(entryId: entryId));
    final resp = await _httpClient.put(
      url,
      headers: {
        ...CloudRequestHeaders.forPage(UserRequestPageIds.upsertRecentSearch),
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
        _decodeObject(resp, UserRequestPageIds.upsertRecentSearch),
      ),
    );
  }

  @override
  Future<void> deleteRecentSearch(String entryId) async {
    final url = _uri(UserApiMetadata.deleteRecentSearchPath(entryId: entryId));
    final resp = await _httpClient.delete(
      url,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.deleteRecentSearch,
      ),
    );
    if (resp.statusCode != 200 && resp.statusCode != 204) {
      throw Exception('deleteRecentSearch failed: ${resp.statusCode}');
    }
  }

  @override
  Future<void> clearRecentSearches() async {
    final url = _uri(UserApiMetadata.clearRecentSearchesPath);
    final resp = await _httpClient.delete(
      url,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.clearRecentSearches,
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
  Future<List<ProfileSocialRelationRowViewData>> listFollowing(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if (cursor != null) params['cursor'] = cursor;
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
    return _decodeItems(resp, UserRequestPageIds.listFollowing)
        .map(_normalizeRelationshipItem)
        .map(
          (m) =>
              ProfileSocialRelationRowViewData.fromProfileSocialRelationRowWire(
                ProfileSocialRelationRowWireDto.fromMap(m),
              ),
        )
        .toList(growable: false);
  }

  @override
  Future<List<ProfileSocialRelationRowViewData>> listFollowers(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if (cursor != null) params['cursor'] = cursor;
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
    return _decodeItems(resp, UserRequestPageIds.listFollowers)
        .map(_normalizeRelationshipItem)
        .map(
          (m) =>
              ProfileSocialRelationRowViewData.fromProfileSocialRelationRowWire(
                ProfileSocialRelationRowWireDto.fromMap(m),
              ),
        )
        .toList(growable: false);
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
      relationshipNormalizedFromRaw(data),
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
    if (resp.statusCode == 200) {
      return _decodeItemsAs(
        resp,
        ContentRequestPageIds.listProfileInteractionActivitiesReceived,
        (m) =>
            ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
              ProfileInteractionActivityWireDto.fromMap(m),
            ),
      );
    }
    if (resp.statusCode == 204 ||
        resp.statusCode == 404 ||
        resp.statusCode == 501) {
      return const <ProfileInteractionActivityViewData>[];
    }
    throw Exception('listUserInteractionReceived failed: ${resp.statusCode}');
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
    if (resp.statusCode == 200) {
      return _decodeItemsAs(
        resp,
        ContentRequestPageIds.listProfileInteractionActivitiesSent,
        (m) =>
            ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
              ProfileInteractionActivityWireDto.fromMap(m),
            ),
      );
    }
    if (resp.statusCode == 204 ||
        resp.statusCode == 404 ||
        resp.statusCode == 501) {
      return const <ProfileInteractionActivityViewData>[];
    }
    throw Exception('listUserInteractionSent failed: ${resp.statusCode}');
  }

  // ── 分身 ──────────────────────────────────────────────────────────────────

  @override
  Future<List<PersonaDto>> listPersonas() async {
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
  Future<PersonaDto> createPersona(PersonaCreateRequestDto request) async {
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
