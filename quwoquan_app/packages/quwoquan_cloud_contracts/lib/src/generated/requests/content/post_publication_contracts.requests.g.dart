// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../content/post_publication_contracts.dart';

List<String> _normalizeGeneratedTextList(
  Iterable<String> values, {
  required bool deduplicate,
}) {
  final result = <String>[];
  final seen = <String>{};
  for (final value in values) {
    final normalized = value.trim();
    if (normalized.isEmpty) continue;
    if (deduplicate && !seen.add(normalized)) continue;
    result.add(normalized);
  }
  return List<String>.unmodifiable(result);
}

final class GeoPoint {
  const GeoPoint({
    required double latitude,
    required double longitude,
  }) : latitude = latitude,
       longitude = longitude;

  final double latitude;
  final double longitude;

  Map<String, Object?> toJson() => <String, Object?>{
    "latitude": this.latitude,
    "longitude": this.longitude,
  };
}

final class PostArticleAssetInput {
  const PostArticleAssetInput({
    required String assetId,
    String? role,
    String? layout,
    String? caption,
  }) : assetId = assetId,
       role = role,
       layout = layout,
       caption = caption;

  final String assetId;
  final String? role;
  final String? layout;
  final String? caption;

  Map<String, Object?> toJson() => <String, Object?>{
    "assetId": this.assetId,
    if (this.role != null) "role": this.role!,
    if (this.layout != null) "layout": this.layout!,
    if (this.caption != null) "caption": this.caption!,
  };
}

final class PostArticleAssetManifestInput {
  PostArticleAssetManifestInput({
    required String schema,
    String? markdownVersion,
    required List<PostArticleAssetInput> assets,
  }) : schema = schema,
       markdownVersion = markdownVersion,
       assets = List.unmodifiable(assets) {
  }

  final String schema;
  final String? markdownVersion;
  final List<PostArticleAssetInput> assets;

  Map<String, Object?> toJson() => <String, Object?>{
    "schema": this.schema,
    if (this.markdownVersion != null) "markdownVersion": this.markdownVersion!,
    "assets": this.assets.map((value) => value.toJson()).toList(growable: false),
  };
}

final class PostArticleLayoutPolicy {
  const PostArticleLayoutPolicy({
    String? wrapDowngrade,
    String? galleryDowngrade,
  }) : wrapDowngrade = wrapDowngrade,
       galleryDowngrade = galleryDowngrade;

  final String? wrapDowngrade;
  final String? galleryDowngrade;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.wrapDowngrade != null) "wrapDowngrade": this.wrapDowngrade!,
    if (this.galleryDowngrade != null) "galleryDowngrade": this.galleryDowngrade!,
  };
}

final class PostArticleRenderProfile {
  const PostArticleRenderProfile({
    String? template,
    String? fontPreset,
    String? paperThemeMode,
    String? paperTexture,
    String? contentVertical,
    PostArticleLayoutPolicy? layoutPolicy,
    int? width,
    int? height,
    int? durationMs,
  }) : template = template,
       fontPreset = fontPreset,
       paperThemeMode = paperThemeMode,
       paperTexture = paperTexture,
       contentVertical = contentVertical,
       layoutPolicy = layoutPolicy,
       width = width,
       height = height,
       durationMs = durationMs;

  final String? template;
  final String? fontPreset;
  final String? paperThemeMode;
  final String? paperTexture;
  final String? contentVertical;
  final PostArticleLayoutPolicy? layoutPolicy;
  final int? width;
  final int? height;
  final int? durationMs;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.template != null) "template": this.template!,
    if (this.fontPreset != null) "fontPreset": this.fontPreset!,
    if (this.paperThemeMode != null) "paperThemeMode": this.paperThemeMode!,
    if (this.paperTexture != null) "paperTexture": this.paperTexture!,
    if (this.contentVertical != null) "contentVertical": this.contentVertical!,
    if (this.layoutPolicy != null) "layoutPolicy": this.layoutPolicy!.toJson(),
    if (this.width != null) "width": this.width!,
    if (this.height != null) "height": this.height!,
    if (this.durationMs != null) "durationMs": this.durationMs!,
  };
}

