// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: contracts/metadata/content/post/fields.yaml (entities.Comment)
// plus wire aliases for API/Mock payloads (displayName, avatar snapshots, etc.).
// Regenerate: make codegen-app

import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';

class CommentDto {
  const CommentDto({
    required this.id,
    required this.postId,
    required this.authorId,
    this.displayName,
    this.avatarUrl,
    required this.content,
    this.replyToCommentId,
    this.replyToUserId,
    this.replyToDisplayName,
    this.parentCommentId,
    this.attachmentMediaIds = const <String>[],
    this.attachments = const <CloudJsonMap>[],
    this.mentions = const <CloudJsonMap>[],
    this.entityRefs = const <String>[],
    this.primaryHomepageId,
    this.canonicalEntityId,
    this.assistantMentioned = false,
    this.assistantReplySource,
    this.assistantCorrectionStatus,
    this.replyCount = 0,
    this.replyPreview = const <CommentDto>[],
    this.replyNextCursor,
    this.postSummary = const <String, dynamic>{},
    this.likeCount = 0,
    this.dislikeCount = 0,
    this.viewerReaction = 'none',
    this.recommendedScore,
    this.status = 'visible',
    this.isAuthor = false,
    this.canDelete = false,
    this.canReply = true,
    this.canReport = true,
    this.personaContextVersion,
    required this.createdAt,
  });

  final String id;
  final String postId;
  final String authorId;
  final String? displayName;
  final String? avatarUrl;
  final String content;
  final String? replyToCommentId;
  final String? replyToUserId;
  final String? replyToDisplayName;
  final String? parentCommentId;
  final List<String> attachmentMediaIds;
  final List<CloudJsonMap> attachments;
  final List<CloudJsonMap> mentions;
  final List<String> entityRefs;
  final String? primaryHomepageId;
  final String? canonicalEntityId;
  final bool assistantMentioned;
  final String? assistantReplySource;
  final String? assistantCorrectionStatus;
  final int replyCount;
  final List<CommentDto> replyPreview;
  final String? replyNextCursor;
  final CloudJsonMap postSummary;
  final int likeCount;
  final int dislikeCount;
  final String viewerReaction;
  final double? recommendedScore;
  final String status;
  final bool isAuthor;
  final bool canDelete;
  final bool canReply;
  final bool canReport;
  final int? personaContextVersion;
  final DateTime createdAt;

  factory CommentDto.fromMap(CloudJsonMap m) {
    return CommentDto(
      id: (m['_id'] ?? m['id'] ?? '').toString(),
      postId: (m['postId'] ?? '').toString(),
      authorId: (m['authorId'] ?? m['subAccountId'] ?? '').toString(),
      displayName: (m['authorDisplayNameSnapshot'] ?? m['displayName'])
          ?.toString(),
      avatarUrl: (m['authorAvatarUrlSnapshot'] ?? m['avatarUrl'])?.toString(),
      content: (m['content'] ?? '').toString(),
      replyToCommentId: m['replyToCommentId']?.toString(),
      replyToUserId: m['replyToUserId']?.toString(),
      replyToDisplayName: m['replyToDisplayName']?.toString(),
      parentCommentId: m['parentCommentId']?.toString(),
      attachmentMediaIds: _commentStringList(m['attachmentMediaIds']),
      attachments: _commentMapList(m['attachments']),
      mentions: _commentMapList(m['mentions']),
      entityRefs: _commentStringList(m['entityRefs']),
      primaryHomepageId: m['primaryHomepageId']?.toString(),
      canonicalEntityId: m['canonicalEntityId']?.toString(),
      assistantMentioned: m['assistantMentioned'] == true,
      assistantReplySource: m['assistantReplySource']?.toString(),
      assistantCorrectionStatus: m['assistantCorrectionStatus']?.toString(),
      replyCount: (m['replyCount'] as num?)?.toInt() ?? 0,
      replyPreview: _commentMapList(m['replyPreview'])
          .map(CommentDto.fromMap)
          .toList(growable: false),
      replyNextCursor: m['replyNextCursor']?.toString(),
      postSummary: _commentMap(m['postSummary']),
      likeCount: (m['likeCount'] as num?)?.toInt() ?? 0,
      dislikeCount: (m['dislikeCount'] as num?)?.toInt() ?? 0,
      viewerReaction: (m['viewerReaction'] ?? 'none').toString(),
      recommendedScore: (m['recommendedScore'] as num?)?.toDouble(),
      status: (m['status'] ?? 'visible').toString(),
      isAuthor: m['isAuthor'] == true,
      canDelete: m['canDelete'] == true,
      canReply: m['canReply'] != false,
      canReport: m['canReport'] != false,
      personaContextVersion: (m['personaContextVersion'] as num?)?.toInt(),
      createdAt:
          DateTime.tryParse(m['createdAt']?.toString() ?? '') ?? DateTime.now(),
    );
  }

