import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const int kAssistantSkillUserSettingsDefaultLimit = 64;

/// SkillUserSetting 的对象级 command/query facade。
abstract class AssistantSkillUserSettingFacet {
  Future<List<SkillUserSetting>> listSkillUserSettings({
    int limit = kAssistantSkillUserSettingsDefaultLimit,
  });

  Future<SkillUserSetting> getSkillUserSetting({required String skillId});

  Future<PutSkillUserSettingReceipt> putSkillUserSetting({
    required String skillId,
    required SkillUserSettingStatus status,
    required Map<String, Object?> configurationData,
    required String configurationSchemaDigest,
    required SkillMemoryPolicy memoryPolicy,
    required List<String> connectorConnectionRefs,
    required int expectedRevision,
    required String clientRequestId,
  });
}