final class PostDeviceInfo {
  const PostDeviceInfo({
    String? manufacturer,
    String? brand,
    String? model,
    String? os,
    String? appVersion,
    int? width,
    int? height,
    int? durationMs,
  }) : manufacturer = manufacturer,
       brand = brand,
       model = model,
       os = os,
       appVersion = appVersion,
       width = width,
       height = height,
       durationMs = durationMs;

  final String? manufacturer;
  final String? brand;
  final String? model;
  final String? os;
  final String? appVersion;
  final int? width;
  final int? height;
  final int? durationMs;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.manufacturer != null) "manufacturer": this.manufacturer!,
    if (this.brand != null) "brand": this.brand!,
    if (this.model != null) "model": this.model!,
    if (this.os != null) "os": this.os!,
    if (this.appVersion != null) "appVersion": this.appVersion!,
    if (this.width != null) "width": this.width!,
    if (this.height != null) "height": this.height!,
    if (this.durationMs != null) "durationMs": this.durationMs!,
  };
}

final class PostHomepageSnapshot {
  const PostHomepageSnapshot({
    String? canonicalEntityId,
    String? title,
    String? subtitle,
    String? coverUrl,
    int? width,
    int? height,
    int? durationMs,
  }) : canonicalEntityId = canonicalEntityId,
       title = title,
       subtitle = subtitle,
       coverUrl = coverUrl,
       width = width,
       height = height,
       durationMs = durationMs;

  final String? canonicalEntityId;
  final String? title;
  final String? subtitle;
  final String? coverUrl;
  final int? width;
  final int? height;
  final int? durationMs;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.canonicalEntityId != null) "canonicalEntityId": this.canonicalEntityId!,
    if (this.title != null) "title": this.title!,
    if (this.subtitle != null) "subtitle": this.subtitle!,
    if (this.coverUrl != null) "coverUrl": this.coverUrl!,
    if (this.width != null) "width": this.width!,
    if (this.height != null) "height": this.height!,
    if (this.durationMs != null) "durationMs": this.durationMs!,
  };
}

final class PostPublishLocation {
  const PostPublishLocation({
    String? country,
    String? province,
    String? city,
  }) : country = country,
       province = province,
       city = city;

  final String? country;
  final String? province;
  final String? city;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.country != null) "country": this.country!,
    if (this.province != null) "province": this.province!,
    if (this.city != null) "city": this.city!,
  };
}

final class PostSemanticMention {
  const PostSemanticMention({
    required String mentionId,
    required String kind,
    required String surface,
    required String location,
    int? rangeStart,
    int? rangeEnd,
    required String status,
    String? candidateId,
    String? targetRef,
  }) : mentionId = mentionId,
       kind = kind,
       surface = surface,
       location = location,
       rangeStart = rangeStart,
       rangeEnd = rangeEnd,
       status = status,
       candidateId = candidateId,
       targetRef = targetRef;

  final String mentionId;
  final String kind;
  final String surface;
  final String location;
  final int? rangeStart;
  final int? rangeEnd;
  final String status;
  final String? candidateId;
  final String? targetRef;

  Map<String, Object?> toJson() => <String, Object?>{
    "mentionId": this.mentionId,
    "kind": this.kind,
    "surface": this.surface,
    "location": this.location,
    if (this.rangeStart != null) "rangeStart": this.rangeStart!,
    if (this.rangeEnd != null) "rangeEnd": this.rangeEnd!,
    "status": this.status,
    if (this.candidateId != null) "candidateId": this.candidateId!,
    if (this.targetRef != null) "targetRef": this.targetRef!,
  };
}

