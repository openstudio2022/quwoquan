import '../operation_request_payload.dart';

// HomepageReview 对象专属 pure contracts：
// 命令（create/update/delete）与查询（list/mine）。
// 幂等身份只来自 Idempotency-Key header，命令体不携带版本或幂等键。

abstract interface class HomepageReviewCommandWriter {
  Future<HomepageReviewView> create(CreateHomepageReviewCommand command);

  Future<HomepageReviewView> update(UpdateHomepageReviewCommand command);

  Future<HomepageReviewView> delete(DeleteHomepageReviewCommand command);
}

abstract interface class HomepageReviewQuery {
  Future<HomepageReviewPageSlice> listByHomepage(HomepageReviewListQuery query);

  /// 当前 persona 对该主页的评价（active 或 deleted 均返回，供编辑/复活预填）；
  /// 从未评价过时抛出 review_not_found 结构化错误。
  Future<HomepageReviewView> getMine(MyHomepageReviewQuery query);
}

/// Alpha/test 适配器对齐 `ENTITY.USER.review_not_found` 的强类型边界信号。
///
/// Remote 仍由运行时 mapper 抛出带同一错误码的 CloudException。
final class HomepageReviewNotFoundException implements Exception {
  const HomepageReviewNotFoundException();
}

enum HomepageReviewStatus {
  active,
  deleted;

  static HomepageReviewStatus fromWire(String value) {
    return switch (value) {
      'active' => HomepageReviewStatus.active,
      'deleted' => HomepageReviewStatus.deleted,
      _ => throw FormatException('unknown HomepageReview status "$value"'),
    };
  }
}

final class CreateHomepageReviewCommand {
  CreateHomepageReviewCommand({
    required String homepageId,
    required this.rating,
    String? body,
    List<String> tagRefs = const <String>[],
    String? authorDisplayNameSnapshot,
    String? authorAvatarUrlSnapshot,
  }) : homepageId = _required(homepageId, 'homepageId'),
       body = _optional(body),
       tagRefs = _tagRefs(tagRefs),
       authorDisplayNameSnapshot = _optional(authorDisplayNameSnapshot),
       authorAvatarUrlSnapshot = _optional(authorAvatarUrlSnapshot) {
    _requireRating(rating);
  }

  final String homepageId;
  final int rating;
  final String? body;
  final List<String> tagRefs;
  final String? authorDisplayNameSnapshot;
  final String? authorAvatarUrlSnapshot;
}

CloudOperationRequestPayload encodeCreateHomepageReviewCommand(
  CreateHomepageReviewCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'homepageId': command.homepageId},
    body: _reviewBody(
      rating: command.rating,
      body: command.body,
      tagRefs: command.tagRefs,
      authorDisplayNameSnapshot: command.authorDisplayNameSnapshot,
      authorAvatarUrlSnapshot: command.authorAvatarUrlSnapshot,
    ),
  );
}

final class UpdateHomepageReviewCommand {
  UpdateHomepageReviewCommand({
    required String reviewId,
    required this.rating,
    String? body,
    List<String> tagRefs = const <String>[],
    String? authorDisplayNameSnapshot,
    String? authorAvatarUrlSnapshot,
  }) : reviewId = _required(reviewId, 'reviewId'),
       body = _optional(body),
       tagRefs = _tagRefs(tagRefs),
       authorDisplayNameSnapshot = _optional(authorDisplayNameSnapshot),
       authorAvatarUrlSnapshot = _optional(authorAvatarUrlSnapshot) {
    _requireRating(rating);
  }

  final String reviewId;
  final int rating;
  final String? body;
  final List<String> tagRefs;
  final String? authorDisplayNameSnapshot;
  final String? authorAvatarUrlSnapshot;
}

CloudOperationRequestPayload encodeUpdateHomepageReviewCommand(
  UpdateHomepageReviewCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'reviewId': command.reviewId},
    body: _reviewBody(
      rating: command.rating,
      body: command.body,
      tagRefs: command.tagRefs,
      authorDisplayNameSnapshot: command.authorDisplayNameSnapshot,
      authorAvatarUrlSnapshot: command.authorAvatarUrlSnapshot,
    ),
  );
}

final class DeleteHomepageReviewCommand {
  DeleteHomepageReviewCommand({required String reviewId})
    : reviewId = _required(reviewId, 'reviewId');

  final String reviewId;
}

CloudOperationRequestPayload encodeDeleteHomepageReviewCommand(
  DeleteHomepageReviewCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'reviewId': command.reviewId},
  );
}

final class HomepageReviewListQuery {
  HomepageReviewListQuery({
    required String homepageId,
    this.cursor,
    this.limit = 20,
  }) : homepageId = _required(homepageId, 'homepageId') {
    if (limit < 1 || limit > 100) {
      throw ArgumentError.value(limit, 'limit', 'must be within 1..100');
    }
  }

  final String homepageId;
  final String? cursor;
  final int limit;
}

CloudOperationRequestPayload encodeHomepageReviewListQuery(
  HomepageReviewListQuery query,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'homepageId': query.homepageId},
    queryParameters: <String, String>{
      'cursor': ?_optional(query.cursor),
      'limit': '${query.limit}',
    },
  );
}

