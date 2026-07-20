import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha 内存 HomepageReview facet。
///
/// 行为与 entity-service HomepageReview 聚合同构：
/// - 一 persona 对一主页仅一条记录（软删后再次创建复活同一聚合）；
/// - 只有作者能更新/删除；
/// - 列表仅返回 active，createdAt 降序；
/// - getMine 返回 active 或 deleted（供编辑/复活预填），从未评价抛 not_found。
final class AlphaHomepageReviewFacet
    implements HomepageReviewCommandWriter, HomepageReviewQuery {
  AlphaHomepageReviewFacet({
    String activePersonaId = 'alpha-persona',
    DateTime Function()? clock,
  }) : _activePersonaId = activePersonaId,
       _clock = clock ?? (() => DateTime.now().toUtc());

  final String _activePersonaId;
  final DateTime Function() _clock;
  final Map<String, _AlphaReviewRecord> _records =
      <String, _AlphaReviewRecord>{};

  static String _key(String homepageId, String personaId) =>
      '$personaId\u0000$homepageId';

  @override
  Future<HomepageReviewView> create(CreateHomepageReviewCommand command) async {
    final key = _key(command.homepageId, _activePersonaId);
    final now = _clock();
    final existing = _records[key];
    if (existing == null) {
      final record = _AlphaReviewRecord(
        id: 'alpha_hpr_${_records.length + 1}',
        homepageId: command.homepageId,
        authorPersonaId: _activePersonaId,
        rating: command.rating,
        body: command.body,
        tagRefs: command.tagRefs,
        authorDisplayNameSnapshot: command.authorDisplayNameSnapshot,
        authorAvatarUrlSnapshot: command.authorAvatarUrlSnapshot,
        status: HomepageReviewStatus.active,
        version: 1,
        createdAt: now,
        updatedAt: now,
      );
      _records[key] = record;
      return record.view;
    }
    if (existing.status == HomepageReviewStatus.active) {
      throw StateError(
        'active review already exists; use UpdateHomepageReview',
      );
    }
    final revived = existing.mutate(
      rating: command.rating,
      body: command.body,
      tagRefs: command.tagRefs,
      authorDisplayNameSnapshot: command.authorDisplayNameSnapshot,
      authorAvatarUrlSnapshot: command.authorAvatarUrlSnapshot,
      status: HomepageReviewStatus.active,
      now: now,
    );
    _records[key] = revived;
    return revived.view;
  }

  @override
  Future<HomepageReviewView> update(UpdateHomepageReviewCommand command) async {
    final record = _findById(command.reviewId);
    _requireAuthor(record);
    if (record.status == HomepageReviewStatus.deleted) {
      throw StateError('review is deleted');
    }
    final next = record.mutate(
      rating: command.rating,
      body: command.body,
      tagRefs: command.tagRefs,
      authorDisplayNameSnapshot: command.authorDisplayNameSnapshot,
      authorAvatarUrlSnapshot: command.authorAvatarUrlSnapshot,
      status: HomepageReviewStatus.active,
      now: _clock(),
    );
    _records[_key(record.homepageId, record.authorPersonaId)] = next;
    return next.view;
  }

  @override
  Future<HomepageReviewView> delete(DeleteHomepageReviewCommand command) async {
    final record = _findById(command.reviewId);
    _requireAuthor(record);
    if (record.status == HomepageReviewStatus.deleted) {
      return record.view;
    }
    final next = record.mutate(
      rating: record.rating,
      body: record.body,
      tagRefs: record.tagRefs,
      authorDisplayNameSnapshot: record.authorDisplayNameSnapshot,
      authorAvatarUrlSnapshot: record.authorAvatarUrlSnapshot,
      status: HomepageReviewStatus.deleted,
      now: _clock(),
    );
    _records[_key(record.homepageId, record.authorPersonaId)] = next;
    return next.view;
  }

  @override
  Future<HomepageReviewPageSlice> listByHomepage(
    HomepageReviewListQuery query,
  ) async {
    final items =
        _records.values
            .where(
              (record) =>
                  record.homepageId == query.homepageId &&
                  record.status == HomepageReviewStatus.active,
            )
            .map((record) => record.view)
            .toList(growable: false)
          ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
    return HomepageReviewPageSlice(items: items.take(query.limit));
  }

  @override
  Future<HomepageReviewView> getMine(MyHomepageReviewQuery query) async {
    final record = _records[_key(query.homepageId, _activePersonaId)];
    if (record == null) {
      throw const HomepageReviewNotFoundException();
    }
    return record.view;
  }

  /// 按主页重算真实摘要（与服务端 SummarizeByHomepage 同构），
  /// 供 alpha detail 摘要卡与 local_contract 断言消费。
  ({double? averageRating, int ratingCount, List<String> highlightTags})
  summarize(String homepageId) {
    final active = _records.values
        .where(
          (record) =>
              record.homepageId == homepageId &&
              record.status == HomepageReviewStatus.active,
        )
        .toList(growable: false);
    if (active.isEmpty) {
      return (
        averageRating: null,
        ratingCount: 0,
        highlightTags: const <String>[],
      );
    }
    final total = active.fold<int>(0, (sum, record) => sum + record.rating);
    final tagCounts = <String, int>{};
    for (final record in active) {
      for (final tag in record.tagRefs) {
        tagCounts[tag] = (tagCounts[tag] ?? 0) + 1;
      }
    }
    final rankedTags = tagCounts.keys.toList(growable: false)
      ..sort((a, b) {
        final byCount = tagCounts[b]!.compareTo(tagCounts[a]!);
        return byCount != 0 ? byCount : a.compareTo(b);
      });
    return (
      averageRating: total / active.length,
      ratingCount: active.length,
      highlightTags: rankedTags.take(3).toList(growable: false),
    );
  }

  _AlphaReviewRecord _findById(String reviewId) {
    for (final record in _records.values) {
      if (record.id == reviewId) {
        return record;
      }
    }
    throw StateError('review not found');
  }

  void _requireAuthor(_AlphaReviewRecord record) {
    if (record.authorPersonaId != _activePersonaId) {
      throw StateError('only the author can mutate this review');
    }
  }
}