final class SubmitContentPostPublicationCommand {
  SubmitContentPostPublicationCommand({
    required String publishIntentId,
    required String localDraftId,
    required ContentPostType contentType,
    ContentPostIdentity? contentIdentity,
    String? title,
    String? body,
    String? summary,
    Iterable<PostSemanticMention> semanticMentions = const [],
    Iterable<String> mediaAssetIds = const [],
    String? articleMarkdown,
    String? markdownDialect,
    PostArticleAssetManifestInput? articleAssetManifest,
    PostArticleRenderProfile? articleRenderProfile,
    String? coverStrategy,
    int? coverFrameTimeMs,
    String? illustrationAssetId,
    GeoPoint? location,
    String? locationName,
    String? geoTagRef,
    DateTime? visitedAt,
    Iterable<String> captureDisclosure = const <String>[],
    String? primaryHomepageId,
    String? primaryHomepageType,
    PostHomepageSnapshot? primaryHomepageSnapshot,
    ContentPostVisibility? visibility,
    ContentPostAssistantUsePolicy? assistantUsePolicy,
    String? sourcePostId,
    ContentPostSourceType? sourceType,
    PostDeviceInfo? deviceInfo,
    PostPublishLocation? publishLocation,
    String? authorDisplayNameSnapshot,
    String? authorAvatarUrlSnapshot,
    int? personaContextVersion,
  }) : publishIntentId = publishIntentId.trim(),
       localDraftId = localDraftId.trim(),
       contentType = contentType,
       contentIdentity = contentIdentity,
       title = title,
       body = body,
       summary = summary,
       semanticMentions = List.unmodifiable(semanticMentions),
       mediaAssetIds = _normalizeGeneratedTextList(mediaAssetIds, deduplicate: false),
       articleMarkdown = articleMarkdown,
       markdownDialect = markdownDialect,
       articleAssetManifest = articleAssetManifest,
       articleRenderProfile = articleRenderProfile,
       coverStrategy = coverStrategy,
       coverFrameTimeMs = coverFrameTimeMs,
       illustrationAssetId = illustrationAssetId,
       location = location,
       locationName = locationName,
       geoTagRef = geoTagRef,
       visitedAt = visitedAt,
       captureDisclosure = _normalizeGeneratedTextList(captureDisclosure, deduplicate: false),
       primaryHomepageId = primaryHomepageId,
       primaryHomepageType = primaryHomepageType,
       primaryHomepageSnapshot = primaryHomepageSnapshot,
       visibility = visibility,
       assistantUsePolicy = assistantUsePolicy,
       sourcePostId = sourcePostId,
       sourceType = sourceType,
       deviceInfo = deviceInfo,
       publishLocation = publishLocation,
       authorDisplayNameSnapshot = authorDisplayNameSnapshot,
       authorAvatarUrlSnapshot = authorAvatarUrlSnapshot,
       personaContextVersion = personaContextVersion {
    if (this.publishIntentId.isEmpty) {
      throw ArgumentError.value(this.publishIntentId, "publishIntentId", 'must not be blank');
    }
    if (this.localDraftId.isEmpty) {
      throw ArgumentError.value(this.localDraftId, "localDraftId", 'must not be blank');
    }
  }

  final String publishIntentId;
  final String localDraftId;
  final ContentPostType contentType;
  final ContentPostIdentity? contentIdentity;
  final String? title;
  final String? body;
  final String? summary;
  final List<PostSemanticMention> semanticMentions;
  final List<String> mediaAssetIds;
  final String? articleMarkdown;
  final String? markdownDialect;
  final PostArticleAssetManifestInput? articleAssetManifest;
  final PostArticleRenderProfile? articleRenderProfile;
  final String? coverStrategy;
  final int? coverFrameTimeMs;
  final String? illustrationAssetId;
  final GeoPoint? location;
  final String? locationName;
  final String? geoTagRef;
  final DateTime? visitedAt;
  final List<String> captureDisclosure;
  final String? primaryHomepageId;
  final String? primaryHomepageType;
  final PostHomepageSnapshot? primaryHomepageSnapshot;
  final ContentPostVisibility? visibility;
  final ContentPostAssistantUsePolicy? assistantUsePolicy;
  final String? sourcePostId;
  final ContentPostSourceType? sourceType;
  final PostDeviceInfo? deviceInfo;
  final PostPublishLocation? publishLocation;
  final String? authorDisplayNameSnapshot;
  final String? authorAvatarUrlSnapshot;
  final int? personaContextVersion;

