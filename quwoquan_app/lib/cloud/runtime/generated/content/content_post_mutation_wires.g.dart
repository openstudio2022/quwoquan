// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: contracts/metadata/content/post/service.yaml (writable_fields per operation).
// Regenerate: make codegen-app

Map<String, dynamic> _mutationPutOpt(Map<String, dynamic> m, String k, Object? v) {
  if (v == null) return m;
  m[k] = v;
  return m;
}

List<String>? _mutationStringList(Object? v) {
  if (v == null) return null;
  if (v is List) {
    return v.map((e) => e.toString()).where((s) => s.isNotEmpty).toList(growable: false);
  }
  return null;
}

Map<String, dynamic>? _mutationStringKeyedMap(Object? v) {
  if (v is! Map) return null;
  return Map<String, dynamic>.from(v as Map);
}

/// HTTP body for CreatePost (metadata writable_fields).
class CreatePostRequestWire {
  CreatePostRequestWire({
    this.type,
    this.contentType,
    this.contentIdentity,
    this.title,
    this.body,
    this.summary,
    this.tags,
    this.mediaUrls,
    this.coverUrl,
    this.articleDocument,
    this.videoUrl,
    this.illustrationAssetId,
    this.location,
    this.locationName,
    this.primaryHomepageId,
    this.primaryHomepageType,
    this.primaryHomepageSnapshot,
    this.visibility,
    this.circleIds,
    this.groupId,
    this.nodeId,
    this.assistantUsePolicy,
    this.sourcePostId,
    this.sourceType,
    this.deviceInfo,
    this.publishLocation,
    this.personaId,
    this.profileSubjectId,
    this.personaContextVersion,
  });

  final String? type;
  final String? contentType;
  final String? contentIdentity;
  final String? title;
  final String? body;
  final String? summary;
  final List<String>? tags;
  final List<String>? mediaUrls;
  final String? coverUrl;
  final Map<String, dynamic>? articleDocument;
  final String? videoUrl;
  final String? illustrationAssetId;
  final Map<String, dynamic>? location;
  final String? locationName;
  final String? primaryHomepageId;
  final String? primaryHomepageType;
  final Map<String, dynamic>? primaryHomepageSnapshot;
  final String? visibility;
  final List<String>? circleIds;
  final String? groupId;
  final String? nodeId;
  final String? assistantUsePolicy;
  final String? sourcePostId;
  final String? sourceType;
  final Map<String, dynamic>? deviceInfo;
  final Map<String, dynamic>? publishLocation;
  final String? personaId;
  final String? profileSubjectId;
  final String? personaContextVersion;

  Map<String, dynamic> toWire() {
    final m = <String, dynamic>{};
    _mutationPutOpt(m, 'type', type);
    _mutationPutOpt(m, 'contentType', contentType);
    _mutationPutOpt(m, 'contentIdentity', contentIdentity);
    _mutationPutOpt(m, 'title', title);
    _mutationPutOpt(m, 'body', body);
    _mutationPutOpt(m, 'summary', summary);
    if (tags != null) m['tags'] = tags!;
    if (mediaUrls != null) m['mediaUrls'] = mediaUrls!;
    _mutationPutOpt(m, 'coverUrl', coverUrl);
    if (articleDocument != null) m['articleDocument'] = articleDocument!;
    _mutationPutOpt(m, 'videoUrl', videoUrl);
    _mutationPutOpt(m, 'illustrationAssetId', illustrationAssetId);
    if (location != null) m['location'] = location!;
    _mutationPutOpt(m, 'locationName', locationName);
    _mutationPutOpt(m, 'primaryHomepageId', primaryHomepageId);
    _mutationPutOpt(m, 'primaryHomepageType', primaryHomepageType);
    if (primaryHomepageSnapshot != null) m['primaryHomepageSnapshot'] = primaryHomepageSnapshot!;
    _mutationPutOpt(m, 'visibility', visibility);
    if (circleIds != null) m['circleIds'] = circleIds!;
    _mutationPutOpt(m, 'groupId', groupId);
    _mutationPutOpt(m, 'nodeId', nodeId);
    _mutationPutOpt(m, 'assistantUsePolicy', assistantUsePolicy);
    _mutationPutOpt(m, 'sourcePostId', sourcePostId);
    _mutationPutOpt(m, 'sourceType', sourceType);
    if (deviceInfo != null) m['deviceInfo'] = deviceInfo!;
    if (publishLocation != null) m['publishLocation'] = publishLocation!;
    _mutationPutOpt(m, 'personaId', personaId);
    _mutationPutOpt(m, 'profileSubjectId', profileSubjectId);
    _mutationPutOpt(m, 'personaContextVersion', personaContextVersion);
    return m;
  }

