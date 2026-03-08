// Code generated from contracts/metadata/user/user_profile/fields.yaml. DO NOT EDIT.

class PersonaDto {
  final String id;
  final String userId;
  final String displayName;
  final String? avatarUrl;
  final bool isPrimary;
  final bool isPrivate;
  final bool isActive;
  final String createdAt;
  final String updatedAt;

  const PersonaDto({
    required this.id,
    required this.userId,
    required this.displayName,
    this.avatarUrl,
    required this.isPrimary,
    required this.isPrivate,
    required this.isActive,
    required this.createdAt,
    required this.updatedAt,
  });

  factory PersonaDto.fromJson(Map<String, dynamic> json) {
    return PersonaDto(
      id: json['id'] as String,
      userId: json['userId'] as String,
      displayName: json['displayName'] as String,
      avatarUrl: json['avatarUrl'] as String?,
      isPrimary: json['isPrimary'] as bool? ?? false,
      isPrivate: json['isPrivate'] as bool? ?? false,
      isActive: json['isActive'] as bool? ?? false,
      createdAt: json['createdAt'] as String? ?? '',
      updatedAt: json['updatedAt'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'userId': userId,
        'displayName': displayName,
        'avatarUrl': avatarUrl,
        'isPrimary': isPrimary,
        'isPrivate': isPrivate,
        'isActive': isActive,
        'createdAt': createdAt,
        'updatedAt': updatedAt,
      };
}
