import '../operation_request_payload.dart';
import 'post_reader_queries.dart';

enum ContentPostType { image, video, micro, article }

enum ContentPostIdentity { moment, work }

enum ContentPostVisibility { public, private }

enum ContentPostAssistantUsePolicy { inherit, exclude }

enum ContentPostSourceType { original, repost, quote }

String postPublicationIntentIdForLocalDraft(String localDraftId) =>
    'post-publication:${_requiredText(localDraftId, 'localDraftId')}';

/// 本地草稿到已发布 Post 的唯一原子命令。
final class SubmitContentPostPublicationCommand {
  SubmitContentPostPublicationCommand({
    required String publishIntentId,
    required String localDraftId,
    required this.contentType,
    this.contentIdentity,
    this.title,
    this.body,
    this.summary,
    Iterable<ContentPostStructuredObject> semanticMentions = const [],
    Iterable<String> mediaAssetIds = const [],
    Iterable<ContentPostStructuredObject> mediaItems = const [],
    this.articleMarkdown,
    this.markdownDialect,
    this.articleAssetManifest,
    this.articleRenderProfile,
    this.coverStrategy,
    this.coverFrameTimeMs,
    this.illustrationAssetId,
    this.location,
    this.locationName,
    this.primaryHomepageId,
    this.primaryHomepageType,
    this.primaryHomepageSnapshot,
    this.visibility,
    this.assistantUsePolicy,
    this.sourcePostId,
    this.sourceType,
    this.deviceInfo,
    this.publishLocation,
    this.authorDisplayNameSnapshot,
    this.authorAvatarUrlSnapshot,
    this.personaContextVersion,
  }) : publishIntentId = _requiredText(publishIntentId, 'publishIntentId'),
       localDraftId = _requiredText(localDraftId, 'localDraftId'),
       semanticMentions = List<ContentPostStructuredObject>.unmodifiable(
         semanticMentions,
       ),
       mediaAssetIds = List<String>.unmodifiable(
         mediaAssetIds.map((value) => _requiredText(value, 'mediaAssetId')),
       ),
       mediaItems = List<ContentPostStructuredObject>.unmodifiable(mediaItems);

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

final class ContentPostPublicationReceipt {
  const ContentPostPublicationReceipt({
    required this.publishIntentId,
    required this.localDraftId,
    required this.postId,
    required this.state,
    required this.committedVersion,
    required this.acceptedAt,
  });

  final String publishIntentId;
  final String localDraftId;
  final String postId;
  final String state;
  final int committedVersion;
  final DateTime acceptedAt;
}

abstract interface class ContentPostPublicationWriter {
  Future<ContentPostPublicationReceipt> submitPostPublication(
    SubmitContentPostPublicationCommand command,
  );
}

CloudOperationRequestPayload encodeSubmitContentPostPublicationCommand(
  SubmitContentPostPublicationCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'publishIntentId': command.publishIntentId,
    'localDraftId': command.localDraftId,
    'contentType': command.contentType.name,
    if (command.contentIdentity != null)
      'contentIdentity': command.contentIdentity!.name,
    if (_optionalText(command.title) case final value?) 'title': value,
    if (_optionalText(command.body) case final value?) 'body': value,
    if (_optionalText(command.summary) case final value?) 'summary': value,
    if (command.semanticMentions.isNotEmpty)
      'semanticMentions': command.semanticMentions
          .map(_encodeStructuredValue)
          .toList(growable: false),
    if (command.mediaAssetIds.isNotEmpty)
      'mediaAssetIds': command.mediaAssetIds,
    if (command.mediaItems.isNotEmpty)
      'mediaItems': command.mediaItems
          .map(_encodeStructuredValue)
          .toList(growable: false),
    if (_optionalText(command.articleMarkdown) case final value?)
      'articleMarkdown': value,
    if (_optionalText(command.markdownDialect) case final value?)
      'markdownDialect': value,
    if (command.articleAssetManifest != null)
      'articleAssetManifest': _encodeStructuredValue(
        command.articleAssetManifest!,
      ),
    if (command.articleRenderProfile != null)
      'articleRenderProfile': _encodeStructuredValue(
        command.articleRenderProfile!,
      ),
    if (_optionalText(command.coverStrategy) case final value?)
      'coverStrategy': value,
    if (command.coverFrameTimeMs != null)
      'coverFrameTimeMs': command.coverFrameTimeMs,
    if (_optionalText(command.illustrationAssetId) case final value?)
      'illustrationAssetId': value,
    if (command.location != null)
      'location': _encodeStructuredValue(command.location!),
    if (_optionalText(command.locationName) case final value?)
      'locationName': value,
    if (_optionalText(command.primaryHomepageId) case final value?)
      'primaryHomepageId': value,
    if (_optionalText(command.primaryHomepageType) case final value?)
      'primaryHomepageType': value,
    if (command.primaryHomepageSnapshot != null)
      'primaryHomepageSnapshot': _encodeStructuredValue(
        command.primaryHomepageSnapshot!,
      ),
    if (command.visibility != null) 'visibility': command.visibility!.name,
    if (command.assistantUsePolicy != null)
      'assistantUsePolicy': command.assistantUsePolicy!.name,
    if (_optionalText(command.sourcePostId) case final value?)
      'sourcePostId': value,
    if (command.sourceType != null) 'sourceType': command.sourceType!.name,
    if (command.deviceInfo != null)
      'deviceInfo': _encodeStructuredValue(command.deviceInfo!),
    if (command.publishLocation != null)
      'publishLocation': _encodeStructuredValue(command.publishLocation!),
    if (_optionalText(command.authorDisplayNameSnapshot) case final value?)
      'authorDisplayNameSnapshot': value,
    if (_optionalText(command.authorAvatarUrlSnapshot) case final value?)
      'authorAvatarUrlSnapshot': value,
    if (command.personaContextVersion != null)
      'personaContextVersion': command.personaContextVersion,
  },
);