  factory CreatePostRequestWire.fromMap(Map<String, dynamic> m) {
    return CreatePostRequestWire(
      type: m['type']?.toString(),
      contentType: m['contentType']?.toString(),
      contentIdentity: m['contentIdentity']?.toString(),
      title: m['title']?.toString(),
      body: m['body']?.toString(),
      summary: m['summary']?.toString(),
      tags: _mutationStringList(m['tags']),
      mediaUrls: _mutationStringList(m['mediaUrls']),
      coverUrl: m['coverUrl']?.toString(),
      articleDocument: _mutationStringKeyedMap(m['articleDocument']),
      videoUrl: m['videoUrl']?.toString(),
      illustrationAssetId: m['illustrationAssetId']?.toString(),
      location: _mutationStringKeyedMap(m['location']),
      locationName: m['locationName']?.toString(),
      primaryHomepageId: m['primaryHomepageId']?.toString(),
      primaryHomepageType: m['primaryHomepageType']?.toString(),
      primaryHomepageSnapshot: _mutationStringKeyedMap(m['primaryHomepageSnapshot']),
      visibility: m['visibility']?.toString(),
      circleIds: _mutationStringList(m['circleIds']),
      groupId: m['groupId']?.toString(),
      nodeId: m['nodeId']?.toString(),
      assistantUsePolicy: m['assistantUsePolicy']?.toString(),
      sourcePostId: m['sourcePostId']?.toString(),
      sourceType: m['sourceType']?.toString(),
      deviceInfo: _mutationStringKeyedMap(m['deviceInfo']),
      publishLocation: _mutationStringKeyedMap(m['publishLocation']),
      personaId: m['personaId']?.toString(),
      profileSubjectId: m['profileSubjectId']?.toString(),
      personaContextVersion: m['personaContextVersion']?.toString(),
    );
  }
}

/// HTTP body for UpdatePost (metadata writable_fields).
class UpdatePostRequestWire {
  UpdatePostRequestWire({
    this.contentType,
    this.contentIdentity,
    this.title,
    this.body,
    this.summary,
    this.tags,
    this.mediaUrls,
    this.coverUrl,
    this.articleDocument,
    this.videoUrl,
    this.illustrationAssetId,
    this.location,
    this.locationName,
    this.primaryHomepageId,
    this.primaryHomepageType,
    this.primaryHomepageSnapshot,
    this.visibility,
    this.circleIds,
    this.groupId,
    this.nodeId,
    this.assistantUsePolicy,
  });

  final String? contentType;
  final String? contentIdentity;
  final String? title;
  final String? body;
  final String? summary;
  final List<String>? tags;
  final List<String>? mediaUrls;
  final String? coverUrl;
  final Map<String, dynamic>? articleDocument;
  final String? videoUrl;
  final String? illustrationAssetId;
  final Map<String, dynamic>? location;
  final String? locationName;
  final String? primaryHomepageId;
  final String? primaryHomepageType;
  final Map<String, dynamic>? primaryHomepageSnapshot;
  final String? visibility;
  final List<String>? circleIds;
  final String? groupId;
  final String? nodeId;
  final String? assistantUsePolicy;

  Map<String, dynamic> toWire() {
    final m = <String, dynamic>{};
    _mutationPutOpt(m, 'contentType', contentType);
    _mutationPutOpt(m, 'contentIdentity', contentIdentity);
    _mutationPutOpt(m, 'title', title);
    _mutationPutOpt(m, 'body', body);
    _mutationPutOpt(m, 'summary', summary);
    if (tags != null) m['tags'] = tags!;
    if (mediaUrls != null) m['mediaUrls'] = mediaUrls!;
    _mutationPutOpt(m, 'coverUrl', coverUrl);
    if (articleDocument != null) m['articleDocument'] = articleDocument!;
    _mutationPutOpt(m, 'videoUrl', videoUrl);
    _mutationPutOpt(m, 'illustrationAssetId', illustrationAssetId);
    if (location != null) m['location'] = location!;
    _mutationPutOpt(m, 'locationName', locationName);
    _mutationPutOpt(m, 'primaryHomepageId', primaryHomepageId);
    _mutationPutOpt(m, 'primaryHomepageType', primaryHomepageType);
    if (primaryHomepageSnapshot != null) m['primaryHomepageSnapshot'] = primaryHomepageSnapshot!;
    _mutationPutOpt(m, 'visibility', visibility);
    if (circleIds != null) m['circleIds'] = circleIds!;
    _mutationPutOpt(m, 'groupId', groupId);
    _mutationPutOpt(m, 'nodeId', nodeId);
    _mutationPutOpt(m, 'assistantUsePolicy', assistantUsePolicy);
    return m;
  }

