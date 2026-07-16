import '../operation_request_payload.dart';
import 'post_reader_models.dart';

export 'post_reader_models.dart';

/// 单篇内容详情查询参数。
final class ContentPostDetailQuery {
  const ContentPostDetailQuery({required this.postId});

  final String postId;
}

/// 指定主体发布内容的分页查询参数。
final class ContentAuthorPostsQuery {
  const ContentAuthorPostsQuery({
    required this.subAccountId,
    this.identity,
    this.type,
    this.visibility,
    this.cursor,
    this.limit = 20,
  });

  final String subAccountId;
  final String? identity;
  final String? type;
  final String? visibility;
  final String? cursor;
  final int limit;
}

CloudOperationRequestPayload encodeContentPostDetailQuery(
  ContentPostDetailQuery query,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      'postId': _requiredText(query.postId, 'postId'),
    },
  );
}

CloudOperationRequestPayload encodeContentAuthorPostsQuery(
  ContentAuthorPostsQuery query,
) {
  _validatePageLimit(query.limit);
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      'subAccountId': _requiredText(query.subAccountId, 'subAccountId'),
    },
    queryParameters: <String, String>{
      if (_optionalText(query.identity) case final identity?)
        'identity': identity,
      if (_optionalText(query.type) case final type?) 'type': type,
      if (_optionalText(query.visibility) case final visibility?)
        'visibility': visibility,
      if (_optionalText(query.cursor) case final cursor?) 'cursor': cursor,
      'limit': '${query.limit}',
    },
  );
}

ContentPostDetailSlice decodeContentPostDetailSlice(Object? response) {
  final root = _expectObject(response, 'Content post detail response');
  final nestedPost = root['post'];
  final post = nestedPost is Map
      ? _decodeContentPostProjection(
          _expectObject(nestedPost, 'Content post detail response.post'),
        )
      : _decodeContentPostProjection(root);
  return ContentPostDetailSlice(
    post: post,
    isOfficial: _optionalBool(root['isOfficial']),
    badge: _optionalText(root['badge']),
    articleTemplate: _optionalText(root['articleTemplate']),
    articleFontPreset: _optionalText(root['articleFontPreset']),
    articleMarkdown: _optionalText(root['articleMarkdown']),
    articleMarkdownVersion: _optionalText(root['articleMarkdownVersion']),
    articleMarkdownDigest: _optionalText(root['articleMarkdownDigest']),
    articleAssetManifest: _optionalStructuredObject(
      root['articleAssetManifest'],
      'articleAssetManifest',
    ),
    articleRenderProfile: _optionalStructuredObject(
      root['articleRenderProfile'],
      'articleRenderProfile',
    ),
    contentVertical: _optionalAliasText(root, const <String>[
      'contentVertical',
      'categoryId',
      'category',
      'vertical',
    ]),
    paperThemeMode: _optionalText(root['paperThemeMode']),
    paperTexture: _optionalAliasText(root, const <String>[
      'paperTexture',
      'articlePaperTexture',
    ]),
    entityMentions: _decodeEntityMentions(root['entityMentions']),
    coverUrl: _optionalText(root['coverUrl']),
    tagRefs: _optionalStringList(root['tagRefs'], 'tagRefs'),
    visibility: _optionalText(root['visibility']),
  );
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
    nextCursor: _optionalText(root['nextCursor'] ?? root['cursor']),
    totalCount: _optionalInt(root['totalCount']),
  );
}

