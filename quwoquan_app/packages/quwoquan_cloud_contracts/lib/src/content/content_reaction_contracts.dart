import '../operation_request_payload.dart';

enum ContentCommentReactionValue { none, like, dislike }

final class LikeContentPostCommand {
  LikeContentPostCommand({required String postId})
    : postId = _requiredText(postId, 'postId');

  final String postId;
}

final class UnlikeContentPostCommand {
  UnlikeContentPostCommand({required String postId})
    : postId = _requiredText(postId, 'postId');

  final String postId;
}

final class ReactToContentCommentCommand {
  ReactToContentCommentCommand({
    required String commentId,
    required this.reaction,
  }) : commentId = _requiredText(commentId, 'commentId');

  final String commentId;
  final ContentCommentReactionValue reaction;
}

final class GetContentPostReactionStateQuery {
  GetContentPostReactionStateQuery({required String postId})
    : postId = _requiredText(postId, 'postId');

  final String postId;
}

final class ContentReactionCommandResult {
  const ContentReactionCommandResult({
    required this.reactionId,
    required this.postId,
    required this.version,
    required this.liked,
    required this.changed,
    required this.replayed,
  });

  final String reactionId;
  final String postId;
  final int version;
  final bool liked;
  final bool changed;
  final bool replayed;
}

final class ContentCommentReactionCommandResult {
  const ContentCommentReactionCommandResult({
    required this.reactionId,
    required this.version,
    required this.reaction,
    required this.changed,
    required this.replayed,
    required this.likeCount,
    required this.dislikeCount,
  });

  final String reactionId;
  final int version;
  final ContentCommentReactionValue reaction;
  final bool changed;
  final bool replayed;
  final int likeCount;
  final int dislikeCount;
}

final class ContentPostReactionStateSlice {
  const ContentPostReactionStateSlice({
    required this.found,
    required this.postId,
    required this.liked,
    required this.version,
    required this.updatedAt,
  });

  final bool found;
  final String postId;
  final bool liked;
  final int version;
  final DateTime? updatedAt;
}

CloudOperationRequestPayload encodeLikeContentPostCommand(
  LikeContentPostCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'postId': command.postId},
);

CloudOperationRequestPayload encodeUnlikeContentPostCommand(
  UnlikeContentPostCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'postId': command.postId},
);

CloudOperationRequestPayload encodeReactToContentCommentCommand(
  ReactToContentCommentCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'commentId': command.commentId},
  body: <String, Object?>{'reaction': command.reaction.name},
);

CloudOperationRequestPayload encodeGetContentPostReactionStateQuery(
  GetContentPostReactionStateQuery query,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'postId': query.postId},
);

ContentReactionCommandResult decodeContentReactionCommandResult(Object? value) {
  final map = _object(value, 'ContentReactionCommandResult');
  return ContentReactionCommandResult(
    reactionId: _string(map, 'reactionId'),
    postId: _string(map, 'postId'),
    version: _integer(map, 'version'),
    liked: _boolean(map, 'liked'),
    changed: _boolean(map, 'changed'),
    replayed: _optionalBoolean(map, 'replayed') ?? false,
  );
}

ContentCommentReactionCommandResult decodeContentCommentReactionCommandResult(
  Object? value,
) {
  final map = _object(value, 'ContentCommentReactionCommandResult');
  final rawReaction = _string(map, 'reaction');
  final reaction = ContentCommentReactionValue.values.firstWhere(
    (value) => value.name == rawReaction,
    orElse: () =>
        throw FormatException('reaction has unsupported value $rawReaction'),
  );
  return ContentCommentReactionCommandResult(
    reactionId: _string(map, 'reactionId'),
    version: _integer(map, 'version'),
    reaction: reaction,
    changed: _boolean(map, 'changed'),
    replayed: _optionalBoolean(map, 'replayed') ?? false,
    likeCount: _integer(map, 'likeCount'),
    dislikeCount: _integer(map, 'dislikeCount'),
  );
}

ContentPostReactionStateSlice decodeContentPostReactionStateSlice(
  Object? value,
) {
  final map = _object(value, 'ContentPostReactionStateSlice');
  return ContentPostReactionStateSlice(
    found: _boolean(map, 'found'),
    postId: _string(map, 'postId'),
    liked: _boolean(map, 'liked'),
    version: _integer(map, 'version'),
    updatedAt: _optionalTimestamp(map, 'updatedAt'),
  );
}

Map<String, Object?> _object(Object? value, String context) {
  if (value is! Map) throw FormatException('$context must be an object');
  return value.map((key, item) => MapEntry(key.toString(), item));
}

String _string(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key must be a non-empty string');
  }
  return value;
}

int _integer(Map<String, Object?> map, String key) {
  final value = map[key];
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

DateTime? _optionalTimestamp(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value == null) return null;
  if (value is! String) throw FormatException('$key must be RFC3339');
  final parsed = DateTime.tryParse(value);
  if (parsed == null) throw FormatException('$key must be RFC3339');
  return parsed.toUtc();
}

String _requiredText(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(value, name, 'must not be empty');
  }
  return normalized;
}