  factory UpdatePostRequestWire.fromMap(Map<String, dynamic> m) {
    return UpdatePostRequestWire(
      contentType: m['contentType']?.toString(),
      contentIdentity: m['contentIdentity']?.toString(),
      title: m['title']?.toString(),
      body: m['body']?.toString(),
      summary: m['summary']?.toString(),
      tags: _mutationStringList(m['tags']),
      mediaUrls: _mutationStringList(m['mediaUrls']),
      coverUrl: m['coverUrl']?.toString(),
      articleDocument: _mutationStringKeyedMap(m['articleDocument']),
      videoUrl: m['videoUrl']?.toString(),
      illustrationAssetId: m['illustrationAssetId']?.toString(),
      location: _mutationStringKeyedMap(m['location']),
      locationName: m['locationName']?.toString(),
      primaryHomepageId: m['primaryHomepageId']?.toString(),
      primaryHomepageType: m['primaryHomepageType']?.toString(),
      primaryHomepageSnapshot: _mutationStringKeyedMap(m['primaryHomepageSnapshot']),
      visibility: m['visibility']?.toString(),
      circleIds: _mutationStringList(m['circleIds']),
      groupId: m['groupId']?.toString(),
      nodeId: m['nodeId']?.toString(),
      assistantUsePolicy: m['assistantUsePolicy']?.toString(),
    );
  }
}

/// HTTP body for PublishPost (metadata writable_fields).
class PublishPostRequestWire {
  PublishPostRequestWire({
    this.contentIdentity,
    this.primaryHomepageId,
    this.primaryHomepageType,
    this.primaryHomepageSnapshot,
    this.visibility,
    this.circleIds,
    this.groupId,
    this.nodeId,
    this.assistantUsePolicy,
  });

  final String? contentIdentity;
  final String? primaryHomepageId;
  final String? primaryHomepageType;
  final Map<String, dynamic>? primaryHomepageSnapshot;
  final String? visibility;
  final List<String>? circleIds;
  final String? groupId;
  final String? nodeId;
  final String? assistantUsePolicy;

  Map<String, dynamic> toWire() {
    final m = <String, dynamic>{};
    _mutationPutOpt(m, 'contentIdentity', contentIdentity);
    _mutationPutOpt(m, 'primaryHomepageId', primaryHomepageId);
    _mutationPutOpt(m, 'primaryHomepageType', primaryHomepageType);
    if (primaryHomepageSnapshot != null) m['primaryHomepageSnapshot'] = primaryHomepageSnapshot!;
    _mutationPutOpt(m, 'visibility', visibility);
    if (circleIds != null) m['circleIds'] = circleIds!;
    _mutationPutOpt(m, 'groupId', groupId);
    _mutationPutOpt(m, 'nodeId', nodeId);
    _mutationPutOpt(m, 'assistantUsePolicy', assistantUsePolicy);
    return m;
  }

  factory PublishPostRequestWire.fromMap(Map<String, dynamic> m) {
    return PublishPostRequestWire(
      contentIdentity: m['contentIdentity']?.toString(),
      primaryHomepageId: m['primaryHomepageId']?.toString(),
      primaryHomepageType: m['primaryHomepageType']?.toString(),
      primaryHomepageSnapshot: _mutationStringKeyedMap(m['primaryHomepageSnapshot']),
      visibility: m['visibility']?.toString(),
      circleIds: _mutationStringList(m['circleIds']),
      groupId: m['groupId']?.toString(),
      nodeId: m['nodeId']?.toString(),
      assistantUsePolicy: m['assistantUsePolicy']?.toString(),
    );
  }
}

/// HTTP body for UpdatePostSettings (metadata writable_fields).
class UpdatePostSettingsRequestWire {
  UpdatePostSettingsRequestWire({
    this.visibility,
    this.primaryHomepageId,
    this.primaryHomepageType,
    this.primaryHomepageSnapshot,
    this.circleIds,
    this.groupId,
    this.nodeId,
    this.assistantUsePolicy,
  });

  final String? visibility;
  final String? primaryHomepageId;
  final String? primaryHomepageType;
  final Map<String, dynamic>? primaryHomepageSnapshot;
  final List<String>? circleIds;
  final String? groupId;
  final String? nodeId;
  final String? assistantUsePolicy;

