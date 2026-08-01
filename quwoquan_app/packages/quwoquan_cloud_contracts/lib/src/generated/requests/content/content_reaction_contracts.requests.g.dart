// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

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

  Map<String, Object?> toJson() => <String, Object?>{
    "postId": this.postId,
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "postId": this.postId,
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "commentId": this.commentId,
    "reaction": switch (this.reaction) { ContentCommentReactionValue.none => "none", ContentCommentReactionValue.like => "like", ContentCommentReactionValue.dislike => "dislike", },
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "postId": this.postId,
  };
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

