// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

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

Object? _encodeGeneratedStructuredValue(ContentPostStructuredValue value) =>
    switch (value) {
      ContentPostStructuredObject(:final fields) => <String, Object?>{
        for (final entry in fields.entries)
          entry.key: _encodeGeneratedStructuredValue(entry.value),
      },
      ContentPostStructuredArray(:final values) => values
          .map(_encodeGeneratedStructuredValue)
          .toList(growable: false),
      ContentPostStructuredText(:final value) => value,
      ContentPostStructuredNumber(:final value) => value,
      ContentPostStructuredBoolean(:final value) => value,
      ContentPostStructuredNull() => null,
    };

final class SubmitContentPostPublicationCommand {
  SubmitContentPostPublicationCommand({
    required String publishIntentId,
    required String localDraftId,
    required ContentPostType contentType,
    ContentPostIdentity? contentIdentity,
    String? title,
    String? body,
    String? summary,
    Iterable<ContentPostStructuredObject> semanticMentions = const [],
    Iterable<String> mediaAssetIds = const [],
    Iterable<ContentPostStructuredObject> mediaItems = const [],
    String? articleMarkdown,
    String? markdownDialect,
    ContentPostStructuredObject? articleAssetManifest,
    ContentPostStructuredObject? articleRenderProfile,
    String? coverStrategy,
    int? coverFrameTimeMs,
    String? illustrationAssetId,
    ContentPostStructuredObject? location,
    String? locationName,
    String? geoTagRef,
    DateTime? visitedAt,
    String? primaryHomepageId,
    String? primaryHomepageType,
    ContentPostStructuredObject? primaryHomepageSnapshot,
    ContentPostVisibility? visibility,
    ContentPostAssistantUsePolicy? assistantUsePolicy,
    String? sourcePostId,
    ContentPostSourceType? sourceType,
    ContentPostStructuredObject? deviceInfo,
    ContentPostStructuredObject? publishLocation,
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
       mediaItems = List.unmodifiable(mediaItems),
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
  final List<ContentPostStructuredObject> semanticMentions;
  final List<String> mediaAssetIds;
  final List<ContentPostStructuredObject> mediaItems;
  final String? articleMarkdown;
  final String? markdownDialect;
  final ContentPostStructuredObject? articleAssetManifest;
  final ContentPostStructuredObject? articleRenderProfile;
  final String? coverStrategy;
  final int? coverFrameTimeMs;
  final String? illustrationAssetId;
  final ContentPostStructuredObject? location;
  final String? locationName;
  final String? geoTagRef;
  final DateTime? visitedAt;
  final String? primaryHomepageId;
  final String? primaryHomepageType;
  final ContentPostStructuredObject? primaryHomepageSnapshot;
  final ContentPostVisibility? visibility;
  final ContentPostAssistantUsePolicy? assistantUsePolicy;
  final String? sourcePostId;
  final ContentPostSourceType? sourceType;
  final ContentPostStructuredObject? deviceInfo;
  final ContentPostStructuredObject? publishLocation;
  final String? authorDisplayNameSnapshot;
  final String? authorAvatarUrlSnapshot;
  final int? personaContextVersion;
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
      if (request.semanticMentions.isNotEmpty) "semanticMentions": request.semanticMentions.map((value) => _encodeGeneratedStructuredValue(value)).toList(growable: false),
      if (request.mediaAssetIds.isNotEmpty) "mediaAssetIds": request.mediaAssetIds.map((value) => value).toList(growable: false),
      if (request.mediaItems.isNotEmpty) "mediaItems": request.mediaItems.map((value) => _encodeGeneratedStructuredValue(value)).toList(growable: false),
      if (request.articleMarkdown != null) "articleMarkdown": request.articleMarkdown!,
      if (request.markdownDialect != null) "markdownDialect": request.markdownDialect!,
      if (request.articleAssetManifest != null) "articleAssetManifest": _encodeGeneratedStructuredValue(request.articleAssetManifest!),
      if (request.articleRenderProfile != null) "articleRenderProfile": _encodeGeneratedStructuredValue(request.articleRenderProfile!),
      if (request.coverStrategy != null) "coverStrategy": request.coverStrategy!,
      if (request.coverFrameTimeMs != null) "coverFrameTimeMs": request.coverFrameTimeMs!,
      if (request.illustrationAssetId != null) "illustrationAssetId": request.illustrationAssetId!,
      if (request.location != null) "location": _encodeGeneratedStructuredValue(request.location!),
      if (request.locationName != null) "locationName": request.locationName!,
      if (request.geoTagRef != null) "geoTagRef": request.geoTagRef!,
      if (request.visitedAt != null) "visitedAt": request.visitedAt!.toUtc().toIso8601String(),
      if (request.primaryHomepageId != null) "primaryHomepageId": request.primaryHomepageId!,
      if (request.primaryHomepageType != null) "primaryHomepageType": request.primaryHomepageType!,
      if (request.primaryHomepageSnapshot != null) "primaryHomepageSnapshot": _encodeGeneratedStructuredValue(request.primaryHomepageSnapshot!),
      if (request.visibility != null) "visibility": switch (request.visibility!) { ContentPostVisibility.public => "public", ContentPostVisibility.private => "private", },
      if (request.assistantUsePolicy != null) "assistantUsePolicy": switch (request.assistantUsePolicy!) { ContentPostAssistantUsePolicy.inherit => "inherit", ContentPostAssistantUsePolicy.exclude => "exclude", },
      if (request.sourcePostId != null) "sourcePostId": request.sourcePostId!,
      if (request.sourceType != null) "sourceType": switch (request.sourceType!) { ContentPostSourceType.original => "original", ContentPostSourceType.repost => "repost", ContentPostSourceType.quote => "quote", },
      if (request.deviceInfo != null) "deviceInfo": _encodeGeneratedStructuredValue(request.deviceInfo!),
      if (request.publishLocation != null) "publishLocation": _encodeGeneratedStructuredValue(request.publishLocation!),
      if (request.authorDisplayNameSnapshot != null) "authorDisplayNameSnapshot": request.authorDisplayNameSnapshot!,
      if (request.authorAvatarUrlSnapshot != null) "authorAvatarUrlSnapshot": request.authorAvatarUrlSnapshot!,
      if (request.personaContextVersion != null) "personaContextVersion": request.personaContextVersion!,
    },
  );
}

