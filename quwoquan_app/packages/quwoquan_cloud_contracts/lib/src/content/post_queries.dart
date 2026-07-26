import '../operation_request_payload.dart';

/// Content Post 查询契约，来源于 `content/content/post/operations.yaml`。
///
/// 这里仅描述业务请求和响应；surface、route、actor 与追踪上下文由
/// [CloudOperationInvocationContext] 传入生成客户端。
final class ContentPostSearchQuery {
  const ContentPostSearchQuery({
    required this.query,
    this.identity,
    this.type,
    this.categoryId,
    this.subCategory,
    this.cursor,
    this.limit = 20,
  });

  final String query;
  final String? identity;
  final String? type;
  final String? categoryId;
  final String? subCategory;
  final String? cursor;
  final int limit;
}

/// 搜索结果中的交集提示。完整推荐投影仍归推荐域；搜索只消费其展示所需字段。
final class ContentPostSearchIntersectionReason {
  const ContentPostSearchIntersectionReason({
    this.kind = '',
    this.primaryText = '',
    this.secondaryText = '',
    this.strength = 0,
  });

  final String kind;
  final String primaryText;
  final String secondaryText;
  final double strength;
}

/// Content Post 搜索结果的稳定 app-facing view。
final class ContentPostSearchItem {
  const ContentPostSearchItem({
    required this.postId,
    required this.contentType,
    this.contentIdentity,
    this.title,
    this.summary,
    this.coverUrl,
    this.authorId,
    this.authorDisplayName,
    this.authorAvatarUrl,
    this.categoryId,
    this.subCategory,
    this.likeCount = 0,
    this.highlightText,
    this.matchedField,
    this.publishedAt,
    this.connectionState = 'unconnected',
    this.intersectionReason,
  });

  final String postId;
  final String contentType;
  final String? contentIdentity;
  final String? title;
  final String? summary;
  final String? coverUrl;
  final String? authorId;
  final String? authorDisplayName;
  final String? authorAvatarUrl;
  final String? categoryId;
  final String? subCategory;
  final int likeCount;
  final String? highlightText;
  final String? matchedField;
  final DateTime? publishedAt;
  final String connectionState;
  final ContentPostSearchIntersectionReason? intersectionReason;
}

final class ContentPostSearchResultSlice {
  ContentPostSearchResultSlice({
    required Iterable<ContentPostSearchItem> items,
    this.nextCursor,
  }) : items = List<ContentPostSearchItem>.unmodifiable(items);

  final List<ContentPostSearchItem> items;
  final String? nextCursor;
}

/// 我的足迹查询参数。`type` 的业务含义由服务端统一定义。
final class ContentFootprintQuery {
  const ContentFootprintQuery({this.type, this.cursor, this.limit = 20});

  final String? type;
  final String? cursor;
  final int limit;
}

/// 足迹项所携带的最小内容预览，避免把 app DTO 带入纯 Dart 合同包。
final class ContentFootprintPostPreview {
  const ContentFootprintPostPreview({
    required this.postId,
    required this.contentType,
    this.contentIdentity,
    this.title,
    this.body,
    this.authorId,
    this.authorDisplayName,
    this.authorAvatarUrl,
    this.authorBackgroundUrl,
    this.coverUrl,
    this.imageUrls = const <String>[],
    this.videoUrl,
    this.thumbnailUrl,
    this.createdAt,
  });

  final String postId;
  final String contentType;
  final String? contentIdentity;
  final String? title;
  final String? body;
  final String? authorId;
  final String? authorDisplayName;
  final String? authorAvatarUrl;
  final String? authorBackgroundUrl;
  final String? coverUrl;
  final List<String> imageUrls;
  final String? videoUrl;
  final String? thumbnailUrl;
  final DateTime? createdAt;
}

final class ContentFootprintEntry {
  const ContentFootprintEntry({
    required this.postId,
    required this.action,
    required this.occurredAt,
    this.post,
  });

  final String postId;
  final String action;
  final DateTime occurredAt;
  final ContentFootprintPostPreview? post;
}

final class ContentFootprintPage {
  ContentFootprintPage({
    required Iterable<ContentFootprintEntry> items,
    this.nextCursor,
  }) : items = List<ContentFootprintEntry>.unmodifiable(items);

