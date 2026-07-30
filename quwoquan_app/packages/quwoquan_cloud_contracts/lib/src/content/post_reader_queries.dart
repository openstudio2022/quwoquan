import '../canonical_sha256_digest.dart';
import '../operation_request_payload.dart';
import '../generated/content_post_get_feed_policy.g.dart';
import 'post_reader_models.dart';

export 'post_reader_models.dart';
part '../generated/requests/content/post_reader_queries.requests.g.dart';

/// Generated operation-owned hard page boundary for the homepage feed.
const int contentDiscoveryFeedMaxPageItems =
    GeneratedContentPostGetFeedPolicy.maximumItems;

ContentPostDetailSlice decodeContentPostDetailSlice(Object? response) {
  final root = _expectObject(response, 'Content post detail response');
  return ContentPostDetailSlice(
    post: _decodeContentPostProjection(root),
    mediaItems: _decodeMediaItems(root['mediaItems']),
    isOfficial: _optionalBool(root['isOfficial']),
    badge: _optionalText(root['badge']),
    articleTemplate: _optionalText(root['articleTemplate']),
    articleFontPreset: _optionalText(root['articleFontPreset']),
    articleMarkdown: _optionalText(root['articleMarkdown']),
    markdownDialect: _optionalText(root['markdownDialect']),
    articleMarkdownDigest: _optionalText(root['articleMarkdownDigest']),
    articleAssetManifest: _optionalStructuredObject(
      root['articleAssetManifest'],
      'articleAssetManifest',
    ),
    articleRenderProfile: _optionalStructuredObject(
      root['articleRenderProfile'],
      'articleRenderProfile',
    ),
    contentVertical: _optionalText(root['contentVertical']),
    paperThemeMode: _optionalText(root['paperThemeMode']),
    paperTexture: _optionalText(root['paperTexture']),
    entityMentions: _decodeEntityMentions(root['entityMentions']),
    coverUrl: _optionalText(root['coverUrl']),
    tagRefs: _optionalStringList(root['tagRefs'], 'tagRefs'),
    status: _requiredText(root['status'], 'status'),
    moderationStatus: _optionalText(root['moderationStatus']),
    visibility: _optionalText(root['visibility']),
  );
}

List<ContentPostMediaItem> _decodeMediaItems(Object? raw) {
  if (raw == null) return const <ContentPostMediaItem>[];
  return _expectList(raw, 'mediaItems')
      .map((item) {
        final value = _expectObject(item, 'mediaItems item');
        return ContentPostMediaItem(
          kind: _requiredText(value['kind'], 'mediaItems.kind'),
          url: _requiredText(value['url'], 'mediaItems.url'),
          mediaAssetId: _optionalText(value['mediaAssetId']),
          mediaAssetVersion: _optionalInt(value['mediaAssetVersion']),
          hlsCmafMasterManifestUrl: _optionalText(
            value['hlsCmafMasterManifestUrl'],
          ),
          hlsCmafDescriptorVersion: _optionalInt(
            value['hlsCmafDescriptorVersion'],
          ),
          coverUrl: _optionalText(value['coverUrl']),
          durationMs: _optionalInt(value['durationMs']),
          width: _optionalInt(value['width']),
          height: _optionalInt(value['height']),
          title: _optionalText(value['title']),
        );
      })
      .toList(growable: false);
}

ContentAuthorPostPageSlice decodeContentAuthorPostPageSlice(Object? response) {
  final root = _expectObject(response, 'Content author posts response');
  final items = _expectList(
    root['items'],
    'Content author posts response.items',
  );
  return ContentAuthorPostPageSlice(
    items: items.map(
      (item) => _decodeContentPostProjection(
        _expectObject(item, 'Content author posts item'),
      ),
    ),
    nextCursor: _optionalText(root['nextCursor']),
    totalCount: _optionalInt(root['totalCount']),
  );
}