  Map<String, Object?> toJson() => <String, Object?>{
    "publishIntentId": this.publishIntentId,
    "localDraftId": this.localDraftId,
    "contentType": switch (this.contentType) { ContentPostType.image => "image", ContentPostType.video => "video", ContentPostType.micro => "micro", ContentPostType.article => "article", },
    if (this.contentIdentity != null) "contentIdentity": switch (this.contentIdentity!) { ContentPostIdentity.moment => "moment", ContentPostIdentity.work => "work", },
    if (this.title != null) "title": this.title!,
    if (this.body != null) "body": this.body!,
    if (this.summary != null) "summary": this.summary!,
    if (this.semanticMentions.isNotEmpty) "semanticMentions": this.semanticMentions.map((value) => value.toJson()).toList(growable: false),
    if (this.mediaAssetIds.isNotEmpty) "mediaAssetIds": this.mediaAssetIds.map((value) => value).toList(growable: false),
    if (this.articleMarkdown != null) "articleMarkdown": this.articleMarkdown!,
    if (this.markdownDialect != null) "markdownDialect": this.markdownDialect!,
    if (this.articleAssetManifest != null) "articleAssetManifest": this.articleAssetManifest!.toJson(),
    if (this.articleRenderProfile != null) "articleRenderProfile": this.articleRenderProfile!.toJson(),
    if (this.coverStrategy != null) "coverStrategy": this.coverStrategy!,
    if (this.coverFrameTimeMs != null) "coverFrameTimeMs": this.coverFrameTimeMs!,
    if (this.illustrationAssetId != null) "illustrationAssetId": this.illustrationAssetId!,
    if (this.location != null) "location": this.location!.toJson(),
    if (this.locationName != null) "locationName": this.locationName!,
    if (this.geoTagRef != null) "geoTagRef": this.geoTagRef!,
    if (this.visitedAt != null) "visitedAt": this.visitedAt!.toUtc().toIso8601String(),
    "captureDisclosure": this.captureDisclosure.map((value) => value).toList(growable: false),
    if (this.primaryHomepageId != null) "primaryHomepageId": this.primaryHomepageId!,
    if (this.primaryHomepageType != null) "primaryHomepageType": this.primaryHomepageType!,
    if (this.primaryHomepageSnapshot != null) "primaryHomepageSnapshot": this.primaryHomepageSnapshot!.toJson(),
    if (this.visibility != null) "visibility": switch (this.visibility!) { ContentPostVisibility.public => "public", ContentPostVisibility.private => "private", },
    if (this.assistantUsePolicy != null) "assistantUsePolicy": switch (this.assistantUsePolicy!) { ContentPostAssistantUsePolicy.inherit => "inherit", ContentPostAssistantUsePolicy.exclude => "exclude", },
    if (this.sourcePostId != null) "sourcePostId": this.sourcePostId!,
    if (this.sourceType != null) "sourceType": switch (this.sourceType!) { ContentPostSourceType.original => "original", ContentPostSourceType.repost => "repost", ContentPostSourceType.quote => "quote", },
    if (this.deviceInfo != null) "deviceInfo": this.deviceInfo!.toJson(),
    if (this.publishLocation != null) "publishLocation": this.publishLocation!.toJson(),
    if (this.authorDisplayNameSnapshot != null) "authorDisplayNameSnapshot": this.authorDisplayNameSnapshot!,
    if (this.authorAvatarUrlSnapshot != null) "authorAvatarUrlSnapshot": this.authorAvatarUrlSnapshot!,
    if (this.personaContextVersion != null) "personaContextVersion": this.personaContextVersion!,
  };
}

