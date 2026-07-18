import '../operation_request_payload.dart';
import 'content_reaction_contracts.dart';

enum ContentCommentStatus { active, deleted }

final class ContentCommentMention {
  ContentCommentMention({
    required String subjectType,
    required String subjectId,
    String? displayName,
  }) : subjectType = _requiredText(subjectType, 'subjectType'),
       subjectId = _requiredText(subjectId, 'subjectId'),
       displayName = _optionalText(displayName);

  final String subjectType;
  final String subjectId;
  final String? displayName;
}

final class ContentCommentAttachment {
  const ContentCommentAttachment({
    required this.mediaId,
    required this.mediaType,
    required this.url,
    required this.width,
    required this.height,
    required this.available,
  });

  final String mediaId;
  final String? mediaType;
  final String? url;
  final int? width;
  final int? height;
  final bool available;

  String? get displayUrl {
    final value = url?.trim() ?? '';
    return available && value.isNotEmpty ? value : null;
  }

  double? get aspectRatio {
    final resolvedWidth = width;
    final resolvedHeight = height;
    if (resolvedWidth == null ||
        resolvedHeight == null ||
        resolvedWidth <= 0 ||
        resolvedHeight <= 0) {
      return null;
    }
    return resolvedWidth / resolvedHeight;
  }
}

final class CreateContentCommentCommand {
  CreateContentCommentCommand({
    required String postId,
    required String content,
    String? replyToCommentId,
    Iterable<String> attachmentMediaIds = const <String>[],
    Iterable<ContentCommentMention> mentions = const <ContentCommentMention>[],
    String? authorDisplayNameSnapshot,
    String? authorAvatarUrlSnapshot,
    this.personaContextVersion,
  }) : postId = _requiredText(postId, 'postId'),
       content = _requiredText(content, 'content'),
       replyToCommentId = _optionalText(replyToCommentId),
       attachmentMediaIds = List<String>.unmodifiable(
         attachmentMediaIds.map((id) => _requiredText(id, 'attachmentMediaId')),
       ),
       mentions = List<ContentCommentMention>.unmodifiable(mentions),
       authorDisplayNameSnapshot = _optionalText(authorDisplayNameSnapshot),
       authorAvatarUrlSnapshot = _optionalText(authorAvatarUrlSnapshot);

  final String postId;
  final String content;
  final String? replyToCommentId;
  final List<String> attachmentMediaIds;
  final List<ContentCommentMention> mentions;
  final String? authorDisplayNameSnapshot;
  final String? authorAvatarUrlSnapshot;
  final int? personaContextVersion;
}

final class DeleteContentCommentCommand {
  DeleteContentCommentCommand({
    required String postId,
    required String commentId,
  }) : postId = _requiredText(postId, 'postId'),
       commentId = _requiredText(commentId, 'commentId');

  final String postId;
  final String commentId;
}

final class ChangeContentCommentPinCommand {
  ChangeContentCommentPinCommand({
    required String postId,
    required String commentId,
  }) : postId = _requiredText(postId, 'postId'),
       commentId = _requiredText(commentId, 'commentId');

  final String postId;
  final String commentId;
}

final class BindContentCommentAttachmentsCommand {
  BindContentCommentAttachmentsCommand({
    required String commentId,
    required Iterable<String> attachmentMediaIds,
  }) : commentId = _requiredText(commentId, 'commentId'),
       attachmentMediaIds = List<String>.unmodifiable(
         attachmentMediaIds.map((id) => _requiredText(id, 'attachmentMediaId')),
       );

  final String commentId;
  final List<String> attachmentMediaIds;
}

final class ListContentCommentsQuery {
  ListContentCommentsQuery({
    required String postId,
    String? cursor,
    this.limit = 20,
  }) : postId = _requiredText(postId, 'postId'),
       cursor = _optionalText(cursor) {
    _requireLimit(limit);
  }

  final String postId;
  final String? cursor;
  final int limit;
}