  final List<ContentFootprintEntry> items;
  final String? nextCursor;
}

/// 当前登录用户对 canonical object 的显式「想去」状态查询。
final class EntityWishlistStateQuery {
  const EntityWishlistStateQuery({
    required this.objectId,
    required this.objectKind,
  });

  final String objectId;
  final String objectKind;
}

/// 当前登录用户对 canonical object 的显式「想去」状态。
final class EntityWishlistState {
  const EntityWishlistState({
    required this.objectId,
    required this.objectKind,
    required this.wishlisted,
  });

  final String objectId;
  final String objectKind;
  final bool wishlisted;
}

CloudOperationRequestPayload encodeContentPostSearchQuery(
  ContentPostSearchQuery query,
) {
  final normalizedQuery = _requiredText(query.query, 'query');
  _validatePageLimit(query.limit);
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      'query': normalizedQuery,
      if (_optionalText(query.identity) case final identity?)
        'identity': identity,
      if (_optionalText(query.type) case final type?) 'type': type,
      if (_optionalText(query.categoryId) case final categoryId?)
        'categoryId': categoryId,
      if (_optionalText(query.subCategory) case final subCategory?)
        'subCategory': subCategory,
      if (_optionalText(query.cursor) case final cursor?) 'cursor': cursor,
      'limit': '${query.limit}',
    },
  );
}

CloudOperationRequestPayload encodeContentFootprintQuery(
  ContentFootprintQuery query,
) {
  _validatePageLimit(query.limit);
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (_optionalText(query.type) case final type?) 'type': type,
      if (_optionalText(query.cursor) case final cursor?) 'cursor': cursor,
      'limit': '${query.limit}',
    },
  );
}

CloudOperationRequestPayload encodeEntityWishlistStateQuery(
  EntityWishlistStateQuery query,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      'objectId': _requiredText(query.objectId, 'objectId'),
      'objectKind': _requiredText(query.objectKind, 'objectKind'),
    },
  );
}

ContentPostSearchResultSlice decodeContentPostSearchResultSlice(
  Object? response,
) {
  final root = _expectObject(response, 'Content post search response');
  final items = _expectList(
    root['items'],
    'Content post search response.items',
  );
  return ContentPostSearchResultSlice(
    items: items.map(_decodeContentPostSearchItem),
    nextCursor: _optionalText(root['nextCursor']),
  );
}

ContentFootprintPage decodeContentFootprintPage(Object? response) {
  final root = _expectObject(response, 'Content footprint response');
  final items = _expectList(root['items'], 'Content footprint response.items');
  return ContentFootprintPage(
    items: items.map(_decodeContentFootprintEntry),
    nextCursor: _optionalText(root['nextCursor']),
  );
}

EntityWishlistState decodeEntityWishlistState(Object? response) {
  final root = _expectObject(response, 'Entity wishlist state response');
  final wishlisted = root['wishlisted'];
  if (wishlisted is! bool) {
    throw const FormatException(
      'Entity wishlist state response.wishlisted must be a bool',
    );
  }
  return EntityWishlistState(
    objectId: _requiredText(root['objectId'], 'objectId'),
    objectKind: _requiredText(root['objectKind'], 'objectKind'),
    wishlisted: wishlisted,
  );
}

ContentPostSearchItem _decodeContentPostSearchItem(Object? rawItem) {
  final item = _expectObject(rawItem, 'Content post search item');
  final reason = item['intersectionReason'];
  return ContentPostSearchItem(
    postId: _requiredText(item['postId'], 'postId'),
    contentType: _optionalText(item['contentType']) ?? 'image',
    contentIdentity: _optionalText(item['contentIdentity']),
    title: _optionalText(item['title']),
    summary: _optionalText(item['summary']),
    coverUrl: _optionalText(item['coverUrl']),
    authorId: _optionalText(item['authorId']),
    authorDisplayName: _optionalText(item['authorDisplayName']),
    authorAvatarUrl: _optionalText(item['authorAvatarUrl']),
    categoryId: _optionalText(item['categoryId']),
    subCategory: _optionalText(item['subCategory']),
    likeCount: _optionalInt(item['likeCount']) ?? 0,
    highlightText: _optionalText(item['highlightText']),
    matchedField: _optionalText(item['matchedField']),
    publishedAt: _optionalDateTime(item['publishedAt'], 'publishedAt'),
    connectionState: _optionalText(item['connectionState']) ?? 'unconnected',
    intersectionReason: reason == null
        ? null
        : _decodeContentPostSearchIntersectionReason(reason),
  );
}