CloudOperationRequestPayload encodeContentPostSubmitPostPublicationGeneratedRequest(SubmitContentPostPublicationCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "publishIntentId": request.publishIntentId,
      "localDraftId": request.localDraftId,
      "contentType": switch (request.contentType) { ContentPostType.image => "image", ContentPostType.video => "video", ContentPostType.micro => "micro", ContentPostType.article => "article", },
      if (request.contentIdentity != null) "contentIdentity": switch (request.contentIdentity!) { ContentPostIdentity.moment => "moment", ContentPostIdentity.work => "work", },
      if (request.title != null) "title": request.title!,
      if (request.body != null) "body": request.body!,
      if (request.summary != null) "summary": request.summary!,
      if (request.semanticMentions.isNotEmpty) "semanticMentions": request.semanticMentions.map((value) => value.toJson()).toList(growable: false),
      if (request.mediaAssetIds.isNotEmpty) "mediaAssetIds": request.mediaAssetIds.map((value) => value).toList(growable: false),
      if (request.articleMarkdown != null) "articleMarkdown": request.articleMarkdown!,
      if (request.markdownDialect != null) "markdownDialect": request.markdownDialect!,
      if (request.articleAssetManifest != null) "articleAssetManifest": request.articleAssetManifest!.toJson(),
      if (request.articleRenderProfile != null) "articleRenderProfile": request.articleRenderProfile!.toJson(),
      if (request.coverStrategy != null) "coverStrategy": request.coverStrategy!,
      if (request.coverFrameTimeMs != null) "coverFrameTimeMs": request.coverFrameTimeMs!,
      if (request.illustrationAssetId != null) "illustrationAssetId": request.illustrationAssetId!,
      if (request.location != null) "location": request.location!.toJson(),
      if (request.locationName != null) "locationName": request.locationName!,
      if (request.geoTagRef != null) "geoTagRef": request.geoTagRef!,
      if (request.visitedAt != null) "visitedAt": request.visitedAt!.toUtc().toIso8601String(),
      "captureDisclosure": request.captureDisclosure.map((value) => value).toList(growable: false),
      if (request.primaryHomepageId != null) "primaryHomepageId": request.primaryHomepageId!,
      if (request.primaryHomepageType != null) "primaryHomepageType": request.primaryHomepageType!,
      if (request.primaryHomepageSnapshot != null) "primaryHomepageSnapshot": request.primaryHomepageSnapshot!.toJson(),
      if (request.visibility != null) "visibility": switch (request.visibility!) { ContentPostVisibility.public => "public", ContentPostVisibility.private => "private", },
      if (request.assistantUsePolicy != null) "assistantUsePolicy": switch (request.assistantUsePolicy!) { ContentPostAssistantUsePolicy.inherit => "inherit", ContentPostAssistantUsePolicy.exclude => "exclude", },
      if (request.sourcePostId != null) "sourcePostId": request.sourcePostId!,
      if (request.sourceType != null) "sourceType": switch (request.sourceType!) { ContentPostSourceType.original => "original", ContentPostSourceType.repost => "repost", ContentPostSourceType.quote => "quote", },
      if (request.deviceInfo != null) "deviceInfo": request.deviceInfo!.toJson(),
      if (request.publishLocation != null) "publishLocation": request.publishLocation!.toJson(),
      if (request.authorDisplayNameSnapshot != null) "authorDisplayNameSnapshot": request.authorDisplayNameSnapshot!,
      if (request.authorAvatarUrlSnapshot != null) "authorAvatarUrlSnapshot": request.authorAvatarUrlSnapshot!,
      if (request.personaContextVersion != null) "personaContextVersion": request.personaContextVersion!,
    },
  );
}

