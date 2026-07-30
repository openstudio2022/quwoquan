// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../content/comment_contracts.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

List<String> _normalizeGeneratedTextList(
  Iterable<String> values, {
  required bool deduplicate,
}) {
  final result = <String>[];
  final seen = <String>{};
  for (final value in values) {
    final normalized = value.trim();
    if (normalized.isEmpty) continue;
    if (deduplicate && !seen.add(normalized)) continue;
    result.add(normalized);
  }
  return List<String>.unmodifiable(result);
}

final class BindContentCommentAttachmentsCommand {
  BindContentCommentAttachmentsCommand({
    required String commentId,
    required Iterable<String> attachmentMediaIds,
  }) : commentId = commentId.trim(),
       attachmentMediaIds = _normalizeGeneratedTextList(attachmentMediaIds, deduplicate: false) {
    if (this.commentId.isEmpty) {
      throw ArgumentError.value(this.commentId, "commentId", 'must not be blank');
    }
    if (this.attachmentMediaIds.isEmpty) {
      throw ArgumentError.value(this.attachmentMediaIds, "attachmentMediaIds", 'must not be blank');
    }
  }

  final String commentId;
  final List<String> attachmentMediaIds;
}

final class ChangeContentCommentPinCommand {
  ChangeContentCommentPinCommand({
    required String postId,
    required String commentId,
  }) : postId = postId.trim(),
       commentId = commentId.trim() {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
    if (this.commentId.isEmpty) {
      throw ArgumentError.value(this.commentId, "commentId", 'must not be blank');
    }
  }

  final String postId;
  final String commentId;
}

final class ContentCommentPageQuery {
  ContentCommentPageQuery({
    String? cursor,
    int limit = 20,
  }) : cursor = _normalizeGeneratedOptionalText(cursor),
       limit = limit {
  }

  final String? cursor;
  final int limit;
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
    int? personaContextVersion,
  }) : postId = postId.trim(),
       content = content.trim(),
       replyToCommentId = _normalizeGeneratedOptionalText(replyToCommentId),
       attachmentMediaIds = _normalizeGeneratedTextList(attachmentMediaIds, deduplicate: false),
       mentions = List.unmodifiable(mentions),
       authorDisplayNameSnapshot = _normalizeGeneratedOptionalText(authorDisplayNameSnapshot),
       authorAvatarUrlSnapshot = _normalizeGeneratedOptionalText(authorAvatarUrlSnapshot),
       personaContextVersion = personaContextVersion {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
    if (this.content.isEmpty) {
      throw ArgumentError.value(this.content, "content", 'must not be blank');
    }
  }

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
  }) : postId = postId.trim(),
       commentId = commentId.trim() {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
    if (this.commentId.isEmpty) {
      throw ArgumentError.value(this.commentId, "commentId", 'must not be blank');
    }
  }

  final String postId;
  final String commentId;
}

final class ListContentCommentRepliesQuery {
  ListContentCommentRepliesQuery({
    required String postId,
    required String commentId,
    String? cursor,
    int limit = 10,
  }) : postId = postId.trim(),
       commentId = commentId.trim(),
       cursor = _normalizeGeneratedOptionalText(cursor),
       limit = limit {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
    if (this.commentId.isEmpty) {
      throw ArgumentError.value(this.commentId, "commentId", 'must not be blank');
    }
  }

  final String postId;
  final String commentId;
  final String? cursor;
  final int limit;
}

final class ListContentCommentsQuery {
  ListContentCommentsQuery({
    required String postId,
    String? cursor,
    int limit = 20,
    ContentCommentSort sort = ContentCommentSort.hot,
  }) : postId = postId.trim(),
       cursor = _normalizeGeneratedOptionalText(cursor),
       limit = limit,
       sort = sort {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
  }

  final String postId;
  final String? cursor;
  final int limit;
  final ContentCommentSort sort;
}

CloudOperationRequestPayload encodeContentCommentBindMediaAssetsToCommentGeneratedRequest(BindContentCommentAttachmentsCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "commentId": request.commentId,
    },
    body: <String, Object?>{
      "attachmentMediaIds": request.attachmentMediaIds.map((value) => value).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeContentCommentCreateCommentGeneratedRequest(CreateContentCommentCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "postId": request.postId,
    },
    body: <String, Object?>{
      "content": request.content,
      if (request.replyToCommentId != null) "replyToCommentId": request.replyToCommentId!,
      "attachmentMediaIds": request.attachmentMediaIds.map((value) => value).toList(growable: false),
      "mentions": request.mentions.map((value) => <String, Object?>{'subjectType': value.subjectType, 'subjectId': value.subjectId, if (value.displayName != null) 'displayName': value.displayName}).toList(growable: false),
      if (request.authorDisplayNameSnapshot != null) "authorDisplayNameSnapshot": request.authorDisplayNameSnapshot!,
      if (request.authorAvatarUrlSnapshot != null) "authorAvatarUrlSnapshot": request.authorAvatarUrlSnapshot!,
      if (request.personaContextVersion != null) "personaContextVersion": request.personaContextVersion!,
    },
  );
}

CloudOperationRequestPayload encodeContentCommentDeleteCommentGeneratedRequest(DeleteContentCommentCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "postId": request.postId,
      "commentId": request.commentId,
    },
  );
}

CloudOperationRequestPayload encodeContentCommentListCommentRepliesGeneratedRequest(ListContentCommentRepliesQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "postId": request.postId,
      "commentId": request.commentId,
    },
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

CloudOperationRequestPayload encodeContentCommentListCommentsGeneratedRequest(ListContentCommentsQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "postId": request.postId,
    },
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
      "sort": (switch (request.sort) { ContentCommentSort.hot => "hot", ContentCommentSort.latest => "latest", }).toString(),
    },
  );
}

CloudOperationRequestPayload encodeContentCommentListCommentsByAuthorGeneratedRequest(ContentCommentPageQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

CloudOperationRequestPayload encodeContentCommentListCommentsForPostAuthorGeneratedRequest(ContentCommentPageQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

CloudOperationRequestPayload encodeContentCommentPinCommentGeneratedRequest(ChangeContentCommentPinCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "postId": request.postId,
      "commentId": request.commentId,
    },
  );
}

CloudOperationRequestPayload encodeContentCommentUnpinCommentGeneratedRequest(ChangeContentCommentPinCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "postId": request.postId,
      "commentId": request.commentId,
    },
  );
}