final class MyHomepageReviewQuery {
  MyHomepageReviewQuery({required String homepageId})
    : homepageId = _required(homepageId, 'homepageId');

  final String homepageId;
}

CloudOperationRequestPayload encodeMyHomepageReviewQuery(
  MyHomepageReviewQuery query,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'homepageId': query.homepageId},
  );
}

final class HomepageReviewView {
  const HomepageReviewView({
    required this.id,
    required this.homepageId,
    required this.authorPersonaId,
    required this.rating,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
    this.authorDisplayNameSnapshot,
    this.authorAvatarUrlSnapshot,
    this.body,
    this.tagRefs = const <String>[],
  });

  final String id;
  final String homepageId;
  final String authorPersonaId;
  final int rating;
  final HomepageReviewStatus status;
  final DateTime createdAt;
  final DateTime updatedAt;
  final String? authorDisplayNameSnapshot;
  final String? authorAvatarUrlSnapshot;
  final String? body;
  final List<String> tagRefs;
}

HomepageReviewView decodeHomepageReviewView(Object? response) {
  final root = _expectObject(response, 'HomepageReview response');
  return _decodeReview(root);
}

final class HomepageReviewPageSlice {
  HomepageReviewPageSlice({
    Iterable<HomepageReviewView> items = const <HomepageReviewView>[],
    this.nextCursor,
  }) : items = List<HomepageReviewView>.unmodifiable(items);

  final List<HomepageReviewView> items;
  final String? nextCursor;
}

HomepageReviewPageSlice decodeHomepageReviewPageSlice(Object? response) {
  final root = _expectObject(response, 'HomepageReview page response');
  final rawItems = root['items'];
  if (rawItems is! List) {
    throw const FormatException('HomepageReview page items must be a list');
  }
  return HomepageReviewPageSlice(
    items: rawItems.map(
      (item) => _decodeReview(_expectObject(item, 'HomepageReview item')),
    ),
    nextCursor: _optional(root['nextCursor'] as String?),
  );
}

HomepageReviewView _decodeReview(Map<Object?, Object?> root) {
  final rating = root['rating'];
  if (rating is! int || rating < 1 || rating > 5) {
    throw const FormatException('HomepageReview rating must be an int in 1..5');
  }
  return HomepageReviewView(
    id: _requiredField(root, 'id'),
    homepageId: _requiredField(root, 'homepageId'),
    authorPersonaId: _requiredField(root, 'authorPersonaId'),
    rating: rating,
    status: HomepageReviewStatus.fromWire(_requiredField(root, 'status')),
    createdAt: _timestamp(root['createdAt'], 'createdAt'),
    updatedAt: _timestamp(root['updatedAt'], 'updatedAt'),
    authorDisplayNameSnapshot: _optional(
      root['authorDisplayNameSnapshot'] as String?,
    ),
    authorAvatarUrlSnapshot: _optional(
      root['authorAvatarUrlSnapshot'] as String?,
    ),
    body: _optional(root['body'] as String?),
    tagRefs: _stringList(root['tagRefs']),
  );
}

Map<String, Object?> _reviewBody({
  required int rating,
  required String? body,
  required List<String> tagRefs,
  required String? authorDisplayNameSnapshot,
  required String? authorAvatarUrlSnapshot,
}) {
  return <String, Object?>{
    'rating': rating,
    'body': ?body,
    if (tagRefs.isNotEmpty) 'tagRefs': tagRefs,
    'authorDisplayNameSnapshot': ?authorDisplayNameSnapshot,
    'authorAvatarUrlSnapshot': ?authorAvatarUrlSnapshot,
  };
}

void _requireRating(int rating) {
  if (rating < 1 || rating > 5) {
    throw ArgumentError.value(rating, 'rating', 'must be within 1..5');
  }
}

List<String> _tagRefs(List<String> tagRefs) {
  return List<String>.unmodifiable(
    tagRefs.map((tag) => tag.trim()).where((tag) => tag.isNotEmpty),
  );
}

Map<Object?, Object?> _expectObject(Object? value, String context) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$context must be a JSON object');
  }
  return value;
}

String _requiredField(Map<Object?, Object?> root, String key) {
  final value = root[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('missing required field "$key"');
  }
  return value.trim();
}

List<String> _stringList(Object? value) {
  if (value == null) return const <String>[];
  if (value is! List) {
    throw const FormatException('expected a string list');
  }
  return List<String>.unmodifiable(
    value.map((item) {
      if (item is! String) {
        throw const FormatException('expected a string list element');
      }
      return item;
    }),
  );
}

DateTime _timestamp(Object? value, String name) {
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$name must be an ISO-8601 string');
  }
  return DateTime.parse(value.trim()).toUtc();
}

String _required(String value, String name) {
  final text = value.trim();
  if (text.isEmpty) {
    throw ArgumentError.value(value, name, 'must not be empty');
  }
  return text;
}

String? _optional(String? value) {
  final text = value?.trim();
  if (text == null || text.isEmpty) return null;
  return text;
}
