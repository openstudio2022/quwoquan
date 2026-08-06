import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Comment 对象的测试端强类型 Facet。
///
/// 它只实现正式 pure contract，不继承聚合 Repository，也不接受
/// path、operation id、Map body 或字符串反应值。
class InMemoryContentCommentFacet implements ContentCommentFacet {
  InMemoryContentCommentFacet({
    List<CommentListItem> items = const <CommentListItem>[],
    this.actorId = 'test_persona',
  }) : items = List<CommentListItem>.of(items);

  final String actorId;
  List<CommentListItem> items;
  Object? failure;
  int queryCalls = 0;
  int createCalls = 0;
  int deleteCalls = 0;
  int reactionCalls = 0;
  int pinCalls = 0;
  CreateContentCommentCommand? lastCreateCommand;
  DeleteContentCommentCommand? lastDeleteCommand;
  ReactToContentCommentCommand? lastReactionCommand;
  ChangeContentCommentPinCommand? lastPinCommand;
  int _sequence = 0;

  @override
  Future<CommentPageSlice> listComments({
    required String postId,
    String? cursor,
    int limit = 20,
    CommentSort sort = CommentSort.hot,
  }) async {
    _throwIfConfigured();
    queryCalls++;
    return _page(
      items
          .where(
            (item) =>
                item.postId == postId &&
                item.parentCommentId == null &&
                item.status == CommentStatus.active,
          )
          .toList(growable: false),
      cursor: cursor,
      limit: limit,
      compare: (left, right) => _compareRootComments(left, right, sort),
    );
  }

  @override
  Future<ReplyPageSlice> listReplies({
    required String postId,
    required String commentId,
    String? cursor,
    int limit = 10,
  }) async {
    _throwIfConfigured();
    queryCalls++;
    final page = _page(
      items
          .where(
            (item) =>
                item.postId == postId &&
                item.parentCommentId == commentId &&
                item.status == CommentStatus.active,
          )
          .toList(growable: false),
      cursor: cursor,
      limit: limit,
      compare: _compareReplies,
    );
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
    _throwIfConfigured();
    queryCalls++;
    final page = _page(
      items
          .where(
            (item) =>
                item.authorId == actorId &&
                (item.status == CommentStatus.active ||
                    item.status == CommentStatus.hidden),
          )
          .toList(growable: false),
      cursor: cursor,
      limit: limit,
      compare: _compareLatest,
    );
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
    _throwIfConfigured();
    queryCalls++;
    final page = _page(
      items
          .where((item) => item.status == CommentStatus.active)
          .toList(growable: false),
      cursor: cursor,
      limit: limit,
      compare: _compareLatest,
    );
    return ReceivedCommentPageSlice(
      items: page.items,
      nextCursor: page.nextCursor,
      total: page.total,
    );
  }

  @override
  Future<CommentCommandResult> createComment(
    CreateContentCommentCommand command,
  ) async {
    _throwIfConfigured();
    createCalls++;
    lastCreateCommand = command;
    final parent = command.replyToCommentId == null
        ? null
        : _find(command.replyToCommentId!);
    final id = 'created_comment_${++_sequence}';
    final now = DateTime.now().toUtc();
    final created = testCommentItem(
      id: id,
      postId: command.postId,
      authorId: actorId,
      content: command.content,
      replyToCommentId: command.replyToCommentId,
      replyToUserId: parent?.authorId,
      parentCommentId: parent == null
          ? null
          : (parent.parentCommentId ?? parent.id),
      attachmentMediaIds: command.attachmentMediaIds,
      mentions: command.mentions,
      authorDisplayNameSnapshot: command.authorDisplayNameSnapshot,
      authorAvatarUrlSnapshot: command.authorAvatarUrlSnapshot,
      personaContextVersion: command.personaContextVersion,
      createdAt: now,
      updatedAt: now,
      isAuthor: true,
      canDelete: true,
      canReport: false,
    );
    items = <CommentListItem>[created, ...items];
    return CommentCommandResult(
      id: id,
      version: 1,
      status: CommentStatus.active,
      replayed: false,
    );
  }

  @override
  Future<CommentCommandResult> deleteComment(
    DeleteContentCommentCommand command,
  ) async {
    _throwIfConfigured();
    deleteCalls++;
    lastDeleteCommand = command;
    final current = _required(command.commentId);
    final deleted = _copyComment(
      current,
      version: current.version + 1,
      status: CommentStatus.deleted,
      deletedAt: () => DateTime.now().toUtc(),
    );
    _replace(deleted);
    return CommentCommandResult(
      id: deleted.id,
      version: deleted.version,
      status: deleted.status,
      replayed: false,
    );
  }

  @override
  Future<CommentCommandResult> pinComment(
    ChangeContentCommentPinCommand command,
  ) => _changePin(command, true);

  @override
  Future<CommentCommandResult> unpinComment(
    ChangeContentCommentPinCommand command,
  ) => _changePin(command, false);

