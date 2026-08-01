import '../operation_request_payload.dart';
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
  final map = _publicationObject(
    encodedBody,
    'Post publication command',
    const <String>{
      'publishIntentId',
      'localDraftId',
      'contentType',
      'contentIdentity',
      'title',
      'body',
      'summary',
      'semanticMentions',
      'mediaAssetIds',
      'articleMarkdown',
      'markdownDialect',
      'articleAssetManifest',
      'articleRenderProfile',
      'coverStrategy',
      'coverFrameTimeMs',
      'illustrationAssetId',
      'location',
      'locationName',
      'geoTagRef',
      'visitedAt',
      'primaryHomepageId',
      'primaryHomepageType',
      'primaryHomepageSnapshot',
      'visibility',
      'assistantUsePolicy',
      'sourcePostId',
      'sourceType',
      'deviceInfo',
      'publishLocation',
      'authorDisplayNameSnapshot',
      'authorAvatarUrlSnapshot',
      'personaContextVersion',
    },
  );
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
    semanticMentions: decodePostSemanticMentionList(map['semanticMentions']),
    mediaAssetIds: _stringList(map['mediaAssetIds'], 'mediaAssetIds'),
    articleMarkdown: _optionalMapText(
      map['articleMarkdown'],
      'articleMarkdown',
    ),
    markdownDialect: _optionalMapText(
      map['markdownDialect'],
      'markdownDialect',
    ),
    articleAssetManifest: decodeOptionalPostArticleAssetManifestInput(
      map['articleAssetManifest'],
    ),
    articleRenderProfile: decodeOptionalPostArticleRenderProfile(
      map['articleRenderProfile'],
    ),
    coverStrategy: _optionalMapText(map['coverStrategy'], 'coverStrategy'),
    coverFrameTimeMs: _optionalInt(map['coverFrameTimeMs'], 'coverFrameTimeMs'),
    illustrationAssetId: _optionalMapText(
      map['illustrationAssetId'],
      'illustrationAssetId',
    ),
    location: decodeOptionalGeoPoint(map['location']),
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
    primaryHomepageSnapshot: decodeOptionalPostHomepageSnapshot(
      map['primaryHomepageSnapshot'],
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
    deviceInfo: decodeOptionalPostDeviceInfo(map['deviceInfo']),
    publishLocation: decodeOptionalPostPublishLocation(map['publishLocation']),
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

List<PostSemanticMention> decodePostSemanticMentionList(Object? encoded) {
  if (encoded == null) return const <PostSemanticMention>[];
  if (encoded is Iterable<PostSemanticMention>) {
    return List<PostSemanticMention>.unmodifiable(encoded);
  }
  if (encoded is! List) {
    throw const FormatException('semanticMentions must be a list');
  }
  return List<PostSemanticMention>.unmodifiable(
    encoded.indexed.map((entry) {
      final map = _publicationObject(
        entry.$2,
        'semanticMentions[${entry.$1}]',
        const <String>{
          'mentionId',
          'kind',
          'surface',
          'location',
          'rangeStart',
          'rangeEnd',
          'status',
          'candidateId',
          'targetRef',
        },
      );
      return PostSemanticMention(
        mentionId: _requiredMapText(map, 'mentionId'),
        kind: _requiredMapText(map, 'kind'),
        surface: _requiredMapText(map, 'surface'),
        location: _requiredMapText(map, 'location'),
        rangeStart: _optionalInt(map['rangeStart'], 'rangeStart'),
        rangeEnd: _optionalInt(map['rangeEnd'], 'rangeEnd'),
        status: _requiredMapText(map, 'status'),
        candidateId: _optionalMapText(map['candidateId'], 'candidateId'),
        targetRef: _optionalMapText(map['targetRef'], 'targetRef'),
      );
    }),
  );
}

PostArticleAssetManifestInput? decodeOptionalPostArticleAssetManifestInput(
  Object? encoded,
) {
  if (encoded == null) return null;
  if (encoded is PostArticleAssetManifestInput) return encoded;
  final map = _publicationObject(
    encoded,
    'articleAssetManifest',
    const <String>{'schema', 'markdownVersion', 'assets'},
  );
  final encodedAssets = map['assets'];
  if (encodedAssets is! List) {
    throw const FormatException('articleAssetManifest.assets must be a list');
  }
  final assets = encodedAssets.indexed
      .map((entry) {
        if (entry.$2 is PostArticleAssetInput) {
          return entry.$2 as PostArticleAssetInput;
        }
        final asset = _publicationObject(
          entry.$2,
          'articleAssetManifest.assets[${entry.$1}]',
          const <String>{'assetId', 'role', 'layout', 'caption'},
        );
        return PostArticleAssetInput(
          assetId: _requiredMapText(asset, 'assetId'),
          role: _optionalMapText(asset['role'], 'role'),
          layout: _optionalMapText(asset['layout'], 'layout'),
          caption: _optionalMapText(asset['caption'], 'caption'),
        );
      })
      .toList(growable: false);
  return PostArticleAssetManifestInput(
    schema: _requiredMapText(map, 'schema'),
    markdownVersion: _optionalMapText(
      map['markdownVersion'],
      'markdownVersion',
    ),
    assets: assets,
  );
}

PostArticleRenderProfile? decodeOptionalPostArticleRenderProfile(
  Object? encoded,
) {
  if (encoded == null) return null;
  if (encoded is PostArticleRenderProfile) return encoded;
  final map =
      _publicationObject(encoded, 'articleRenderProfile', const <String>{
        'template',
        'fontPreset',
        'paperThemeMode',
        'paperTexture',
        'contentVertical',
        'layoutPolicy',
        'width',
        'height',
        'durationMs',
      });
  return PostArticleRenderProfile(
    template: _optionalMapText(map['template'], 'template'),
    fontPreset: _optionalMapText(map['fontPreset'], 'fontPreset'),
    paperThemeMode: _optionalMapText(map['paperThemeMode'], 'paperThemeMode'),
    paperTexture: _optionalMapText(map['paperTexture'], 'paperTexture'),
    contentVertical: _optionalMapText(
      map['contentVertical'],
      'contentVertical',
    ),
    layoutPolicy: _decodeOptionalPostArticleLayoutPolicy(map['layoutPolicy']),
    width: _optionalInt(map['width'], 'width'),
    height: _optionalInt(map['height'], 'height'),
    durationMs: _optionalInt(map['durationMs'], 'durationMs'),
  );
}

PostArticleLayoutPolicy? _decodeOptionalPostArticleLayoutPolicy(
  Object? encoded,
) {
  if (encoded == null) return null;
  if (encoded is PostArticleLayoutPolicy) return encoded;
  final map = _publicationObject(
    encoded,
    'articleRenderProfile.layoutPolicy',
    const <String>{'wrapDowngrade', 'galleryDowngrade'},
  );
  return PostArticleLayoutPolicy(
    wrapDowngrade: _optionalMapText(map['wrapDowngrade'], 'wrapDowngrade'),
    galleryDowngrade: _optionalMapText(
      map['galleryDowngrade'],
      'galleryDowngrade',
    ),
  );
}

GeoPoint? decodeOptionalGeoPoint(Object? encoded) {
  if (encoded == null) return null;
  if (encoded is GeoPoint) return encoded;
  final map = _publicationObject(encoded, 'location', const <String>{
    'latitude',
    'longitude',
  });
  return GeoPoint(
    latitude: _requiredDouble(map['latitude'], 'latitude'),
    longitude: _requiredDouble(map['longitude'], 'longitude'),
  );
}

PostHomepageSnapshot? decodeOptionalPostHomepageSnapshot(Object? encoded) {
  if (encoded == null) return null;
  if (encoded is PostHomepageSnapshot) return encoded;
  final map = _publicationObject(
    encoded,
    'primaryHomepageSnapshot',
    const <String>{
      'canonicalEntityId',
      'title',
      'subtitle',
      'coverUrl',
      'width',
      'height',
      'durationMs',
    },
  );
  return PostHomepageSnapshot(
    canonicalEntityId: _optionalMapText(
      map['canonicalEntityId'],
      'canonicalEntityId',
    ),
    title: _optionalMapText(map['title'], 'title'),
    subtitle: _optionalMapText(map['subtitle'], 'subtitle'),
    coverUrl: _optionalMapText(map['coverUrl'], 'coverUrl'),
    width: _optionalInt(map['width'], 'width'),
    height: _optionalInt(map['height'], 'height'),
    durationMs: _optionalInt(map['durationMs'], 'durationMs'),
  );
}

PostDeviceInfo? decodeOptionalPostDeviceInfo(Object? encoded) {
  if (encoded == null) return null;
  if (encoded is PostDeviceInfo) return encoded;
  final map = _publicationObject(encoded, 'deviceInfo', const <String>{
    'manufacturer',
    'brand',
    'model',
    'os',
    'appVersion',
    'width',
    'height',
    'durationMs',
  });
  return PostDeviceInfo(
    manufacturer: _optionalMapText(map['manufacturer'], 'manufacturer'),
    brand: _optionalMapText(map['brand'], 'brand'),
    model: _optionalMapText(map['model'], 'model'),
    os: _optionalMapText(map['os'], 'os'),
    appVersion: _optionalMapText(map['appVersion'], 'appVersion'),
    width: _optionalInt(map['width'], 'width'),
    height: _optionalInt(map['height'], 'height'),
    durationMs: _optionalInt(map['durationMs'], 'durationMs'),
  );
}

PostPublishLocation? decodeOptionalPostPublishLocation(Object? encoded) {
  if (encoded == null) return null;
  if (encoded is PostPublishLocation) return encoded;
  final map = _publicationObject(encoded, 'publishLocation', const <String>{
    'country',
    'province',
    'city',
  });
  return PostPublishLocation(
    country: _optionalMapText(map['country'], 'country'),
    province: _optionalMapText(map['province'], 'province'),
    city: _optionalMapText(map['city'], 'city'),
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
  if (raw is int) return raw;
  if (raw is double && raw.isFinite && raw == raw.truncateToDouble()) {
    return raw.toInt();
  }
  throw FormatException('$name must be an integer');
}

double _requiredDouble(Object? raw, String name) {
  if (raw is num && raw.isFinite) return raw.toDouble();
  throw FormatException('$name must be a finite number');
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

Map<String, Object?> _publicationObject(
  Object? raw,
  String name,
  Set<String> allowedFields,
) {
  if (raw is! Map) {
    throw FormatException('$name must be an object');
  }
  final map = <String, Object?>{};
  for (final entry in raw.entries) {
    if (entry.key is! String) {
      throw FormatException('$name keys must be strings');
    }
    final key = entry.key as String;
    if (!allowedFields.contains(key)) {
      throw FormatException('$name contains unknown field $key');
    }
    map[key] = entry.value;
  }
  return map;
}
