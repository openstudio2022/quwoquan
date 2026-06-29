import 'content_errors.g.dart';

extension ContentErrorCodeExt on ContentErrorCode {
  String get code {
    switch (this) {
      case ContentErrorCode.postNotFound:
        return 'CONTENT.USER.post_not_found';
      case ContentErrorCode.commentNotFound:
        return 'CONTENT.USER.comment_not_found';
      case ContentErrorCode.forbiddenEdit:
        return 'CONTENT.USER.forbidden_edit';
      case ContentErrorCode.forbiddenDelete:
        return 'CONTENT.USER.forbidden_delete';
      case ContentErrorCode.unauthorized:
        return 'CONTENT.USER.unauthorized';
      case ContentErrorCode.invalidArgument:
        return 'CONTENT.USER.invalid_argument';
      case ContentErrorCode.assistantMentionContextMissing:
        return 'CONTENT.USER.assistant_mention_context_missing';
      case ContentErrorCode.invalidContentType:
        return 'CONTENT.USER.invalid_content_type';
      case ContentErrorCode.rateLimited:
        return 'CONTENT.USER.rate_limited';
      case ContentErrorCode.mediaNotFound:
        return 'CONTENT.USER.media_not_found';
      case ContentErrorCode.originalAccessDenied:
        return 'CONTENT.USER.original_access_denied';
      case ContentErrorCode.originalAccessRateLimited:
        return 'CONTENT.USER.original_access_rate_limited';
      case ContentErrorCode.commentTooLong:
        return 'CONTENT.USER.comment_too_long';
      case ContentErrorCode.commentRateLimited:
        return 'CONTENT.USER.comment_rate_limited';
      case ContentErrorCode.commentLikeDuplicate:
        return 'CONTENT.USER.comment_like_duplicate';
      case ContentErrorCode.commentReactionForbidden:
        return 'CONTENT.USER.comment_reaction_forbidden';
      case ContentErrorCode.commentPinForbidden:
        return 'CONTENT.USER.comment_pin_forbidden';
      case ContentErrorCode.commentPinInvalidTarget:
        return 'CONTENT.USER.comment_pin_invalid_target';
      case ContentErrorCode.commentAttachmentLimitExceeded:
        return 'CONTENT.USER.comment_attachment_limit_exceeded';
      case ContentErrorCode.commentAttachmentNotReady:
        return 'CONTENT.USER.comment_attachment_not_ready';
      case ContentErrorCode.commentForbiddenDelete:
        return 'CONTENT.USER.comment_forbidden_delete';
      case ContentErrorCode.contentTooLong:
        return 'CONTENT.USER.content_too_long';
      case ContentErrorCode.mediaNotReady:
        return 'CONTENT.USER.media_not_ready';
      case ContentErrorCode.postImmutableAfterPublish:
        return 'CONTENT.USER.post_immutable_after_publish';
      case ContentErrorCode.publicRequiredForCircleDistribution:
        return 'CONTENT.USER.public_required_for_circle_distribution';
      case ContentErrorCode.invalidMomentPayload:
        return 'CONTENT.USER.invalid_moment_payload';
      case ContentErrorCode.contentDeleted:
        return 'CONTENT.USER.content_deleted';
      case ContentErrorCode.circleDistributionForbidden:
        return 'CONTENT.USER.circle_distribution_forbidden';
      case ContentErrorCode.storageWriteFailed:
        return 'CONTENT.SYSTEM.storage_write_failed';
      case ContentErrorCode.internalError:
        return 'CONTENT.SYSTEM.internal_error';
      case ContentErrorCode.upstreamTimeout:
        return 'CONTENT.MIDDLEWARE.upstream_timeout';
      case ContentErrorCode.unknown:
        return '';
    }
  }
}