SubmitContentPostPublicationCommand decodeSubmitContentPostPublicationCommand(
  Object? encodedBody,
) {
  if (encodedBody is! Map) {
    throw const FormatException('Post publication command must be an object');
  }
  final map = encodedBody.map((key, value) => MapEntry(key.toString(), value));
  return SubmitContentPostPublicationCommand(
    publishIntentId: _requiredMapText(map, 'publishIntentId'),
    localDraftId: _requiredMapText(map, 'localDraftId'),
    contentType: _requiredEnum(
      ContentPostType.values,
      map['contentType'],
      'contentType',
    ),
    contentIdentity: _optionalEnum(
      ContentPostIdentity.values,
      map['contentIdentity'],
      'contentIdentity',
    ),
    title: _optionalMapText(map['title'], 'title'),
    body: _optionalMapText(map['body'], 'body'),
    summary: _optionalMapText(map['summary'], 'summary'),
    semanticMentions: _structuredObjectList(
      map['semanticMentions'],
      'semanticMentions',
    ),
    mediaAssetIds: _stringList(map['mediaAssetIds'], 'mediaAssetIds'),
    mediaItems: _structuredObjectList(map['mediaItems'], 'mediaItems'),
    articleMarkdown: _optionalMapText(
      map['articleMarkdown'],
      'articleMarkdown',
    ),
    markdownDialect: _optionalMapText(
      map['markdownDialect'],
      'markdownDialect',
    ),
    articleAssetManifest: _structuredObjectOrNull(
      map['articleAssetManifest'],
      'articleAssetManifest',
    ),
    articleRenderProfile: _structuredObjectOrNull(
      map['articleRenderProfile'],
      'articleRenderProfile',
    ),
    coverStrategy: _optionalMapText(map['coverStrategy'], 'coverStrategy'),
    coverFrameTimeMs: _optionalInt(map['coverFrameTimeMs'], 'coverFrameTimeMs'),
    illustrationAssetId: _optionalMapText(
      map['illustrationAssetId'],
      'illustrationAssetId',
    ),
    location: _structuredObjectOrNull(map['location'], 'location'),
    locationName: _optionalMapText(map['locationName'], 'locationName'),
    primaryHomepageId: _optionalMapText(
      map['primaryHomepageId'],
      'primaryHomepageId',
    ),
    primaryHomepageType: _optionalMapText(
      map['primaryHomepageType'],
      'primaryHomepageType',
    ),
    primaryHomepageSnapshot: _structuredObjectOrNull(
      map['primaryHomepageSnapshot'],
      'primaryHomepageSnapshot',
    ),
    visibility: _optionalEnum(
      ContentPostVisibility.values,
      map['visibility'],
      'visibility',
    ),
    assistantUsePolicy: _optionalEnum(
      ContentPostAssistantUsePolicy.values,
      map['assistantUsePolicy'],
      'assistantUsePolicy',
    ),
    sourcePostId: _optionalMapText(map['sourcePostId'], 'sourcePostId'),
    sourceType: _optionalEnum(
      ContentPostSourceType.values,
      map['sourceType'],
      'sourceType',
    ),
    deviceInfo: _structuredObjectOrNull(map['deviceInfo'], 'deviceInfo'),
    publishLocation: _structuredObjectOrNull(
      map['publishLocation'],
      'publishLocation',
    ),
    authorDisplayNameSnapshot: _optionalMapText(
      map['authorDisplayNameSnapshot'],
      'authorDisplayNameSnapshot',
    ),
    authorAvatarUrlSnapshot: _optionalMapText(
      map['authorAvatarUrlSnapshot'],
      'authorAvatarUrlSnapshot',
    ),
    personaContextVersion: _optionalInt(
      map['personaContextVersion'],
      'personaContextVersion',
    ),
  );
}