ContentDiscoveryFeedPageSlice decodeContentDiscoveryFeedPageSlice(
  Object? response,
) {
  final root = _expectObject(response, 'Content discovery feed response');
  final items = _expectList(root['items'], 'Content discovery feed items');
  if (items.length > contentDiscoveryFeedMaxPageItems) {
    throw const FormatException(
      'Content discovery feed items exceed the App page limit',
    );
  }
  final rawCards = root['objectCards'];
  final cardValues = rawCards == null
      ? const <Object?>[]
      : _expectList(rawCards, 'Content discovery feed objectCards');
  if (cardValues.length > items.length) {
    throw const FormatException(
      'Content discovery feed objectCards exceed the item-derived limit',
    );
  }
  final cards = cardValues
      .map((item) => _decodeContentFeedObjectCard(item, items.length))
      .toList(growable: false);
  final nextCursor = _optionalText(root['nextCursor']);
  final previousCursor = _optionalText(root['previousCursor']);
  final paginationExpiresAt = _optionalDateTime(root['paginationExpiresAt']);
  final hasCursor =
      (nextCursor?.isNotEmpty ?? false) ||
      (previousCursor?.isNotEmpty ?? false);
  if (hasCursor != (paginationExpiresAt != null)) {
    throw const FormatException(
      'Content discovery feed cursors and paginationExpiresAt must be paired',
    );
  }
  final outcome = switch (root['outcome']) {
    'content' => ContentDiscoveryFeedOutcome.content,
    'empty' => ContentDiscoveryFeedOutcome.empty,
    _ => throw const FormatException(
      'Content discovery feed outcome is invalid',
    ),
  };
  final emptyReason = switch (root['emptyReason']) {
    null => null,
    'no_active_release' => ContentDiscoveryFeedEmptyReason.noActiveRelease,
    'no_eligible_content' => ContentDiscoveryFeedEmptyReason.noEligibleContent,
    'following_empty' => ContentDiscoveryFeedEmptyReason.followingEmpty,
    'continuation_end' => ContentDiscoveryFeedEmptyReason.continuationEnd,
    _ => throw const FormatException(
      'Content discovery feed emptyReason is invalid',
    ),
  };
  if (items.isEmpty) {
    if (outcome != ContentDiscoveryFeedOutcome.empty || emptyReason == null) {
      throw const FormatException(
        'Empty content discovery feed requires canonical empty outcome',
      );
    }
  } else if (outcome != ContentDiscoveryFeedOutcome.content ||
      emptyReason != null) {
    throw const FormatException(
      'Non-empty content discovery feed requires content outcome',
    );
  }
  return ContentDiscoveryFeedPageSlice(
    items: items.map(
      (item) => _decodeContentPostProjection(
        _expectObject(item, 'Content discovery feed item'),
      ),
    ),
    outcome: outcome,
    emptyReason: emptyReason,
    objectCards: cards,
    nextCursor: nextCursor,
    previousCursor: previousCursor,
    paginationExpiresAt: paginationExpiresAt,
    feedRequestId: _optionalText(root['feedRequestId']),
    policyDigest: _optionalPolicyDigest(root['policyDigest']),
    hasMore: _optionalBool(root['hasMore']),
  );
}

const Set<String> _contentFeedObjectCardFields = <String>{
  'objectKind',
  'objectId',
  'title',
  'subtitle',
  'coverUrl',
  'tagRefs',
  'reasonText',
  'recallPath',
  'anchorIndex',
};

/// Decodes the fixed, flat FeedObjectCard projection without entering the
/// generic recursive structured-value decoder.
///
/// The canonical projection currently declares no per-field byte or tag-count
/// budget, so this validator does not invent one. Aggregate bytes are bounded
/// only when the canonical Cloud live-response policy is injected; unknown
/// fields and nested values still fail closed before a recursive typed object
/// graph can be materialized.
ContentPostStructuredObject _decodeContentFeedObjectCard(
  Object? raw,
  int itemCount,
) {
  final object = _expectObject(raw, 'Content discovery feed objectCards item');
  final fields = <String, ContentPostStructuredValue>{};
  for (final entry in object.entries) {
    final key = entry.key;
    if (key is! String || !_contentFeedObjectCardFields.contains(key)) {
      throw const FormatException(
        'Content discovery feed objectCards contain an unknown field',
      );
    }
    final value = entry.value;
    switch (key) {
      case 'tagRefs':
        final tags = _expectList(value, 'Content discovery feed tagRefs');
        fields[key] = ContentPostStructuredArray(
          tags.map((tag) {
            if (tag is! String) {
              throw const FormatException(
                'Content discovery feed tagRefs must contain strings',
              );
            }
            return ContentPostStructuredText(tag);
          }),
        );
      case 'anchorIndex':
        if (value is! num || !value.isFinite || value.toInt() != value) {
          throw const FormatException(
            'Content discovery feed anchorIndex must be an integer',
          );
        }
        final anchorIndex = value.toInt();
        if (anchorIndex < 0 || anchorIndex > itemCount) {
          throw const FormatException(
            'Content discovery feed anchorIndex is outside the page',
          );
        }
        fields[key] = ContentPostStructuredNumber(anchorIndex);
      default:
        if (value is! String) {
          throw const FormatException(
            'Content discovery feed objectCards text fields must be strings',
          );
        }
        fields[key] = ContentPostStructuredText(value);
    }
  }
  return ContentPostStructuredObject(fields);
}

