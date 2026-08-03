import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../object_scenario_seed_reader.dart';

/// local_contract Comment/ContentReaction 对象替身。
final class AlphaContentCommentFacet implements ContentCommentFacet {
  AlphaContentCommentFacet({
    ObjectScenarioSeedReader? fixtures,
    this.actorId = 'fixture_user_current',
  }) : _items = _readItems(fixtures ?? objectScenarioSeedReader, actorId);

  final String actorId;
  List<ContentCommentListItem> _items;
  int _sequence = 0;

  @override
  Future<CommentPageSlice> listComments({
    required String postId,
    String? cursor,
    int limit = 20,
    ContentCommentSort sort = ContentCommentSort.hot,
  }) async {
    final roots = _items
        .where(
          (item) =>
              item.postId == postId &&
              item.status == ContentCommentStatus.active &&
              item.parentCommentId == null,
        )
        .toList();
    // 与服务端排序契约同源：置顶段在前；hot 档按确定性热度分
    // (like - dislike + 2*reply) 降序，latest 档按时间降序。
    int hotScore(ContentCommentListItem item) =>
        (item.likeCount - item.dislikeCount) + 2 * item.replyCount;
    roots.sort((a, b) {
      if (a.isPinned != b.isPinned) return a.isPinned ? -1 : 1;
      if (a.isPinned && b.isPinned) {
        final pinCompare = (b.pinnedAt ?? DateTime(0)).compareTo(
          a.pinnedAt ?? DateTime(0),
        );
        if (pinCompare != 0) return pinCompare;
      } else if (sort == ContentCommentSort.hot) {
        final scoreCompare = hotScore(b).compareTo(hotScore(a));
        if (scoreCompare != 0) return scoreCompare;
      }
      final createdCompare = b.createdAt.compareTo(a.createdAt);
      if (createdCompare != 0) return createdCompare;
      return b.id.compareTo(a.id);
    });
    return _page(
      List<ContentCommentListItem>.unmodifiable(roots),
      cursor,
      limit,
    );
  }

  @override
  Future<ReplyPageSlice> listReplies({
    required String postId,
    required String commentId,
    String? cursor,
    int limit = 10,
  }) async {
    final replies =
        _items
            .where(
              (item) =>
                  item.postId == postId &&
                  item.parentCommentId == commentId &&
                  item.status == ContentCommentStatus.active,
            )
            .toList(growable: false)
          ..sort((left, right) {
            final createdOrder = left.createdAt.compareTo(right.createdAt);
            if (createdOrder != 0) return createdOrder;
            return left.id.compareTo(right.id);
          });
    final page = _page(replies, cursor, limit);
    return ReplyPageSlice(
      items: page.items,
      nextCursor: page.nextCursor,
      total: page.total,
    );
  }

  @override
  Future<AuthorCommentPageSlice> listByAuthor({
    String? cursor,
    int limit = 20,
  }) async {
    final comments =
        _items
            .where(
              (item) =>
                  item.authorId == actorId &&
                  (item.status == ContentCommentStatus.active ||
                      item.status == ContentCommentStatus.hidden),
            )
            .toList(growable: false)
          ..sort(_compareLatest);
    final page = _page(comments, cursor, limit);
    return AuthorCommentPageSlice(
      items: page.items,
      nextCursor: page.nextCursor,
      total: page.total,
    );
  }

  @override
  Future<ReceivedCommentPageSlice> listReceived({
    String? cursor,
    int limit = 20,
  }) async {
    final comments =
        _items
            .where(
              (item) =>
                  item.authorId != actorId &&
                  item.status == ContentCommentStatus.active,
            )
            .toList(growable: false)
          ..sort(_compareLatest);
    final page = _page(comments, cursor, limit);
    return ReceivedCommentPageSlice(
      items: page.items,
      nextCursor: page.nextCursor,
      total: page.total,
    );
  }