ContentPostPublicationReceipt decodeContentPostPublicationReceipt(
  Object? response,
) {
  if (response is! Map) {
    throw const FormatException(
      'ContentPostPublicationReceipt must be an object',
    );
  }
  final map = response.map((key, value) => MapEntry(key.toString(), value));
  final committedVersion = map['committedVersion'];
  if (committedVersion is! num || committedVersion.toInt() < 1) {
    throw const FormatException('committedVersion must be a positive integer');
  }
  final acceptedAt = DateTime.tryParse(_requiredMapText(map, 'acceptedAt'));
  if (acceptedAt == null) {
    throw const FormatException('acceptedAt must be RFC3339');
  }
  return ContentPostPublicationReceipt(
    publishIntentId: _requiredMapText(map, 'publishIntentId'),
    localDraftId: _requiredMapText(map, 'localDraftId'),
    postId: _requiredMapText(map, 'postId'),
    state: _requiredMapText(map, 'state'),
    committedVersion: committedVersion.toInt(),
    acceptedAt: acceptedAt.toUtc(),
  );
}

Object? _encodeStructuredValue(ContentPostStructuredValue value) =>
    switch (value) {
      ContentPostStructuredObject(:final fields) => <String, Object?>{
        for (final entry in fields.entries)
          entry.key: _encodeStructuredValue(entry.value),
      },
      ContentPostStructuredArray(:final values) =>
        values.map(_encodeStructuredValue).toList(growable: false),
      ContentPostStructuredText(:final value) => value,
      ContentPostStructuredNumber(:final value) => value,
      ContentPostStructuredBoolean(:final value) => value,
      ContentPostStructuredNull() => null,
    };

String _requiredText(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(value, name, 'must not be empty');
  }
  return normalized;
}

String _requiredMapText(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key must be a non-empty string');
  }
  return value.trim();
}

String? _optionalText(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}

T _requiredEnum<T extends Enum>(List<T> values, Object? raw, String name) {
  final parsed = _optionalEnum(values, raw, name);
  if (parsed == null) {
    throw FormatException('$name is required');
  }
  return parsed;
}

T? _optionalEnum<T extends Enum>(List<T> values, Object? raw, String name) {
  final normalized = _optionalMapText(raw, name);
  if (normalized == null) {
    return null;
  }
  for (final value in values) {
    if (value.name == normalized) {
      return value;
    }
  }
  throw FormatException('$name has an unsupported value');
}

String? _optionalMapText(Object? raw, String name) {
  if (raw == null) {
    return null;
  }
  if (raw is! String) {
    throw FormatException('$name must be a string');
  }
  final normalized = raw.trim();
  return normalized.isEmpty ? null : normalized;
}

int? _optionalInt(Object? raw, String name) {
  if (raw == null) {
    return null;
  }
  if (raw is num) {
    return raw.toInt();
  }
  throw FormatException('$name must be an integer');
}

List<String> _stringList(Object? raw, String name) {
  if (raw == null) {
    return const <String>[];
  }
  if (raw is! List) {
    throw FormatException('$name must be a list');
  }
  return raw
      .map((value) {
        if (value is! String || value.trim().isEmpty) {
          throw FormatException('$name values must be non-empty strings');
        }
        return value.trim();
      })
      .toList(growable: false);
}

List<ContentPostStructuredObject> _structuredObjectList(
  Object? raw,
  String name,
) {
  if (raw == null) {
    return const <ContentPostStructuredObject>[];
  }
  if (raw is! List) {
    throw FormatException('$name must be a list');
  }
  return raw
      .map((value) => _structuredObject(value, name))
      .toList(growable: false);
}

ContentPostStructuredObject? _structuredObjectOrNull(
  Object? raw,
  String name,
) => raw == null ? null : _structuredObject(raw, name);

ContentPostStructuredObject _structuredObject(Object? raw, String name) {
  if (raw is! Map) {
    throw FormatException('$name must be an object');
  }
  return ContentPostStructuredObject(<String, ContentPostStructuredValue>{
    for (final entry in raw.entries)
      if (entry.key is String)
        entry.key as String: _structuredValue(entry.value, name),
  });
}

ContentPostStructuredValue _structuredValue(Object? raw, String name) {
  if (raw == null) return const ContentPostStructuredNull();
  if (raw is String) return ContentPostStructuredText(raw);
  if (raw is num) return ContentPostStructuredNumber(raw);
  if (raw is bool) return ContentPostStructuredBoolean(raw);
  if (raw is List) {
    return ContentPostStructuredArray(
      raw.map((value) => _structuredValue(value, name)),
    );
  }
  if (raw is Map) {
    return _structuredObject(raw, name);
  }
  throw FormatException('$name contains unsupported data');
}
