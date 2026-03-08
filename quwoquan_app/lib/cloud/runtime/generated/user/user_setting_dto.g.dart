// Code generated from contracts/metadata/user/user_profile/fields.yaml. DO NOT EDIT.

class UserSettingDto {
  final String userId;
  final bool enablePush;
  final bool enableMarketing;
  final String? quietHoursStart;
  final String? quietHoursEnd;
  final bool allowStrangerMsg;
  final String profileVisibility;
  final String? contentLanguage;
  final String? feedPreference;
  final bool assistantEnabled;
  final String updatedAt;

  const UserSettingDto({
    required this.userId,
    required this.enablePush,
    required this.enableMarketing,
    this.quietHoursStart,
    this.quietHoursEnd,
    required this.allowStrangerMsg,
    required this.profileVisibility,
    this.contentLanguage,
    this.feedPreference,
    required this.assistantEnabled,
    required this.updatedAt,
  });

  factory UserSettingDto.fromJson(Map<String, dynamic> json) {
    return UserSettingDto(
      userId: json['userId'] as String,
      enablePush: json['enablePush'] as bool? ?? true,
      enableMarketing: json['enableMarketing'] as bool? ?? false,
      quietHoursStart: json['quietHoursStart'] as String?,
      quietHoursEnd: json['quietHoursEnd'] as String?,
      allowStrangerMsg: json['allowStrangerMsg'] as bool? ?? true,
      profileVisibility: json['profileVisibility'] as String? ?? 'public',
      contentLanguage: json['contentLanguage'] as String?,
      feedPreference: json['feedPreference'] as String?,
      assistantEnabled: json['assistantEnabled'] as bool? ?? true,
      updatedAt: json['updatedAt'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() => {
        'userId': userId,
        'enablePush': enablePush,
        'enableMarketing': enableMarketing,
        'quietHoursStart': quietHoursStart,
        'quietHoursEnd': quietHoursEnd,
        'allowStrangerMsg': allowStrangerMsg,
        'profileVisibility': profileVisibility,
        'contentLanguage': contentLanguage,
        'feedPreference': feedPreference,
        'assistantEnabled': assistantEnabled,
        'updatedAt': updatedAt,
      };
}