  Map<String, dynamic> toWire() {
    final m = <String, dynamic>{};
    _mutationPutOpt(m, 'visibility', visibility);
    _mutationPutOpt(m, 'primaryHomepageId', primaryHomepageId);
    _mutationPutOpt(m, 'primaryHomepageType', primaryHomepageType);
    if (primaryHomepageSnapshot != null) m['primaryHomepageSnapshot'] = primaryHomepageSnapshot!;
    if (circleIds != null) m['circleIds'] = circleIds!;
    _mutationPutOpt(m, 'groupId', groupId);
    _mutationPutOpt(m, 'nodeId', nodeId);
    _mutationPutOpt(m, 'assistantUsePolicy', assistantUsePolicy);
    return m;
  }

  factory UpdatePostSettingsRequestWire.fromMap(Map<String, dynamic> m) {
    return UpdatePostSettingsRequestWire(
      visibility: m['visibility']?.toString(),
      primaryHomepageId: m['primaryHomepageId']?.toString(),
      primaryHomepageType: m['primaryHomepageType']?.toString(),
      primaryHomepageSnapshot: _mutationStringKeyedMap(m['primaryHomepageSnapshot']),
      circleIds: _mutationStringList(m['circleIds']),
      groupId: m['groupId']?.toString(),
      nodeId: m['nodeId']?.toString(),
      assistantUsePolicy: m['assistantUsePolicy']?.toString(),
    );
  }
}

/// HTTP body for PromotePostToWork (metadata writable_fields).
class PromotePostToWorkRequestWire {
  PromotePostToWorkRequestWire({
    this.contentType,
    this.title,
    this.summary,
    this.tags,
    this.coverUrl,
    this.articleDocument,
    this.primaryHomepageId,
    this.primaryHomepageType,
    this.primaryHomepageSnapshot,
    this.visibility,
    this.circleIds,
    this.groupId,
    this.nodeId,
    this.assistantUsePolicy,
  });

  final String? contentType;
  final String? title;
  final String? summary;
  final List<String>? tags;
  final String? coverUrl;
  final Map<String, dynamic>? articleDocument;
  final String? primaryHomepageId;
  final String? primaryHomepageType;
  final Map<String, dynamic>? primaryHomepageSnapshot;
  final String? visibility;
  final List<String>? circleIds;
  final String? groupId;
  final String? nodeId;
  final String? assistantUsePolicy;

  Map<String, dynamic> toWire() {
    final m = <String, dynamic>{};
    _mutationPutOpt(m, 'contentType', contentType);
    _mutationPutOpt(m, 'title', title);
    _mutationPutOpt(m, 'summary', summary);
    if (tags != null) m['tags'] = tags!;
    _mutationPutOpt(m, 'coverUrl', coverUrl);
    if (articleDocument != null) m['articleDocument'] = articleDocument!;
    _mutationPutOpt(m, 'primaryHomepageId', primaryHomepageId);
    _mutationPutOpt(m, 'primaryHomepageType', primaryHomepageType);
    if (primaryHomepageSnapshot != null) m['primaryHomepageSnapshot'] = primaryHomepageSnapshot!;
    _mutationPutOpt(m, 'visibility', visibility);
    if (circleIds != null) m['circleIds'] = circleIds!;
    _mutationPutOpt(m, 'groupId', groupId);
    _mutationPutOpt(m, 'nodeId', nodeId);
    _mutationPutOpt(m, 'assistantUsePolicy', assistantUsePolicy);
    return m;
  }

  factory PromotePostToWorkRequestWire.fromMap(Map<String, dynamic> m) {
    return PromotePostToWorkRequestWire(
      contentType: m['contentType']?.toString(),
      title: m['title']?.toString(),
      summary: m['summary']?.toString(),
      tags: _mutationStringList(m['tags']),
      coverUrl: m['coverUrl']?.toString(),
      articleDocument: _mutationStringKeyedMap(m['articleDocument']),
      primaryHomepageId: m['primaryHomepageId']?.toString(),
      primaryHomepageType: m['primaryHomepageType']?.toString(),
      primaryHomepageSnapshot: _mutationStringKeyedMap(m['primaryHomepageSnapshot']),
      visibility: m['visibility']?.toString(),
      circleIds: _mutationStringList(m['circleIds']),
      groupId: m['groupId']?.toString(),
      nodeId: m['nodeId']?.toString(),
      assistantUsePolicy: m['assistantUsePolicy']?.toString(),
    );
  }
}

