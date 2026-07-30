// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../content/content_reaction_contracts.dart';

final class GetContentPostReactionStateQuery {
  GetContentPostReactionStateQuery({
    required String postId,
  }) : postId = postId.trim() {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
  }

  final String postId;
}

final class LikeContentPostCommand {
  LikeContentPostCommand({
    required String postId,
  }) : postId = postId.trim() {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
  }

  final String postId;
}

final class ReactToContentCommentCommand {
  ReactToContentCommentCommand({
    required String commentId,
    required ContentCommentReactionValue reaction,
  }) : commentId = commentId.trim(),
       reaction = reaction {
    if (this.commentId.isEmpty) {
      throw ArgumentError.value(this.commentId, "commentId", 'must not be blank');
    }
  }

  final String commentId;
  final ContentCommentReactionValue reaction;
}

final class UnlikeContentPostCommand {
  UnlikeContentPostCommand({
    required String postId,
  }) : postId = postId.trim() {
    if (this.postId.isEmpty) {
      throw ArgumentError.value(this.postId, "postId", 'must not be blank');
    }
  }

  final String postId;
}

CloudOperationRequestPayload encodeContentContentReactionGetContentReactionStateGeneratedRequest(GetContentPostReactionStateQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "postId": request.postId,
    },
  );
}

CloudOperationRequestPayload encodeContentContentReactionLikePostGeneratedRequest(LikeContentPostCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "postId": request.postId,
    },
  );
}

CloudOperationRequestPayload encodeContentContentReactionReactToCommentGeneratedRequest(ReactToContentCommentCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "commentId": request.commentId,
    },
    body: <String, Object?>{
      "reaction": switch (request.reaction) { ContentCommentReactionValue.none => "none", ContentCommentReactionValue.like => "like", ContentCommentReactionValue.dislike => "dislike", },
    },
  );
}

CloudOperationRequestPayload encodeContentContentReactionUnlikePostGeneratedRequest(UnlikeContentPostCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "postId": request.postId,
    },
  );
}

