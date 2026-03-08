// Code generated from contracts/metadata/user. DO NOT EDIT.

class UserWorkDto {
  final String id;
  final String userId;
  final String title;
  final String? coverUrl;
  final String workType;
  final String? refId;
  final int sortOrder;
  final String createdAt;
  final String updatedAt;

  const UserWorkDto({
    required this.id,
    required this.userId,
    required this.title,
    this.coverUrl,
    required this.workType,
    this.refId,
    required this.sortOrder,
    required this.createdAt,
    required this.updatedAt,
  });

  factory UserWorkDto.fromJson(Map<String, dynamic> json) {
    return UserWorkDto(
      id: json['id'] as String,
      userId: json['userId'] as String,
      title: json['title'] as String,
      coverUrl: json['coverUrl'] as String?,
      workType: json['workType'] as String,
      refId: json['refId'] as String?,
      sortOrder: (json['sortOrder'] as num?)?.toInt() ?? 0,
      createdAt: json['createdAt'] as String? ?? '',
      updatedAt: json['updatedAt'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'userId': userId,
        'title': title,
        'coverUrl': coverUrl,
        'workType': workType,
        'refId': refId,
        'sortOrder': sortOrder,
        'createdAt': createdAt,
        'updatedAt': updatedAt,
      };
}