final class ListContentCommentRepliesQuery {
  ListContentCommentRepliesQuery({
    required String postId,
    required String commentId,
    String? cursor,
    this.limit = 10,
  }) : postId = _requiredText(postId, 'postId'),
       commentId = _requiredText(commentId, 'commentId'),
       cursor = _optionalText(cursor) {
    _requireLimit(limit);
  }

  final String postId;
  final String commentId;
  final String? cursor;
  final int limit;
}

final class ContentCommentPageQuery {
  ContentCommentPageQuery({String? cursor, this.limit = 20})
    : cursor = _optionalText(cursor) {
    _requireLimit(limit);
  }

  final String? cursor;
  final int limit;
}

final class ContentCommentCommandResult {
  const ContentCommentCommandResult({
    required this.id,
    required this.version,
    required this.status,
    required this.replayed,
  });

  final String id;
  final int version;
  final ContentCommentStatus status;
  final bool replayed;
}

final class ContentCommentListItem {
  const ContentCommentListItem({
    required this.id,
    required this.version,
    required this.postId,
    required this.authorId,
    required this.authorDisplayNameSnapshot,
    required this.authorAvatarUrlSnapshot,
    required this.personaContextVersion,
    required this.content,
    required this.replyToCommentId,
    required this.replyToUserId,
    required this.parentCommentId,
    required this.attachmentMediaIds,
    required this.attachments,
    required this.mentions,
    required this.assistantMentioned,
    required this.assistantReplySource,
    required this.assistantCorrectionStatus,
    required this.status,
    required this.isPinned,
    required this.pinnedAt,
    required this.createdAt,
    required this.updatedAt,
    required this.deletedAt,
    required this.replyCount,
    required this.replyPreview,
    required this.replyNextCursor,
    required this.likeCount,
    required this.dislikeCount,
    required this.viewerReaction,
    required this.isAuthor,
    required this.canDelete,
    required this.canReply,
    required this.canReport,
    required this.canPin,
  });

  final String id;
  final int version;
  final String postId;
  final String authorId;
  final String? authorDisplayNameSnapshot;
  final String? authorAvatarUrlSnapshot;
  final int? personaContextVersion;
  final String content;
  final String? replyToCommentId;
  final String? replyToUserId;
  final String? parentCommentId;
  final List<String> attachmentMediaIds;
  final List<ContentCommentAttachment> attachments;
  final List<ContentCommentMention> mentions;
  final bool assistantMentioned;
  final String? assistantReplySource;
  final String? assistantCorrectionStatus;
  final ContentCommentStatus status;
  final bool isPinned;
  final DateTime? pinnedAt;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime? deletedAt;
  final int replyCount;
  final List<ContentCommentListItem> replyPreview;
  final String? replyNextCursor;
  final int likeCount;
  final int dislikeCount;
  final ContentCommentReactionValue viewerReaction;
  final bool isAuthor;
  final bool canDelete;
  final bool canReply;
  final bool canReport;
  final bool canPin;

  ContentCommentListItem copyWith({
    int? version,
    List<String>? attachmentMediaIds,
    List<ContentCommentAttachment>? attachments,
    int? replyCount,
    List<ContentCommentListItem>? replyPreview,
    String? Function()? replyNextCursor,
    int? likeCount,
    int? dislikeCount,
    ContentCommentReactionValue? viewerReaction,
    ContentCommentStatus? status,
    bool? isPinned,
    DateTime? Function()? pinnedAt,
    DateTime? Function()? deletedAt,
  }) {
    return ContentCommentListItem(
      id: id,
      version: version ?? this.version,
      postId: postId,
      authorId: authorId,
      authorDisplayNameSnapshot: authorDisplayNameSnapshot,
      authorAvatarUrlSnapshot: authorAvatarUrlSnapshot,
      personaContextVersion: personaContextVersion,
      content: content,
      replyToCommentId: replyToCommentId,
      replyToUserId: replyToUserId,
      parentCommentId: parentCommentId,
      attachmentMediaIds: attachmentMediaIds ?? this.attachmentMediaIds,
      attachments: attachments ?? this.attachments,
      mentions: mentions,
      assistantMentioned: assistantMentioned,
      assistantReplySource: assistantReplySource,
      assistantCorrectionStatus: assistantCorrectionStatus,
      status: status ?? this.status,
      isPinned: isPinned ?? this.isPinned,
      pinnedAt: pinnedAt == null ? this.pinnedAt : pinnedAt(),
      createdAt: createdAt,
      updatedAt: updatedAt,
      deletedAt: deletedAt == null ? this.deletedAt : deletedAt(),
      replyCount: replyCount ?? this.replyCount,
      replyPreview: replyPreview ?? this.replyPreview,
      replyNextCursor: replyNextCursor == null
          ? this.replyNextCursor
          : replyNextCursor(),
      likeCount: likeCount ?? this.likeCount,
      dislikeCount: dislikeCount ?? this.dislikeCount,
      viewerReaction: viewerReaction ?? this.viewerReaction,
      isAuthor: isAuthor,
      canDelete: canDelete,
      canReply: canReply,
      canReport: canReport,
      canPin: canPin,
    );
  }
}

