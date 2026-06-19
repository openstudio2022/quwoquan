package main

// Wire DTOs derived from contracts/metadata/content (fields.yaml entities + report request shape).
// Kept as explicit templates so wire alias rules stay readable; header cites SSOT.

func renderCommentDtoDart() string {
	return `// GENERATED FILE — DO NOT EDIT BY HAND.
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
`
}

func renderPostSearchItemViewDtoDart() string {
	return `// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: contracts/metadata/content/post/fields.yaml (entities.PostSearchItemView)
// plus wire aliases (id/_id, type, summary/body, avatar snapshots, etc.).
// Regenerate: make codegen-app

import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';

class PostSearchItemView {
  const PostSearchItemView({
    required this.postId,
    required this.contentType,
    this.contentIdentity,
    this.title,
    this.summary,
    this.coverUrl,
    this.authorId,
    this.authorDisplayName,
    this.authorAvatarUrl,
    this.circleId,
    this.circleName,
    this.categoryId,
    this.subCategory,
    this.likeCount = 0,
    this.highlightText,
    this.matchedField,
    this.publishedAt,
    this.connectionState = 'unconnected',
    this.intersectionReason,
  });

  final String postId;
  final String contentType;
  final String? contentIdentity;
  final String? title;
  final String? summary;
  final String? coverUrl;
  final String? authorId;
  final String? authorDisplayName;
  final String? authorAvatarUrl;
  final String? circleId;
  final String? circleName;
  final String? categoryId;
  final String? subCategory;
  final int likeCount;
  final String? highlightText;
  final String? matchedField;
  final DateTime? publishedAt;
  final String connectionState;
  final IntersectionReason? intersectionReason;

  factory PostSearchItemView.fromMap(CloudJsonMap map) {
    final rawReason = map['intersectionReason'];
    IntersectionReason? parsedReason;
    if (rawReason is Map) {
      parsedReason = IntersectionReason.fromMap(
        Map<String, dynamic>.from(rawReason),
      );
    }
    return PostSearchItemView(
      postId: (map['postId'] ?? map['id'] ?? map['_id'] ?? '')
          .toString()
          .trim(),
      contentType: (map['contentType'] ?? map['type'] ?? 'image')
          .toString()
          .trim(),
      contentIdentity: map['contentIdentity']?.toString(),
      title: map['title']?.toString(),
      summary: (map['summary'] ?? map['body'] ?? map['highlightText'])
          ?.toString(),
      coverUrl: (map['coverUrl'] ?? map['thumbnailUrl'])?.toString(),
      authorId: (map['authorId'] ?? map['subAccountId'])?.toString(),
      authorDisplayName:
          (map['authorDisplayName'] ??
                  map['authorDisplayNameSnapshot'] ??
                  map['displayName'])
              ?.toString(),
      authorAvatarUrl:
          (map['authorAvatarUrl'] ??
                  map['authorAvatarUrlSnapshot'] ??
                  map['avatarUrl'])
              ?.toString(),
      circleId: map['circleId']?.toString(),
      circleName: map['circleName']?.toString(),
      categoryId: map['categoryId']?.toString(),
      subCategory: map['subCategory']?.toString(),
      likeCount: _postSearchWireParseInt(map['likeCount']) ?? 0,
      highlightText: map['highlightText']?.toString(),
      matchedField: map['matchedField']?.toString(),
      publishedAt: _postSearchWireParseDateTime(map['publishedAt']),
      connectionState:
          (map['connectionState'] ?? 'unconnected').toString().trim(),
      intersectionReason: parsedReason,
    );
  }
}

DateTime? _postSearchWireParseDateTime(Object? value) {
  if (value == null) return null;
  if (value is DateTime) return value;
  final s = value.toString();
  if (s.isEmpty) return null;
  return DateTime.tryParse(s);
}

int? _postSearchWireParseInt(Object? value) {
  if (value == null) return null;
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString());
}
`
}

func renderCreateReportRequestWireDart() string {
	return `// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: contracts/metadata/content/report/fields.yaml (CreateReport API body keys)
// aligned with ContentApiMetadata.createReportPath payload.
// Regenerate: make codegen-app

import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';

class CreateReportRequestWire {
  const CreateReportRequestWire({
    required this.targetId,
    required this.targetType,
    required this.reason,
    this.description,
  });

  final String targetId;
  final String targetType;
  final String reason;
  final String? description;

  CloudJsonMap toMap() => <String, dynamic>{
        'targetId': targetId,
        'targetType': targetType,
        'reason': reason,
        if (description != null && description!.isNotEmpty)
          'description': description,
      };
}
`
}