  CloudJsonMap toMap() => {
        'id': id,
        'postId': postId,
        'authorId': authorId,
        'displayName': displayName,
        'authorDisplayNameSnapshot': displayName,
        'avatarUrl': avatarUrl,
        'authorAvatarUrlSnapshot': avatarUrl,
        'content': content,
        'replyToCommentId': replyToCommentId,
        'replyToUserId': replyToUserId,
        'replyToDisplayName': replyToDisplayName,
        'parentCommentId': parentCommentId,
        'attachmentMediaIds': attachmentMediaIds,
        'attachments': attachments,
        'mentions': mentions,
        'entityRefs': entityRefs,
        'primaryHomepageId': primaryHomepageId,
        'canonicalEntityId': canonicalEntityId,
        'assistantMentioned': assistantMentioned,
        'assistantReplySource': assistantReplySource,
        'assistantCorrectionStatus': assistantCorrectionStatus,
        'replyCount': replyCount,
        'replyPreview': replyPreview.map((e) => e.toMap()).toList(growable: false),
        'replyNextCursor': replyNextCursor,
        'postSummary': postSummary,
        'likeCount': likeCount,
        'dislikeCount': dislikeCount,
        'viewerReaction': viewerReaction,
        'recommendedScore': recommendedScore,
        'status': status,
        'isAuthor': isAuthor,
        'canDelete': canDelete,
        'canReply': canReply,
        'canReport': canReport,
        if (personaContextVersion != null)
          'personaContextVersion': personaContextVersion,
        'createdAt': createdAt.toIso8601String(),
      };

  CommentDto copyWith({
    int? replyCount,
    List<CommentDto>? replyPreview,
    String? Function()? replyNextCursor,
    CloudJsonMap? postSummary,
    int? likeCount,
    int? dislikeCount,
    String? viewerReaction,
    String? status,
  }) {
    return CommentDto(
      id: id,
      postId: postId,
      authorId: authorId,
      displayName: displayName,
      avatarUrl: avatarUrl,
      content: content,
      replyToCommentId: replyToCommentId,
      replyToUserId: replyToUserId,
      replyToDisplayName: replyToDisplayName,
      parentCommentId: parentCommentId,
      attachmentMediaIds: attachmentMediaIds,
      attachments: attachments,
      mentions: mentions,
      entityRefs: entityRefs,
      primaryHomepageId: primaryHomepageId,
      canonicalEntityId: canonicalEntityId,
      assistantMentioned: assistantMentioned,
      assistantReplySource: assistantReplySource,
      assistantCorrectionStatus: assistantCorrectionStatus,
      replyCount: replyCount ?? this.replyCount,
      replyPreview: replyPreview ?? this.replyPreview,
      replyNextCursor:
          replyNextCursor != null ? replyNextCursor() : this.replyNextCursor,
      postSummary: postSummary ?? this.postSummary,
      likeCount: likeCount ?? this.likeCount,
      dislikeCount: dislikeCount ?? this.dislikeCount,
      viewerReaction: viewerReaction ?? this.viewerReaction,
      recommendedScore: recommendedScore,
      status: status ?? this.status,
      isAuthor: isAuthor,
      canDelete: canDelete,
      canReply: canReply,
      canReport: canReport,
      personaContextVersion: personaContextVersion,
      createdAt: createdAt,
    );
  }
}

List<String> _commentStringList(Object? raw) {
  final list = raw is List ? raw : const <Object?>[];
  return list.map((e) => e.toString()).toList(growable: false);
}

CloudJsonMap _commentMap(Object? raw) {
  if (raw is Map) {
    return Map<String, dynamic>.from(raw);
  }
  return const <String, dynamic>{};
}

List<CloudJsonMap> _commentMapList(Object? raw) {
  final list = raw is List ? raw : const <Object?>[];
  return list
      .whereType<Map>()
      .map((e) => Map<String, dynamic>.from(e))
      .toList(growable: false);
}
