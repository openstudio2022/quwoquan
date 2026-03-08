// Code generated from contracts/metadata/user. DO NOT EDIT.

class UserLifeItemDto {
  final String id;
  final String userId;
  final String category;
  final String title;
  final String? subtitle;
  final String? imageUrl;
  final String? refId;
  final int sortOrder;
  final String createdAt;
  final String updatedAt;

  const UserLifeItemDto({
    required this.id,
    required this.userId,
    required this.category,
    required this.title,
    this.subtitle,
    this.imageUrl,
    this.refId,
    required this.sortOrder,
    required this.createdAt,
    required this.updatedAt,
  });

  factory UserLifeItemDto.fromJson(Map<String, dynamic> json) {
    return UserLifeItemDto(
      id: json['id'] as String,
      userId: json['userId'] as String,
      category: json['category'] as String,
      title: json['title'] as String,
      subtitle: json['subtitle'] as String?,
      imageUrl: json['imageUrl'] as String?,
      refId: json['refId'] as String?,
      sortOrder: (json['sortOrder'] as num?)?.toInt() ?? 0,
      createdAt: json['createdAt'] as String? ?? '',
      updatedAt: json['updatedAt'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'userId': userId,
        'category': category,
        'title': title,
        'subtitle': subtitle,
        'imageUrl': imageUrl,
        'refId': refId,
        'sortOrder': sortOrder,
        'createdAt': createdAt,
        'updatedAt': updatedAt,
      };
}