final class _AlphaReviewRecord {
  const _AlphaReviewRecord({
    required this.id,
    required this.homepageId,
    required this.authorPersonaId,
    required this.rating,
    required this.body,
    required this.tagRefs,
    required this.authorDisplayNameSnapshot,
    required this.authorAvatarUrlSnapshot,
    required this.status,
    required this.version,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String homepageId;
  final String authorPersonaId;
  final int rating;
  final String? body;
  final List<String> tagRefs;
  final String? authorDisplayNameSnapshot;
  final String? authorAvatarUrlSnapshot;
  final HomepageReviewStatus status;
  final int version;
  final DateTime createdAt;
  final DateTime updatedAt;

  _AlphaReviewRecord mutate({
    required int rating,
    required String? body,
    required List<String> tagRefs,
    required String? authorDisplayNameSnapshot,
    required String? authorAvatarUrlSnapshot,
    required HomepageReviewStatus status,
    required DateTime now,
  }) {
    return _AlphaReviewRecord(
      id: id,
      homepageId: homepageId,
      authorPersonaId: authorPersonaId,
      rating: rating,
      body: body,
      tagRefs: tagRefs,
      authorDisplayNameSnapshot:
          authorDisplayNameSnapshot ?? this.authorDisplayNameSnapshot,
      authorAvatarUrlSnapshot:
          authorAvatarUrlSnapshot ?? this.authorAvatarUrlSnapshot,
      status: status,
      version: version + 1,
      createdAt: createdAt,
      updatedAt: now,
    );
  }

  HomepageReviewView get view => HomepageReviewView(
    id: id,
    homepageId: homepageId,
    authorPersonaId: authorPersonaId,
    rating: rating,
    status: status,
    createdAt: createdAt,
    updatedAt: updatedAt,
    authorDisplayNameSnapshot: authorDisplayNameSnapshot,
    authorAvatarUrlSnapshot: authorAvatarUrlSnapshot,
    body: body,
    tagRefs: tagRefs,
  );
}