  @override
  Future<ContentCommentCommandResult> createComment(
    CreateContentCommentCommand command,
  ) async {
    final now = DateTime.now().toUtc();
    final parent = command.replyToCommentId == null
        ? null
        : _find(command.replyToCommentId!);
    final id = 'alpha_comment_${++_sequence}';
    final item = ContentCommentListItem(
      id: id,
      version: 1,
      postId: command.postId,
      authorId: actorId,
      authorDisplayNameSnapshot: command.authorDisplayNameSnapshot,
      authorAvatarUrlSnapshot: command.authorAvatarUrlSnapshot,
      personaContextVersion: command.personaContextVersion,
      content: command.content,
      replyToCommentId: command.replyToCommentId,
      replyToUserId: parent?.authorId,
      parentCommentId: parent == null
          ? null
          : (parent.parentCommentId ?? parent.id),
      attachmentMediaIds: command.attachmentMediaIds,
      attachments: command.attachmentMediaIds
          .map(
            (mediaId) => CommentAttachmentSlice(
              mediaId: mediaId,
              mediaType: null,
              url: null,
              width: null,
              height: null,
              available: false,
            ),
          )
          .toList(growable: false),
      mentions: command.mentions,
      assistantMentioned: false,
      assistantReplySource: null,
      assistantCorrectionStatus: null,
      status: ContentCommentStatus.active,
      isPinned: false,
      pinnedAt: null,
      createdAt: now,
      updatedAt: now,
      deletedAt: null,
      replyCount: 0,
      replyPreview: const <ContentCommentListItem>[],
      replyNextCursor: null,
      likeCount: 0,
      dislikeCount: 0,
      viewerReaction: ContentCommentReactionValue.none,
      isAuthor: true,
      canDelete: true,
      canReply: true,
      canReport: false,
      canPin: false,
    );
    _items = <ContentCommentListItem>[item, ..._items];
    return ContentCommentCommandResult(
      id: id,
      version: 1,
      status: ContentCommentStatus.active,
      replayed: false,
    );
  }

  @override
  Future<ContentCommentCommandResult> deleteComment(
    DeleteContentCommentCommand command,
  ) async {
    final current = _required(command.commentId);
    if (current.status == ContentCommentStatus.deleted) {
      return ContentCommentCommandResult(
        id: current.id,
        version: current.version,
        status: current.status,
        replayed: true,
      );
    }
    final now = DateTime.now().toUtc();
    final updated = current.copyWith(
      version: current.version + 1,
      status: ContentCommentStatus.deleted,
      deletedAt: () => now,
    );
    _replace(updated);
    return ContentCommentCommandResult(
      id: updated.id,
      version: updated.version,
      status: updated.status,
      replayed: false,
    );
  }

  @override
  Future<ContentCommentCommandResult> pinComment(
    ChangeContentCommentPinCommand command,
  ) => _changePin(command, true);

  @override
  Future<ContentCommentCommandResult> unpinComment(
    ChangeContentCommentPinCommand command,
  ) => _changePin(command, false);

  @override
  Future<ContentCommentCommandResult> bindAttachments(
    BindContentCommentAttachmentsCommand command,
  ) async {
    final current = _required(command.commentId);
    if (_sameStrings(current.attachmentMediaIds, command.attachmentMediaIds)) {
      return ContentCommentCommandResult(
        id: current.id,
        version: current.version,
        status: current.status,
        replayed: true,
      );
    }
    final updated = current.copyWith(
      version: current.version + 1,
      attachmentMediaIds: command.attachmentMediaIds,
      attachments: command.attachmentMediaIds
          .map(
            (mediaId) => CommentAttachmentSlice(
              mediaId: mediaId,
              mediaType: null,
              url: null,
              width: null,
              height: null,
              available: false,
            ),
          )
          .toList(growable: false),
    );
    _replace(updated);
    return ContentCommentCommandResult(
      id: updated.id,
      version: updated.version,
      status: updated.status,
      replayed: false,
    );
  }

  Future<ContentCommentCommandResult> _changePin(
    ChangeContentCommentPinCommand command,
    bool pinned,
  ) async {
    final current = _required(command.commentId);
    if (current.isPinned == pinned) {
      return ContentCommentCommandResult(
        id: current.id,
        version: current.version,
        status: current.status,
        replayed: true,
      );
    }
    final updated = current.copyWith(
      version: current.version + 1,
      isPinned: pinned,
      pinnedAt: () => pinned ? DateTime.now().toUtc() : null,
    );
    _replace(updated);
    return ContentCommentCommandResult(
      id: updated.id,
      version: updated.version,
      status: updated.status,
      replayed: false,
    );
  }

  @override
  Future<ContentCommentReactionCommandResult> reactToComment(
    ReactToContentCommentCommand command,
  ) async {
    final current = _find(command.commentId);
    if (current == null) throw StateError('Comment not found');
    var likeCount = current.likeCount;
    var dislikeCount = current.dislikeCount;
    if (current.viewerReaction == ContentCommentReactionValue.like) likeCount--;
    if (current.viewerReaction == ContentCommentReactionValue.dislike) {
      dislikeCount--;
    }
    if (command.reaction == ContentCommentReactionValue.like) likeCount++;
    if (command.reaction == ContentCommentReactionValue.dislike) dislikeCount++;
    final updated = current.copyWith(
      likeCount: likeCount < 0 ? 0 : likeCount,
      dislikeCount: dislikeCount < 0 ? 0 : dislikeCount,
      viewerReaction: command.reaction,
    );
    _replace(updated);
    return ContentCommentReactionCommandResult(
      reactionId: 'alpha_reaction_${current.id}_$actorId',
      version: 1,
      reaction: command.reaction,
      changed: current.viewerReaction != command.reaction,
      replayed: false,
      likeCount: updated.likeCount,
      dislikeCount: updated.dislikeCount,
    );
  }