ContentPostProjection decodeContentPostProjection(Object? response) {
  return _decodeContentPostProjection(
    _expectObject(response, 'Content post projection'),
  );
}

ContentPostProjection _decodeContentPostProjection(Map<Object?, Object?> item) {
  final rawReasons = item['intersectionReasons'];
  return ContentPostProjection(
    postId: _requiredText(item['postId'], 'postId'),
    contentType: _optionalText(item['contentType']) ?? 'image',
    contentIdentity: _optionalText(item['contentIdentity']),
    assistantUsePolicy: _optionalText(item['assistantUsePolicy']) ?? 'inherit',
    authorId: _optionalText(item['authorId']),
    authorDisplayName: _optionalText(item['authorDisplayName']),
    authorAvatarUrl: _optionalText(item['authorAvatarUrl']),
    authorBackgroundUrl: _optionalText(item['authorBackgroundUrl']),
    authorRoleLabel: _optionalText(item['authorRoleLabel']),
    authorIdentityTags:
        _optionalStringList(
          item['authorIdentityTags'],
          'author identity tags',
        ) ??
        const <String>[],
    authorVerified: _optionalBool(item['authorVerified']) ?? false,
    title: _optionalText(item['title']),
    body: _optionalText(item['body']),
    summary: _optionalText(item['summary']),
    coverUrl: _optionalText(item['coverUrl']),
    articleTemplate: _optionalText(item['articleTemplate']),
    articleFontPreset: _optionalText(item['articleFontPreset']),
    mediaUrls:
        _optionalStringList(item['mediaUrls'], 'content post media URLs') ??
        const <String>[],
    videoUrl: _optionalText(item['videoUrl']),
    mediaAssetId: _optionalText(item['mediaAssetId']),
    mediaAssetVersion: _optionalInt(item['mediaAssetVersion']),
    hlsCmafMasterManifestUrl: _optionalText(item['hlsCmafMasterManifestUrl']),
    hlsCmafDescriptorVersion: _optionalInt(item['hlsCmafDescriptorVersion']),
    thumbnailUrl: _optionalText(item['thumbnailUrl']),
    width: _optionalInt(item['width']),
    height: _optionalInt(item['height']),
    durationMs: _optionalInt(item['durationMs']),
    likeCount: _optionalInt(item['likeCount']) ?? 0,
    commentCount: _optionalInt(item['commentCount']) ?? 0,
    shareCount: _optionalInt(item['shareCount']) ?? 0,
    createdAt: _optionalDateTime(item['createdAt']),
    updatedAt: _optionalDateTime(item['updatedAt']),
    publishedAt: _optionalDateTime(item['publishedAt']),
    contentVertical: _optionalText(item['contentVertical']),
    recallPath: _optionalText(item['recallPath']),
    supplySource: _optionalText(item['supplySource']),
    intersectionReasons: rawReasons == null
        ? null
        : _decodeIntersectionReasons(rawReasons),
  );
}

List<ContentPostIntersectionReason> _decodeIntersectionReasons(Object? raw) {
  return _expectList(raw, 'intersectionReasons')
      .map((item) {
        final reason = _expectObject(item, 'intersection reason');
        return ContentPostIntersectionReason(
          kind: _optionalText(reason['kind']) ?? '',
          primaryText: _optionalText(reason['primaryText']) ?? '',
          secondaryText: _optionalText(reason['secondaryText']) ?? '',
          strength:
              _optionalDouble(reason['strength']) ??
              _optionalDouble(reason['strengthScore']) ??
              0,
        );
      })
      .toList(growable: false);
}