ContentPostProjection _decodeContentPostProjection(Map<Object?, Object?> item) {
  final rawReasons = item['intersectionReasons'];
  return ContentPostProjection(
    postId: _requiredAliasText(item, const <String>['postId', 'id', '_id']),
    contentType:
        _optionalAliasText(item, const <String>['contentType', 'type']) ??
        'image',
    contentIdentity: _optionalAliasText(item, const <String>[
      'contentIdentity',
      'identity',
    ]),
    assistantUsePolicy: _optionalText(item['assistantUsePolicy']) ?? 'inherit',
    authorId: _optionalAliasText(item, const <String>[
      'authorId',
      'userId',
      'author_id',
    ]),
    authorDisplayName: _optionalAliasText(item, const <String>[
      'authorDisplayName',
      'authorDisplayNameSnapshot',
      'authorNickname',
      'nickname',
      'username',
      'displayName',
    ]),
    authorAvatarUrl: _optionalAliasText(item, const <String>[
      'authorAvatarUrl',
      'authorAvatarUrlSnapshot',
      'avatarUrl',
      'avatar',
    ]),
    authorBackgroundUrl: _optionalText(item['authorBackgroundUrl']),
    authorRoleLabel: _optionalAliasText(item, const <String>[
      'authorRoleLabel',
      'roleLabel',
      'authorRole',
    ]),
    authorIdentityTags:
        _optionalStringList(
          item['authorIdentityTags'] ??
              item['identityTags'] ??
              item['authorTags'],
          'author identity tags',
        ) ??
        const <String>[],
    authorVerified:
        _optionalBool(
          item['authorVerified'] ?? item['verified'] ?? item['isVerified'],
        ) ??
        false,
    title: _optionalText(item['title']),
    body: _optionalAliasText(item, const <String>[
      'body',
      'description',
      'content',
      'caption',
    ]),
    summary: _optionalText(item['summary']),
    coverUrl: _optionalAliasText(item, const <String>[
      'coverUrl',
      'cover',
      'thumbnailUrl',
      'thumbnail',
    ]),
    imageUrls:
        _optionalStringList(
          item['mediaUrls'] ??
              item['images'] ??
              item['imageUrls'] ??
              item['image_urls'],
          'content post image URLs',
        ) ??
        const <String>[],
    videoUrl: _optionalAliasText(item, const <String>['videoUrl', 'video_url']),
    thumbnailUrl: _optionalAliasText(item, const <String>[
      'thumbnailUrl',
      'thumbnail',
      'coverUrl',
      'cover',
    ]),
    width: _optionalInt(
      item['width'] ?? item['imageWidth'] ?? item['image_width'] ?? item['w'],
    ),
    height: _optionalInt(
      item['height'] ??
          item['imageHeight'] ??
          item['image_height'] ??
          item['h'],
    ),
    durationMs: _optionalInt(item['durationMs'] ?? item['duration']),
    likeCount:
        _optionalInt(
          item['likeCount'] ?? item['likesCount'] ?? item['likes'],
        ) ??
        0,
    commentCount:
        _optionalInt(
          item['commentCount'] ?? item['commentsCount'] ?? item['comments'],
        ) ??
        0,
    shareCount:
        _optionalInt(
          item['shareCount'] ?? item['sharesCount'] ?? item['shares'],
        ) ??
        0,
    createdAt: _optionalDateTime(item['createdAt'] ?? item['created_at']),
    updatedAt: _optionalDateTime(item['updatedAt'] ?? item['updated_at']),
    publishedAt: _optionalDateTime(item['publishedAt'] ?? item['published_at']),
    contentVertical: _optionalAliasText(item, const <String>[
      'contentVertical',
      'categoryId',
      'category',
      'vertical',
    ]),
    recallPath: _optionalAliasText(item, const <String>[
      'recallPath',
      'recall_path',
    ]),
    supplySource: _optionalAliasText(item, const <String>[
      'supplySource',
      'supply_source',
    ]),
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
          kind:
              _optionalAliasText(reason, const <String>[
                'kind',
                'intersectionKind',
                'sourceRef',
              ]) ??
              '',
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
          subjectType:
              _optionalAliasText(mention, const <String>[
                'subjectType',
                'type',
              ]) ??
              '',
          subjectId:
              _optionalAliasText(mention, const <String>[
                'subjectId',
                'id',
                'homepageId',
              ]) ??
              '',
          displayName:
              _optionalAliasText(mention, const <String>[
                'displayName',
                'label',
                'name',
              ]) ??
              '',
          rangeStart:
              _optionalInt(mention['rangeStart'] ?? mention['start']) ?? 0,
          rangeEnd: _optionalInt(mention['rangeEnd'] ?? mention['end']) ?? 0,
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

String _requiredAliasText(Map<Object?, Object?> map, List<String> keys) {
  for (final key in keys) {
    final text = _optionalText(map[key]);
    if (text != null) {
      return text;
    }
  }
  throw FormatException('${keys.first} must be a non-empty string');
}

String _requiredText(Object? value, String name) {
  final text = _optionalText(value);
  if (text == null) {
    throw FormatException('$name must be a non-empty string');
  }
  return text;
}

String? _optionalAliasText(Map<Object?, Object?> map, List<String> keys) {
  for (final key in keys) {
    final text = _optionalText(map[key]);
    if (text != null) {
      return text;
    }
  }
  return null;
}

String? _optionalText(Object? value) {
  if (value == null) return null;
  if (value is! String) {
    throw FormatException('Expected a string value');
  }
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
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

void _validatePageLimit(int limit) {
  if (limit <= 0 || limit > 100) {
    throw ArgumentError.value(limit, 'limit', 'must be between 1 and 100');
  }
}