  CommentPageSlice _page(
    List<ContentCommentListItem> values,
    String? cursor,
    int limit,
  ) {
    final offset = int.tryParse(cursor ?? '') ?? 0;
    final start = offset.clamp(0, values.length).toInt();
    final pageSize = limit.clamp(1, 100).toInt();
    final end = (start + pageSize).clamp(0, values.length).toInt();
    return CommentPageSlice(
      items: values.sublist(start, end),
      nextCursor: end < values.length ? '$end' : null,
      total: values.length,
    );
  }

  static int _compareLatest(
    ContentCommentListItem left,
    ContentCommentListItem right,
  ) {
    final createdOrder = right.createdAt.compareTo(left.createdAt);
    if (createdOrder != 0) return createdOrder;
    return right.id.compareTo(left.id);
  }

  ContentCommentListItem? _find(String id) {
    for (final item in _items) {
      if (item.id == id) return item;
    }
    return null;
  }

  ContentCommentListItem _required(String id) {
    final item = _find(id);
    if (item == null) throw StateError('Comment not found');
    return item;
  }

  bool _sameStrings(List<String> left, List<String> right) {
    if (left.length != right.length) return false;
    for (var index = 0; index < left.length; index++) {
      if (left[index] != right[index]) return false;
    }
    return true;
  }

  void _replace(ContentCommentListItem updated) {
    _items = _items
        .map((item) => item.id == updated.id ? updated : item)
        .toList(growable: false);
  }

  static List<ContentCommentListItem> _readItems(
    ObjectScenarioSeedReader fixtures,
    String actorId,
  ) {
    final root = fixtures.document('content');
    if (root['seedSets'] is! Map) {
      throw FormatException('Content alpha fixture seedSets is missing');
    }
    final seed = (root['seedSets'] as Map)['comment_thread_core'];
    if (seed is! Map || seed['comments'] is! List) {
      throw FormatException('comment_thread_core fixture is missing');
    }
    final rawItems = (seed['comments'] as List)
        .whereType<Map>()
        .map((raw) => Map<String, dynamic>.from(raw))
        .toList(growable: false);
    final base = rawItems.map((raw) => _fromFixture(raw, actorId)).toList();
    return base
        .map((item) {
          if (item.parentCommentId != null) return item;
          final replies = base
              .where((candidate) => candidate.parentCommentId == item.id)
              .toList(growable: false);
          return item.copyWith(
            replyCount: replies.length,
            replyPreview: replies.take(1).toList(growable: false),
            replyNextCursor: () => replies.length > 1 ? '1' : null,
          );
        })
        .toList(growable: false);
  }

  static ContentCommentListItem _fromFixture(
    Map<String, dynamic> raw,
    String actorId,
  ) {
    final id = raw['commentId'].toString();
    final authorId = raw['authorId'].toString();
    final createdAt = DateTime.parse(raw['createdAt'].toString()).toUtc();
    return ContentCommentListItem(
      id: id,
      version: (raw['version'] as num?)?.toInt() ?? 1,
      postId: raw['postId'].toString(),
      authorId: authorId,
      authorDisplayNameSnapshot: raw['authorDisplayNameSnapshot']?.toString(),
      authorAvatarUrlSnapshot: raw['authorAvatarUrlSnapshot']?.toString(),
      personaContextVersion: (raw['personaContextVersion'] as num?)?.toInt(),
      content: raw['content'].toString(),
      replyToCommentId: raw['replyToCommentId']?.toString(),
      replyToUserId: raw['replyToUserId']?.toString(),
      parentCommentId: raw['parentCommentId']?.toString(),
      attachmentMediaIds: const <String>[],
      attachments: const <CommentAttachmentSlice>[],
      mentions: const <ContentCommentMention>[],
      assistantMentioned: raw['assistantMentioned'] == true,
      assistantReplySource: raw['assistantReplySource']?.toString(),
      assistantCorrectionStatus: raw['assistantCorrectionStatus']?.toString(),
      status: ContentCommentStatus.active,
      isPinned: raw['isPinned'] == true,
      pinnedAt: raw['pinnedAt'] == null
          ? null
          : DateTime.parse(raw['pinnedAt'].toString()).toUtc(),
      createdAt: createdAt,
      updatedAt: createdAt,
      deletedAt: null,
      replyCount: (raw['replyCount'] as num?)?.toInt() ?? 0,
      replyPreview: const <ContentCommentListItem>[],
      replyNextCursor: null,
      likeCount: (raw['likeCount'] as num?)?.toInt() ?? 0,
      dislikeCount: (raw['dislikeCount'] as num?)?.toInt() ?? 0,
      viewerReaction: ContentCommentReactionValue.none,
      isAuthor: authorId == actorId,
      canDelete: authorId == actorId,
      canReply: true,
      canReport: authorId != actorId,
      canPin: false,
    );
  }
}
