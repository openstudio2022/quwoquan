/// User 设置聚合的端侧应用模型。
///
/// 该类型不冒充 generated wire contract；Remote adapter 负责把各设置 operation
/// 的响应映射到此模型，后续按 notification/privacy/call projection 分别收敛。
final class UserSettingModel {
  const UserSettingModel({
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

  factory UserSettingModel.fromWire(Map<String, dynamic> wire) {
    return UserSettingModel(
      userId: wire['userId'] as String? ?? '',
      enablePush: wire['enablePush'] as bool? ?? true,
      enableMarketing: wire['enableMarketing'] as bool? ?? false,
      quietHoursStart: wire['quietHoursStart'] as String?,
      quietHoursEnd: wire['quietHoursEnd'] as String?,
      allowStrangerMsg: wire['allowStrangerMsg'] as bool? ?? true,
      profileVisibility: wire['profileVisibility'] as String? ?? 'public',
      contentLanguage: wire['contentLanguage'] as String?,
      feedPreference: wire['feedPreference'] as String?,
      assistantEnabled: wire['assistantEnabled'] as bool? ?? true,
      updatedAt: wire['updatedAt'] as String? ?? '',
    );
  }
}
