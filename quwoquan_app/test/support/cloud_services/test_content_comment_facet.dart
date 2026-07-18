import 'package:quwoquan_app/cloud/services/content/content_repository.dart';

/// Comment 对象的测试端强类型 Facet。
///
/// 它只实现正式 pure contract，不继承聚合 Repository，也不接受
/// path、operation id、Map body 或字符串反应值。
class TestContentCommentFacet implements ContentCommentFacet {
  TestContentCommentFacet({
    List<ContentCommentListItem> items = const <ContentCommentListItem>[],
    this.actorId = 'test_persona',
  }) : items = List<ContentCommentListItem>.of(items);

  final String actorId;
  List<ContentCommentListItem> items;
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
  Future<ContentCommentPageSlice> listComments({
    required String postId,
    String? cursor,
    int limit = 20,
  }) async {
    _throwIfConfigured();
    queryCalls++;
    return _page(
      items
          .where(
            (item) =>
                item.postId == postId &&
                item.parentCommentId == null &&
                item.status == ContentCommentStatus.active,
          )
          .toList(growable: false),
      cursor: cursor,
      limit: limit,
    );
  }

  @override
  Future<ContentCommentReplyPageSlice> listReplies({
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
                item.status == ContentCommentStatus.active,
          )
          .toList(growable: false),
      cursor: cursor,
      limit: limit,
    );
    return ContentCommentReplyPageSlice(
      items: page.items,
      nextCursor: page.nextCursor,
      total: page.total,
    );
  }

  @override
  Future<ContentAuthorCommentPageSlice> listByAuthor({
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
                item.status == ContentCommentStatus.active,
          )
          .toList(growable: false),
      cursor: cursor,
      limit: limit,
    );
    return ContentAuthorCommentPageSlice(
      items: page.items,
      nextCursor: page.nextCursor,
      total: page.total,
    );
  }

  @override
  Future<ContentReceivedCommentPageSlice> listReceived({
    String? cursor,
    int limit = 20,
  }) async {
    _throwIfConfigured();
    queryCalls++;
    final page = _page(
      items
          .where((item) => item.status == ContentCommentStatus.active)
          .toList(growable: false),
      cursor: cursor,
      limit: limit,
    );
    return ContentReceivedCommentPageSlice(
      items: page.items,
      nextCursor: page.nextCursor,
      total: page.total,
    );
  }

  @override
  Future<ContentCommentCommandResult> createComment(
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
    items = <ContentCommentListItem>[created, ...items];
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
    _throwIfConfigured();
    deleteCalls++;
    lastDeleteCommand = command;
    final current = _required(command.commentId);
    final deleted = current.copyWith(
      version: current.version + 1,
      status: ContentCommentStatus.deleted,
      deletedAt: () => DateTime.now().toUtc(),
    );
    _replace(deleted);
    return ContentCommentCommandResult(
      id: deleted.id,
      version: deleted.version,
      status: deleted.status,
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
    _throwIfConfigured();
    final current = _required(command.commentId);
    final updated = current.copyWith(
      version: current.version + 1,
      attachmentMediaIds: command.attachmentMediaIds,
      attachments: command.attachmentMediaIds
          .map(
            (mediaId) => ContentCommentAttachment(
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
    if (current.viewerReaction == ContentCommentReactionValue.like) {
      likeCount--;
    } else if (current.viewerReaction == ContentCommentReactionValue.dislike) {
      dislikeCount--;
    }
    if (command.reaction == ContentCommentReactionValue.like) {
      likeCount++;
    } else if (command.reaction == ContentCommentReactionValue.dislike) {
      dislikeCount++;
    }
    final updated = current.copyWith(
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

  Future<ContentCommentCommandResult> _changePin(
    ChangeContentCommentPinCommand command,
    bool pinned,
  ) async {
    _throwIfConfigured();
    pinCalls++;
    lastPinCommand = command;
    final current = _required(command.commentId);
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

  ContentCommentPageSlice _page(
    List<ContentCommentListItem> values, {
    required String? cursor,
    required int limit,
  }) {
    final ordered = List<ContentCommentListItem>.of(values)
      ..sort((left, right) {
        if (left.isPinned != right.isPinned) return left.isPinned ? -1 : 1;
        return right.createdAt.compareTo(left.createdAt);
      });
    final offset = int.tryParse(cursor ?? '') ?? 0;
    final start = offset.clamp(0, ordered.length).toInt();
    final end = (start + limit).clamp(0, ordered.length).toInt();
    return ContentCommentPageSlice(
      items: ordered.sublist(start, end),
      nextCursor: end < ordered.length ? '$end' : null,
      total: ordered.length,
    );
  }

  ContentCommentListItem? _find(String id) {
    for (final item in items) {
      if (item.id == id) return item;
      for (final reply in item.replyPreview) {
        if (reply.id == id) return reply;
      }
    }
    return null;
  }

  ContentCommentListItem _required(String id) {
    final current = _find(id);
    if (current == null) throw StateError('comment not found');
    return current;
  }

  void _replace(ContentCommentListItem updated) {
    items = items
        .map((item) {
          if (item.id == updated.id) return updated;
          return item.copyWith(
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

ContentCommentListItem testCommentItem({
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
  List<ContentCommentAttachment> attachments =
      const <ContentCommentAttachment>[],
  List<ContentCommentMention> mentions = const <ContentCommentMention>[],
  ContentCommentStatus status = ContentCommentStatus.active,
  bool isPinned = false,
  DateTime? pinnedAt,
  DateTime? createdAt,
  DateTime? updatedAt,
  DateTime? deletedAt,
  int replyCount = 0,
  List<ContentCommentListItem> replyPreview = const <ContentCommentListItem>[],
  String? replyNextCursor,
  int likeCount = 0,
  int dislikeCount = 0,
  ContentCommentReactionValue viewerReaction = ContentCommentReactionValue.none,
  bool isAuthor = false,
  bool canDelete = false,
  bool canReply = true,
  bool canReport = true,
  bool canPin = false,
}) {
  final timestamp = createdAt ?? DateTime.utc(2026, 7, 14, 8);
  return ContentCommentListItem(
    id: id,
    version: version,
    postId: postId,
    authorId: authorId,
    authorDisplayNameSnapshot: authorDisplayNameSnapshot,
    authorAvatarUrlSnapshot: authorAvatarUrlSnapshot,
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
  );
}