List<ContentPostEntityMention> _decodeEntityMentions(Object? raw) {
  if (raw == null) return const <ContentPostEntityMention>[];
  return _expectList(raw, 'entityMentions')
      .map((item) {
        final mention = _expectObject(item, 'entity mention');
        return ContentPostEntityMention(
          subjectType: _optionalText(mention['subjectType']) ?? '',
          subjectId: _optionalText(mention['subjectId']) ?? '',
          displayName: _optionalText(mention['displayName']) ?? '',
          rangeStart: _optionalInt(mention['rangeStart']) ?? 0,
          rangeEnd: _optionalInt(mention['rangeEnd']) ?? 0,
        );
      })
      .toList(growable: false);
}

ContentPostStructuredObject? _optionalStructuredObject(
  Object? raw,
  String context,
) {
  if (raw == null) return null;
  final value = _decodeStructuredValue(raw, context);
  if (value is! ContentPostStructuredObject) {
    throw FormatException('$context must be an object');
  }
  return value;
}

ContentPostStructuredValue _decodeStructuredValue(Object? raw, String context) {
  if (raw == null) return const ContentPostStructuredNull();
  if (raw is String) return ContentPostStructuredText(raw);
  if (raw is num) return ContentPostStructuredNumber(raw);
  if (raw is bool) return ContentPostStructuredBoolean(raw);
  if (raw is List) {
    return ContentPostStructuredArray(
      raw.map((value) => _decodeStructuredValue(value, context)),
    );
  }
  if (raw is Map) {
    final fields = <String, ContentPostStructuredValue>{};
    for (final entry in raw.entries) {
      if (entry.key is! String) {
        throw FormatException('$context keys must be strings');
      }
      fields[entry.key as String] = _decodeStructuredValue(
        entry.value,
        context,
      );
    }
    return ContentPostStructuredObject(fields);
  }
  throw FormatException('$context contains unsupported JSON data');
}

Map<Object?, Object?> _expectObject(Object? value, String context) {
  if (value is Map<Object?, Object?>) {
    return value;
  }
  throw FormatException('$context must be an object');
}

List<Object?> _expectList(Object? value, String context) {
  if (value is List<Object?>) {
    return value;
  }
  throw FormatException('$context must be a list');
}

String _requiredText(Object? value, String name) {
  final text = _optionalText(value);
  if (text == null) {
    throw FormatException('$name must be a non-empty string');
  }
  return text;
}

String? _optionalText(Object? value) {
  if (value == null) return null;
  if (value is! String) {
    throw FormatException('Expected a string value');
  }
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}

String? _optionalPolicyDigest(Object? value) {
  if (value == null) {
    return null;
  }
  if (value is! String || !isCanonicalSha256Digest(value)) {
    throw const FormatException(
      'policyDigest must be a canonical SHA-256 digest',
    );
  }
  return value;
}

bool? _optionalBool(Object? value) {
  if (value == null) return null;
  if (value is bool) return value;
  throw FormatException('Expected a boolean value');
}

int? _optionalInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value.trim());
  throw FormatException('Expected an integer value');
}

double? _optionalDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  if (value is String) return double.tryParse(value.trim());
  throw FormatException('Expected a numeric value');
}

DateTime? _optionalDateTime(Object? value) {
  if (value == null) return null;
  if (value is! String) {
    throw FormatException('Expected an ISO-8601 timestamp');
  }
  final normalized = value.trim();
  if (normalized.isEmpty) return null;
  final parsed = DateTime.tryParse(normalized);
  if (parsed == null) {
    throw FormatException('Expected an ISO-8601 timestamp');
  }
  return parsed;
}

List<String>? _optionalStringList(Object? value, String context) {
  if (value == null) return null;
  return List<String>.unmodifiable(
    _expectList(value, context)
        .map((item) {
          if (item is! String) {
            throw FormatException('$context must contain strings');
          }
          return item.trim();
        })
        .where((item) => item.isNotEmpty),
  );
}
