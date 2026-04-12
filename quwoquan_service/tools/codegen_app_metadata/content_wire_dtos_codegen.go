package main

// Wire DTOs derived from contracts/metadata/content (fields.yaml entities + report request shape).
// Kept as explicit templates so wire alias rules stay readable; header cites SSOT.

func renderCommentDtoDart() string {
	return `// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: contracts/metadata/content/post/fields.yaml (entities.Comment)
// plus wire aliases for API/Mock payloads (profileSubjectId, displayName, etc.).
// Regenerate: make codegen-app

import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';

class CommentDto {
  const CommentDto({
    required this.id,
    required this.postId,
    required this.authorId,
    this.personaId,
    this.displayName,
    this.avatarUrl,
    required this.content,
    this.replyToCommentId,
    this.replyToUserId,
    this.replyToDisplayName,
    this.replyCount = 0,
    this.likeCount = 0,
    this.status = 'visible',
    this.isAuthor = false,
    this.personaContextVersion,
    required this.createdAt,
  });

  final String id;
  final String postId;
  final String authorId;
  final String? personaId;
  final String? displayName;
  final String? avatarUrl;
  final String content;
  final String? replyToCommentId;
  final String? replyToUserId;
  final String? replyToDisplayName;
  final int replyCount;
  final int likeCount;
  final String status;
  final bool isAuthor;
  final int? personaContextVersion;
  final DateTime createdAt;

  factory CommentDto.fromMap(CloudJsonMap m) {
    return CommentDto(
      id: (m['_id'] ?? m['id'] ?? '').toString(),
      postId: (m['postId'] ?? '').toString(),
      authorId: (m['profileSubjectId'] ?? m['authorId'] ?? '').toString(),
      personaId: (m['personaId'] ?? m['subAccountId'])?.toString(),
      displayName: (m['authorDisplayNameSnapshot'] ?? m['displayName'])
          ?.toString(),
      avatarUrl: (m['authorAvatarUrlSnapshot'] ?? m['avatarUrl'])?.toString(),
      content: (m['content'] ?? '').toString(),
      replyToCommentId: m['replyToCommentId']?.toString(),
      replyToUserId: m['replyToUserId']?.toString(),
      replyToDisplayName: m['replyToDisplayName']?.toString(),
      replyCount: (m['replyCount'] as num?)?.toInt() ?? 0,
      likeCount: (m['likeCount'] as num?)?.toInt() ?? 0,
      status: (m['status'] ?? 'visible').toString(),
      isAuthor: m['isAuthor'] == true,
      personaContextVersion: (m['personaContextVersion'] as num?)?.toInt(),
      createdAt:
          DateTime.tryParse(m['createdAt']?.toString() ?? '') ?? DateTime.now(),
    );
  }

  CloudJsonMap toMap() => {
        'id': id,
        'postId': postId,
        'authorId': authorId,
        'profileSubjectId': authorId,
        'personaId': personaId,
        'displayName': displayName,
        'authorDisplayNameSnapshot': displayName,
        'avatarUrl': avatarUrl,
        'authorAvatarUrlSnapshot': avatarUrl,
        'content': content,
        'replyToCommentId': replyToCommentId,
        'replyToUserId': replyToUserId,
        'replyToDisplayName': replyToDisplayName,
        'replyCount': replyCount,
        'likeCount': likeCount,
        'status': status,
        'isAuthor': isAuthor,
        if (personaContextVersion != null)
          'personaContextVersion': personaContextVersion,
        'createdAt': createdAt.toIso8601String(),
      };

  CommentDto copyWith({int? replyCount, int? likeCount, String? status}) {
    return CommentDto(
      id: id,
      postId: postId,
      authorId: authorId,
      personaId: personaId,
      displayName: displayName,
      avatarUrl: avatarUrl,
      content: content,
      replyToCommentId: replyToCommentId,
      replyToUserId: replyToUserId,
      replyToDisplayName: replyToDisplayName,
      replyCount: replyCount ?? this.replyCount,
      likeCount: likeCount ?? this.likeCount,
      status: status ?? this.status,
      isAuthor: isAuthor,
      personaContextVersion: personaContextVersion,
      createdAt: createdAt,
    );
  }
}
`
}

func renderPostSearchItemViewDtoDart() string {
	return `// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: contracts/metadata/content/post/fields.yaml (entities.PostSearchItemView)
// plus wire aliases (id/_id, type, summary/body, avatar snapshots, etc.).
// Regenerate: make codegen-app

import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';

class PostSearchItemView {
  const PostSearchItemView({
    required this.postId,
    required this.contentType,
    this.contentIdentity,
    this.title,
    this.summary,
    this.coverUrl,
    this.authorProfileSubjectId,
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
  });

  final String postId;
  final String contentType;
  final String? contentIdentity;
  final String? title;
  final String? summary;
  final String? coverUrl;
  final String? authorProfileSubjectId;
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

  factory PostSearchItemView.fromMap(CloudJsonMap map) {
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
      authorProfileSubjectId:
          (map['authorProfileSubjectId'] ?? map['profileSubjectId'])
              ?.toString(),
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
