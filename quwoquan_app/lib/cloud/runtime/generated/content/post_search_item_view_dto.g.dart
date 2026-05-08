// GENERATED FILE — DO NOT EDIT BY HAND.
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
