import '../operation_request_payload.dart';
import 'post_reader_queries.dart';
part '../generated/requests/content/post_publication_contracts.requests.g.dart';

enum ContentPostType { image, video, micro, article }

enum ContentPostIdentity { moment, work }

enum ContentPostVisibility { public, private }

enum ContentPostAssistantUsePolicy { inherit, exclude }

enum ContentPostSourceType { original, repost, quote }

String postPublicationIntentIdForLocalDraft(String localDraftId) =>
    'post-publication:${_requiredText(localDraftId, 'localDraftId')}';

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
    geoTagRef: _optionalMapText(map['geoTagRef'], 'geoTagRef'),
    visitedAt: _optionalTimestamp(map['visitedAt'], 'visitedAt'),
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

DateTime? _optionalTimestamp(Object? raw, String name) {
  final normalized = _optionalMapText(raw, name);
  if (normalized == null) {
    return null;
  }
  final parsed = DateTime.tryParse(normalized);
  if (parsed == null) {
    throw FormatException('$name must be RFC3339');
  }
  return parsed.toUtc();
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
