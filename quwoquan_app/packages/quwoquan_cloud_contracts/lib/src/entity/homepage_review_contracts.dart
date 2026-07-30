import '../operation_request_payload.dart';
part '../generated/requests/entity/homepage_review_contracts.requests.g.dart';

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

String? _optional(String? value) {
  final text = value?.trim();
  if (text == null || text.isEmpty) return null;
  return text;
}
