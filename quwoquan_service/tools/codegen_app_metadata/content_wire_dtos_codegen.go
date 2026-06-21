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
    this.ipLocation,
    required this.content,
    this.replyToCommentId,
    this.replyToUserId,
    this.replyToDisplayName,
    this.parentCommentId,
    this.attachmentMediaIds = const <String>[],
    this.attachments = const <CommentAttachmentDto>[],
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
    this.authorLiked = false,
    this.recommendedScore,
    this.status = 'visible',
    this.isPinned = false,
    this.pinnedAt,
    this.isAuthor = false,
    this.canDelete = false,
    this.canReply = true,
    this.canReport = true,
    this.canPin = false,
    this.personaContextVersion,
    required this.createdAt,
    this.deletedAt,
  });

  final String id;
  final String postId;
  final String authorId;
  final String? displayName;
  final String? avatarUrl;
  final String? ipLocation;
  final String content;
  final String? replyToCommentId;
  final String? replyToUserId;
  final String? replyToDisplayName;
  final String? parentCommentId;
  final List<String> attachmentMediaIds;
  final List<CommentAttachmentDto> attachments;
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
  final bool authorLiked;
  final double? recommendedScore;
  final String status;
  final bool isPinned;
  final DateTime? pinnedAt;
  final bool isAuthor;
  final bool canDelete;
  final bool canReply;
  final bool canReport;
  final bool canPin;
  final int? personaContextVersion;
  final DateTime createdAt;
  // 软删落时间戳：status=deleted 时由服务端 projection 输出 RFC3339，否则为 null。
  // 支撑端侧基于 GetCommentCountsDelta 的「此期间删除 M」可解释增量。
  final DateTime? deletedAt;

  factory CommentDto.fromMap(CloudJsonMap m) {
    return CommentDto(
      id: (m['_id'] ?? m['id'] ?? '').toString(),
      postId: (m['postId'] ?? '').toString(),
      authorId: (m['authorId'] ?? m['subAccountId'] ?? '').toString(),
      displayName: (m['authorDisplayNameSnapshot'] ?? m['displayName'])
          ?.toString(),
      avatarUrl: (m['authorAvatarUrlSnapshot'] ?? m['avatarUrl'])?.toString(),
      ipLocation: m['ipLocation']?.toString(),
      content: (m['content'] ?? '').toString(),
      replyToCommentId: m['replyToCommentId']?.toString(),
      replyToUserId: m['replyToUserId']?.toString(),
      replyToDisplayName: m['replyToDisplayName']?.toString(),
      parentCommentId: m['parentCommentId']?.toString(),
      attachmentMediaIds: _commentStringList(m['attachmentMediaIds']),
      attachments: _commentAttachmentList(m['attachments']),
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
      authorLiked: m['authorLiked'] == true,
      recommendedScore: (m['recommendedScore'] as num?)?.toDouble(),
      status: (m['status'] ?? 'visible').toString(),
      isPinned: m['isPinned'] == true,
      pinnedAt: DateTime.tryParse(m['pinnedAt']?.toString() ?? ''),
      isAuthor: m['isAuthor'] == true,
      canDelete: m['canDelete'] == true,
      canReply: m['canReply'] != false,
      canReport: m['canReport'] != false,
      canPin: m['canPin'] == true,
      personaContextVersion: (m['personaContextVersion'] as num?)?.toInt(),
      createdAt:
          DateTime.tryParse(m['createdAt']?.toString() ?? '') ?? DateTime.now(),
      deletedAt: DateTime.tryParse(m['deletedAt']?.toString() ?? ''),
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
        'ipLocation': ipLocation,
        'content': content,
        'replyToCommentId': replyToCommentId,
        'replyToUserId': replyToUserId,
        'replyToDisplayName': replyToDisplayName,
        'parentCommentId': parentCommentId,
        'attachmentMediaIds': attachmentMediaIds,
        'attachments':
            attachments.map((e) => e.toMap()).toList(growable: false),
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
        'authorLiked': authorLiked,
        'recommendedScore': recommendedScore,
        'status': status,
        'isPinned': isPinned,
        if (pinnedAt != null) 'pinnedAt': pinnedAt!.toIso8601String(),
        'isAuthor': isAuthor,
        'canDelete': canDelete,
        'canReply': canReply,
        'canReport': canReport,
        'canPin': canPin,
        if (personaContextVersion != null)
          'personaContextVersion': personaContextVersion,
        'createdAt': createdAt.toIso8601String(),
        if (deletedAt != null) 'deletedAt': deletedAt!.toIso8601String(),
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
    bool? isPinned,
    DateTime? Function()? pinnedAt,
    DateTime? Function()? deletedAt,
  }) {
    return CommentDto(
      id: id,
      postId: postId,
      authorId: authorId,
      displayName: displayName,
      avatarUrl: avatarUrl,
      ipLocation: ipLocation,
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
      authorLiked: authorLiked,
      recommendedScore: recommendedScore,
      status: status ?? this.status,
      isPinned: isPinned ?? this.isPinned,
      pinnedAt: pinnedAt != null ? pinnedAt() : this.pinnedAt,
      isAuthor: isAuthor,
      canDelete: canDelete,
      canReply: canReply,
      canReport: canReport,
      canPin: canPin,
      personaContextVersion: personaContextVersion,
      createdAt: createdAt,
      deletedAt: deletedAt != null ? deletedAt() : this.deletedAt,
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

/// 评论附件回显快照（contracts/metadata/content/post/fields.yaml entities.Comment.attachments）。
/// 形态 [{mediaId,type,url,thumbnailUrl,width,height,moderationStatus}]，
/// 类型化以消除消费端 Map 穿透。
class CommentAttachmentDto {
  const CommentAttachmentDto({
    required this.mediaId,
    this.type,
    this.url,
    this.thumbnailUrl,
    this.width,
    this.height,
    this.moderationStatus,
  });

  final String mediaId;
  final String? type;
  final String? url;
  final String? thumbnailUrl;
  final int? width;
  final int? height;
  final String? moderationStatus;

  /// 缩略图优先 thumbnailUrl，回退原图 url；二者皆空返回 null。
  String? get displayUrl {
    final thumb = thumbnailUrl;
    if (thumb != null && thumb.isNotEmpty) return thumb;
    final full = url;
    if (full != null && full.isNotEmpty) return full;
    return null;
  }

  /// 原始宽高比；任一缺失或非正返回 null（由消费端套用统一宽高比护栏）。
  double? get aspectRatio {
    final w = width;
    final h = height;
    if (w == null || h == null || w <= 0 || h <= 0) return null;
    return w / h;
  }

  factory CommentAttachmentDto.fromMap(CloudJsonMap m) {
    return CommentAttachmentDto(
      mediaId: (m['mediaId'] ?? m['id'] ?? '').toString(),
      type: m['type']?.toString(),
      url: m['url']?.toString(),
      thumbnailUrl: m['thumbnailUrl']?.toString(),
      width: (m['width'] as num?)?.toInt(),
      height: (m['height'] as num?)?.toInt(),
      moderationStatus: m['moderationStatus']?.toString(),
    );
  }

  CloudJsonMap toMap() => <String, dynamic>{
        'mediaId': mediaId,
        if (type != null) 'type': type,
        if (url != null) 'url': url,
        if (thumbnailUrl != null) 'thumbnailUrl': thumbnailUrl,
        if (width != null) 'width': width,
        if (height != null) 'height': height,
        if (moderationStatus != null) 'moderationStatus': moderationStatus,
      };
}

List<CommentAttachmentDto> _commentAttachmentList(Object? raw) {
  final list = raw is List ? raw : const <Object?>[];
  return list
      .whereType<Map>()
      .map((e) => CommentAttachmentDto.fromMap(Map<String, dynamic>.from(e)))
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