  @override
  Future<CommentCommandResult> bindAttachments(
    BindContentCommentAttachmentsCommand command,
  ) async {
    _throwIfConfigured();
    final current = _required(command.commentId);
    final updated = _copyComment(
      current,
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
    return CommentCommandResult(
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
    _throwIfConfigured();
    reactionCalls++;
    lastReactionCommand = command;
    final current = _find(command.commentId);
    if (current == null) throw StateError('comment not found');
    var likeCount = current.likeCount;
    var dislikeCount = current.dislikeCount;
    if (current.viewerReaction == CommentReactionType.like) {
      likeCount--;
    } else if (current.viewerReaction == CommentReactionType.dislike) {
      dislikeCount--;
    }
    if (command.reaction == CommentReactionType.like) {
      likeCount++;
    } else if (command.reaction == CommentReactionType.dislike) {
      dislikeCount++;
    }
    final updated = _copyComment(
      current,
      likeCount: likeCount.clamp(0, 1 << 31).toInt(),
      dislikeCount: dislikeCount.clamp(0, 1 << 31).toInt(),
      viewerReaction: command.reaction,
    );
    _replace(updated);
    return ContentCommentReactionCommandResult(
      reactionId: 'test_reaction_${command.commentId}',
      version: 1,
      reaction: command.reaction,
      changed: updated.viewerReaction != current.viewerReaction,
      replayed: false,
      likeCount: updated.likeCount,
      dislikeCount: updated.dislikeCount,
    );
  }

  Future<CommentCommandResult> _changePin(
    ChangeContentCommentPinCommand command,
    bool pinned,
  ) async {
    _throwIfConfigured();
    pinCalls++;
    lastPinCommand = command;
    final current = _required(command.commentId);
    final updated = _copyComment(
      current,
      version: current.version + 1,
      isPinned: pinned,
      pinnedAt: () => pinned ? DateTime.now().toUtc() : null,
    );
    _replace(updated);
    return CommentCommandResult(
      id: updated.id,
      version: updated.version,
      status: updated.status,
      replayed: false,
    );
  }

  CommentPageSlice _page(
    List<CommentListItem> values, {
    required String? cursor,
    required int limit,
    required int Function(CommentListItem left, CommentListItem right) compare,
  }) {
    final ordered = List<CommentListItem>.of(values)..sort(compare);
    final offset = int.tryParse(cursor ?? '') ?? 0;
    final start = offset.clamp(0, ordered.length).toInt();
    final end = (start + limit).clamp(0, ordered.length).toInt();
    return CommentPageSlice(
      items: ordered.sublist(start, end),
      nextCursor: end < ordered.length ? '$end' : null,
      total: ordered.length,
    );
  }

  static int _compareRootComments(
    CommentListItem left,
    CommentListItem right,
    CommentSort sort,
  ) {
    if (left.isPinned != right.isPinned) return left.isPinned ? -1 : 1;
    if (left.isPinned) {
      final pinnedOrder = _compareNullableDateDescending(
        left.pinnedAt,
        right.pinnedAt,
      );
      if (pinnedOrder != 0) return pinnedOrder;
    }
    if (sort == CommentSort.hot) {
      final leftScore =
          left.likeCount - left.dislikeCount + 2 * left.replyCount;
      final rightScore =
          right.likeCount - right.dislikeCount + 2 * right.replyCount;
      final scoreOrder = rightScore.compareTo(leftScore);
      if (scoreOrder != 0) return scoreOrder;
    }
    return _compareLatest(left, right);
  }

  static int _compareLatest(CommentListItem left, CommentListItem right) {
    final createdOrder = right.createdAt.compareTo(left.createdAt);
    if (createdOrder != 0) return createdOrder;
    return right.id.compareTo(left.id);
  }

  static int _compareReplies(CommentListItem left, CommentListItem right) {
    final createdOrder = left.createdAt.compareTo(right.createdAt);
    if (createdOrder != 0) return createdOrder;
    return left.id.compareTo(right.id);
  }

  static int _compareNullableDateDescending(DateTime? left, DateTime? right) {
    if (left == null && right == null) return 0;
    if (left == null) return 1;
    if (right == null) return -1;
    return right.compareTo(left);
  }

  CommentListItem? _find(String id) {
    for (final item in items) {
      if (item.id == id) return item;
      for (final reply in item.replyPreview) {
        if (reply.id == id) return reply;
      }
    }
    return null;
  }

  CommentListItem _required(String id) {
    final current = _find(id);
    if (current == null) throw StateError('comment not found');
    return current;
  }

  void _replace(CommentListItem updated) {
    items = items
        .map((item) {
          if (item.id == updated.id) return updated;
          return _copyComment(
            item,
            replyPreview: item.replyPreview
                .map((reply) => reply.id == updated.id ? updated : reply)
                .toList(growable: false),
          );
        })
        .toList(growable: false);
  }

  void _throwIfConfigured() {
    final configured = failure;
    if (configured != null) throw configured;
  }
}

CommentListItem testCommentItem({
  required String id,
  String postId = 'post_1',
  String authorId = 'test_persona',
  String content = '测试评论',
  int version = 1,
  String? authorDisplayNameSnapshot = '测试用户',
  String? authorAvatarUrlSnapshot,
  int? personaContextVersion = 1,
  String? replyToCommentId,
  String? replyToUserId,
  String? parentCommentId,
  List<String> attachmentMediaIds = const <String>[],
  List<CommentAttachmentSlice> attachments = const <CommentAttachmentSlice>[],
  List<CommentMention> mentions = const <CommentMention>[],
  CommentStatus status = CommentStatus.active,
  bool isPinned = false,
  DateTime? pinnedAt,
  DateTime? createdAt,
  DateTime? updatedAt,
  DateTime? deletedAt,
  int replyCount = 0,
  List<CommentListItem> replyPreview = const <CommentListItem>[],
  String? replyNextCursor,
  int likeCount = 0,
  int dislikeCount = 0,
  CommentReactionType viewerReaction = CommentReactionType.none,
  bool isAuthor = false,
  bool canDelete = false,
  bool canReply = true,
  bool canReport = true,
  bool canPin = false,
  String? authorIpLocation,
  bool authorLiked = false,
  CommentViewerRelation viewerRelation = CommentViewerRelation.none,
}) {
  final timestamp = createdAt ?? DateTime.utc(2026, 7, 14, 8);
  return CommentListItem(
    id: id,
    version: version,
    postId: postId,
    authorId: authorId,
    authorDisplayNameSnapshot: authorDisplayNameSnapshot,
    authorAvatarUrlSnapshot: _optionalUri(authorAvatarUrlSnapshot),
    personaContextVersion: personaContextVersion,
    content: content,
    replyToCommentId: replyToCommentId,
    replyToUserId: replyToUserId,
    parentCommentId: parentCommentId,
    attachmentMediaIds: attachmentMediaIds,
    attachments: attachments,
    mentions: mentions,
    assistantMentioned: false,
    assistantReplySource: null,
    assistantCorrectionStatus: null,
    status: status,
    isPinned: isPinned,
    pinnedAt: pinnedAt,
    createdAt: timestamp,
    updatedAt: updatedAt ?? timestamp,
    deletedAt: deletedAt,
    replyCount: replyCount,
    replyPreview: replyPreview,
    replyNextCursor: replyNextCursor,
    likeCount: likeCount,
    dislikeCount: dislikeCount,
    viewerReaction: viewerReaction,
    isAuthor: isAuthor,
    canDelete: canDelete,
    canReply: canReply,
    canReport: canReport,
    canPin: canPin,
    authorIpLocation: authorIpLocation,
    authorLiked: authorLiked,
    viewerRelation: viewerRelation,
  );
}

CommentListItem _copyComment(
  CommentListItem current, {
  int? version,
  CommentStatus? status,
  DateTime? Function()? deletedAt,
  List<String>? attachmentMediaIds,
  List<CommentAttachmentSlice>? attachments,
  bool? isPinned,
  DateTime? Function()? pinnedAt,
  int? likeCount,
  int? dislikeCount,
  CommentReactionType? viewerReaction,
  List<CommentListItem>? replyPreview,
}) {
  return CommentListItem(
    id: current.id,
    version: version ?? current.version,
    postId: current.postId,
    authorId: current.authorId,
    authorDisplayNameSnapshot: current.authorDisplayNameSnapshot,
    authorAvatarUrlSnapshot: current.authorAvatarUrlSnapshot,
    personaContextVersion: current.personaContextVersion,
    content: current.content,
    replyToCommentId: current.replyToCommentId,
    replyToUserId: current.replyToUserId,
    parentCommentId: current.parentCommentId,
    attachmentMediaIds: attachmentMediaIds ?? current.attachmentMediaIds,
    attachments: attachments ?? current.attachments,
    mentions: current.mentions,
    assistantMentioned: current.assistantMentioned,
    assistantReplySource: current.assistantReplySource,
    assistantCorrectionStatus: current.assistantCorrectionStatus,
    authorIpLocation: current.authorIpLocation,
    status: status ?? current.status,
    isPinned: isPinned ?? current.isPinned,
    pinnedAt: pinnedAt == null ? current.pinnedAt : pinnedAt(),
    createdAt: current.createdAt,
    updatedAt: current.updatedAt,
    deletedAt: deletedAt == null ? current.deletedAt : deletedAt(),
    replyCount: current.replyCount,
    replyPreview: replyPreview ?? current.replyPreview,
    replyNextCursor: current.replyNextCursor,
    likeCount: likeCount ?? current.likeCount,
    dislikeCount: dislikeCount ?? current.dislikeCount,
    viewerReaction: viewerReaction ?? current.viewerReaction,
    authorLiked: current.authorLiked,
    viewerRelation: current.viewerRelation,
    isAuthor: current.isAuthor,
    canDelete: current.canDelete,
    canReply: current.canReply,
    canReport: current.canReport,
    canPin: current.canPin,
  );
}

Uri? _optionalUri(String? raw) {
  final value = raw?.trim() ?? '';
  return value.isEmpty ? null : Uri.parse(value);
}