class ContentCommentPageSlice {
  const ContentCommentPageSlice({
    required this.items,
    required this.nextCursor,
    required this.total,
  });

  final List<ContentCommentListItem> items;
  final String? nextCursor;
  final int total;
}

final class ContentCommentReplyPageSlice extends ContentCommentPageSlice {
  const ContentCommentReplyPageSlice({
    required super.items,
    required super.nextCursor,
    required super.total,
  });
}

final class ContentAuthorCommentPageSlice extends ContentCommentPageSlice {
  const ContentAuthorCommentPageSlice({
    required super.items,
    required super.nextCursor,
    required super.total,
  });
}

final class ContentReceivedCommentPageSlice extends ContentCommentPageSlice {
  const ContentReceivedCommentPageSlice({
    required super.items,
    required super.nextCursor,
    required super.total,
  });
}

CloudOperationRequestPayload encodeCreateContentCommentCommand(
  CreateContentCommentCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'postId': command.postId},
  body: <String, Object?>{
    'content': command.content,
    if (command.replyToCommentId != null)
      'replyToCommentId': command.replyToCommentId,
    'attachmentMediaIds': command.attachmentMediaIds,
    'mentions': command.mentions
        .map(
          (mention) => <String, Object?>{
            'subjectType': mention.subjectType,
            'subjectId': mention.subjectId,
            if (mention.displayName != null) 'displayName': mention.displayName,
          },
        )
        .toList(growable: false),
    if (command.authorDisplayNameSnapshot != null)
      'authorDisplayNameSnapshot': command.authorDisplayNameSnapshot,
    if (command.authorAvatarUrlSnapshot != null)
      'authorAvatarUrlSnapshot': command.authorAvatarUrlSnapshot,
    if (command.personaContextVersion != null)
      'personaContextVersion': command.personaContextVersion,
  },
);

CloudOperationRequestPayload encodeDeleteContentCommentCommand(
  DeleteContentCommentCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{
    'postId': command.postId,
    'commentId': command.commentId,
  },
);

CloudOperationRequestPayload encodeChangeContentCommentPinCommand(
  ChangeContentCommentPinCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{
    'postId': command.postId,
    'commentId': command.commentId,
  },
);

CloudOperationRequestPayload encodeBindContentCommentAttachmentsCommand(
  BindContentCommentAttachmentsCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'commentId': command.commentId},
  body: <String, Object?>{'attachmentMediaIds': command.attachmentMediaIds},
);

CloudOperationRequestPayload encodeListContentCommentsQuery(
  ListContentCommentsQuery query,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'postId': query.postId},
  queryParameters: <String, String>{
    'limit': '${query.limit}',
    if (query.cursor != null) 'cursor': query.cursor!,
  },
);

CloudOperationRequestPayload encodeListContentCommentRepliesQuery(
  ListContentCommentRepliesQuery query,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{
    'postId': query.postId,
    'commentId': query.commentId,
  },
  queryParameters: <String, String>{
    'limit': '${query.limit}',
    if (query.cursor != null) 'cursor': query.cursor!,
  },
);