ContentPostSearchIntersectionReason _decodeContentPostSearchIntersectionReason(
  Object? rawReason,
) {
  final reason = _expectObject(rawReason, 'Content search intersection reason');
  return ContentPostSearchIntersectionReason(
    kind: _optionalText(reason['kind']) ?? '',
    primaryText: _optionalText(reason['primaryText']) ?? '',
    secondaryText: _optionalText(reason['secondaryText']) ?? '',
    strength:
        _optionalDouble(reason['strength']) ??
        _optionalDouble(reason['strengthScore']) ??
        0,
  );
}

ContentFootprintEntry _decodeContentFootprintEntry(Object? rawItem) {
  final item = _expectObject(rawItem, 'Content footprint item');
  final rawPost = item['post'];
  return ContentFootprintEntry(
    postId: _requiredText(item['postId'], 'postId'),
    action: _requiredText(item['action'], 'action'),
    occurredAt: _requiredDateTime(item['occurredAt'], 'occurredAt'),
    post: rawPost == null ? null : _decodeContentFootprintPostPreview(rawPost),
  );
}

ContentFootprintPostPreview _decodeContentFootprintPostPreview(
  Object? rawPost,
) {
  final post = _expectObject(rawPost, 'Content footprint item.post');
  return ContentFootprintPostPreview(
    postId: _requiredText(post['postId'], 'postId'),
    contentType: _optionalText(post['contentType']) ?? 'image',
    contentIdentity: _optionalText(post['contentIdentity']),
    title: _optionalText(post['title']),
    body: _optionalText(post['body']),
    authorId: _optionalText(post['authorId']),
    authorDisplayName: _optionalText(post['authorDisplayName']),
    authorAvatarUrl: _optionalText(post['authorAvatarUrl']),
    authorBackgroundUrl: _optionalText(post['authorBackgroundUrl']),
    coverUrl: _optionalText(post['coverUrl']),
    imageUrls: _optionalStringList(
      post['imageUrls'],
      'Content footprint item.post image URLs',
    ),
    videoUrl: _optionalText(post['videoUrl']),
    thumbnailUrl: _optionalText(post['thumbnailUrl']),
    createdAt: _optionalDateTime(post['createdAt'], 'createdAt'),
  );
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
  if (value == null) {
    return null;
  }
  if (value is! String) {
    throw FormatException('Expected a string value');
  }
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}

int? _optionalInt(Object? value) {
  if (value == null) {
    return null;
  }
  if (value is num) {
    return value.toInt();
  }
  if (value is String) {
    return int.tryParse(value.trim());
  }
  throw FormatException('Expected an integer value');
}

double? _optionalDouble(Object? value) {
  if (value == null) {
    return null;
  }
  if (value is num) {
    return value.toDouble();
  }
  if (value is String) {
    return double.tryParse(value.trim());
  }
  throw FormatException('Expected a numeric value');
}

DateTime _requiredDateTime(Object? value, String name) {
  final parsed = _optionalDateTime(value, name);
  if (parsed == null) {
    throw FormatException('$name must be an ISO-8601 timestamp');
  }
  return parsed;
}

DateTime? _optionalDateTime(Object? value, String name) {
  if (value == null) {
    return null;
  }
  if (value is! String) {
    throw FormatException('$name must be an ISO-8601 timestamp');
  }
  final normalized = value.trim();
  if (normalized.isEmpty) {
    return null;
  }
  final parsed = DateTime.tryParse(normalized);
  if (parsed == null) {
    throw FormatException('$name must be an ISO-8601 timestamp');
  }
  return parsed;
}

List<String> _optionalStringList(Object? value, String context) {
  if (value == null) {
    return const <String>[];
  }
  final values = _expectList(value, context);
  return List<String>.unmodifiable(
    values
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