CloudOperationRequestPayload encodeContentCommentPageQuery(
  ContentCommentPageQuery query,
) => CloudOperationRequestPayload(
  queryParameters: <String, String>{
    'limit': '${query.limit}',
    if (query.cursor != null) 'cursor': query.cursor!,
  },
);

ContentCommentCommandResult decodeContentCommentCommandResult(Object? value) {
  final map = _object(value, 'ContentCommentCommandResult');
  return ContentCommentCommandResult(
    id: _string(map, 'id'),
    version: _integer(map, 'version'),
    status: _status(map, 'status'),
    replayed: _optionalBoolean(map, 'replayed') ?? false,
  );
}

ContentCommentPageSlice decodeContentCommentPageSlice(Object? value) {
  final page = _decodePage(value, 'ContentCommentPageSlice');
  return ContentCommentPageSlice(
    items: page.items,
    nextCursor: page.nextCursor,
    total: page.total,
  );
}

ContentCommentReplyPageSlice decodeContentCommentReplyPageSlice(Object? value) {
  final page = _decodePage(value, 'ContentCommentReplyPageSlice');
  return ContentCommentReplyPageSlice(
    items: page.items,
    nextCursor: page.nextCursor,
    total: page.total,
  );
}

ContentAuthorCommentPageSlice decodeContentAuthorCommentPageSlice(
  Object? value,
) {
  final page = _decodePage(value, 'ContentAuthorCommentPageSlice');
  return ContentAuthorCommentPageSlice(
    items: page.items,
    nextCursor: page.nextCursor,
    total: page.total,
  );
}

ContentReceivedCommentPageSlice decodeContentReceivedCommentPageSlice(
  Object? value,
) {
  final page = _decodePage(value, 'ContentReceivedCommentPageSlice');
  return ContentReceivedCommentPageSlice(
    items: page.items,
    nextCursor: page.nextCursor,
    total: page.total,
  );
}

ContentCommentPageSlice _decodePage(Object? value, String context) {
  final map = _object(value, context);
  final rawItems = map['items'];
  if (rawItems is! List<Object?>) {
    throw FormatException('$context.items must be an array');
  }
  return ContentCommentPageSlice(
    items: rawItems
        .map((item) => _decodeCommentListItem(item, '$context.items'))
        .toList(growable: false),
    nextCursor: _optionalString(map, 'nextCursor'),
    total: _integer(map, 'total'),
  );
}

ContentCommentListItem _decodeCommentListItem(Object? value, String context) {
  final map = _object(value, context);
  return ContentCommentListItem(
    id: _string(map, 'id'),
    version: _integer(map, 'version'),
    postId: _string(map, 'postId'),
    authorId: _string(map, 'authorId'),
    authorDisplayNameSnapshot: _optionalString(
      map,
      'authorDisplayNameSnapshot',
    ),
    authorAvatarUrlSnapshot: _optionalString(map, 'authorAvatarUrlSnapshot'),
    personaContextVersion: _optionalInteger(map, 'personaContextVersion'),
    content: _string(map, 'content'),
    replyToCommentId: _optionalString(map, 'replyToCommentId'),
    replyToUserId: _optionalString(map, 'replyToUserId'),
    parentCommentId: _optionalString(map, 'parentCommentId'),
    attachmentMediaIds: _stringList(map, 'attachmentMediaIds'),
    attachments: _objectList(map, 'attachments')
        .map(
          (attachment) => ContentCommentAttachment(
            mediaId: _string(attachment, 'mediaId'),
            mediaType: _optionalString(attachment, 'mediaType'),
            url: _optionalString(attachment, 'url'),
            width: _optionalInteger(attachment, 'width'),
            height: _optionalInteger(attachment, 'height'),
            available: _boolean(attachment, 'available'),
          ),
        )
        .toList(growable: false),
    mentions: _objectList(map, 'mentions')
        .map(
          (mention) => ContentCommentMention(
            subjectType: _string(mention, 'subjectType'),
            subjectId: _string(mention, 'subjectId'),
            displayName: _optionalString(mention, 'displayName'),
          ),
        )
        .toList(growable: false),
    assistantMentioned: _boolean(map, 'assistantMentioned'),
    assistantReplySource: _optionalString(map, 'assistantReplySource'),
    assistantCorrectionStatus: _optionalString(
      map,
      'assistantCorrectionStatus',
    ),
    status: _status(map, 'status'),
    isPinned: _boolean(map, 'isPinned'),
    pinnedAt: _optionalTimestamp(map, 'pinnedAt'),
    createdAt: _timestamp(map, 'createdAt'),
    updatedAt: _timestamp(map, 'updatedAt'),
    deletedAt: _optionalTimestamp(map, 'deletedAt'),
    replyCount: _integer(map, 'replyCount'),
    replyPreview: _objectList(map, 'replyPreview')
        .map((reply) => _decodeCommentListItem(reply, '$context.replyPreview'))
        .toList(growable: false),
    replyNextCursor: _optionalString(map, 'replyNextCursor'),
    likeCount: _integer(map, 'likeCount'),
    dislikeCount: _integer(map, 'dislikeCount'),
    viewerReaction: _reactionValue(map, 'viewerReaction'),
    isAuthor: _boolean(map, 'isAuthor'),
    canDelete: _boolean(map, 'canDelete'),
    canReply: _boolean(map, 'canReply'),
    canReport: _boolean(map, 'canReport'),
    canPin: _boolean(map, 'canPin'),
  );
}

Map<String, Object?> _object(Object? value, String context) {
  if (value is! Map) {
    throw FormatException('$context must be an object');
  }
  return value.map((key, item) => MapEntry(key.toString(), item));
}

List<Map<String, Object?>> _objectList(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! List) {
    throw FormatException('$key must be an array');
  }
  return value.map((item) => _object(item, key)).toList(growable: false);
}

List<String> _stringList(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! List || value.any((item) => item is! String)) {
    throw FormatException('$key must be a string array');
  }
  return List<String>.unmodifiable(value.cast<String>());
}

String _string(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key must be a non-empty string');
  }
  return value;
}

String? _optionalString(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value == null) return null;
  if (value is! String) throw FormatException('$key must be a string');
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}

int _integer(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! int) throw FormatException('$key must be an integer');
  return value;
}

int? _optionalInteger(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value == null) return null;
  if (value is! int) throw FormatException('$key must be an integer');
  return value;
}

bool _boolean(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! bool) throw FormatException('$key must be a boolean');
  return value;
}

bool? _optionalBoolean(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value == null) return null;
  if (value is! bool) throw FormatException('$key must be a boolean');
  return value;
}

DateTime _timestamp(Map<String, Object?> map, String key) {
  final value = _string(map, key);
  final parsed = DateTime.tryParse(value);
  if (parsed == null) throw FormatException('$key must be RFC3339');
  return parsed.toUtc();
}

DateTime? _optionalTimestamp(Map<String, Object?> map, String key) {
  final value = _optionalString(map, key);
  if (value == null) return null;
  final parsed = DateTime.tryParse(value);
  if (parsed == null) throw FormatException('$key must be RFC3339');
  return parsed.toUtc();
}

ContentCommentStatus _status(Map<String, Object?> map, String key) {
  final raw = _string(map, key);
  return ContentCommentStatus.values.firstWhere(
    (value) => value.name == raw,
    orElse: () => throw FormatException('$key has unsupported value $raw'),
  );
}

ContentCommentReactionValue _reactionValue(
  Map<String, Object?> map,
  String key,
) {
  final raw = _string(map, key);
  return ContentCommentReactionValue.values.firstWhere(
    (value) => value.name == raw,
    orElse: () => throw FormatException('$key has unsupported value $raw'),
  );
}

String _requiredText(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(value, name, 'must not be empty');
  }
  return normalized;
}

String? _optionalText(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}

void _requireLimit(int limit) {
  if (limit <= 0 || limit > 100) {
    throw ArgumentError.value(limit, 'limit', 'must be between 1 and 100');
  }
}
