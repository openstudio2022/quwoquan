import 'package:quwoquan_app/service/assistant_service/assistant/skill_user_setting/application/skill_user_setting_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class InMemoryAssistantSkillUserSettingFacet
    implements AssistantSkillUserSettingFacet {
  final Map<String, SkillUserSetting> _settings = <String, SkillUserSetting>{};

  @override
  Future<List<SkillUserSetting>> listSkillUserSettings({
    int limit = kAssistantSkillUserSettingsDefaultLimit,
  }) async => _settings.values.take(limit).toList(growable: false);

  @override
  Future<SkillUserSetting> getSkillUserSetting({
    required String skillId,
  }) async {
    final setting = _settings[skillId];
    if (setting == null) throw StateError('skill user setting not found');
    return setting;
  }

  @override
  Future<PutSkillUserSettingReceipt> putSkillUserSetting({
    required String skillId,
    required SkillUserSettingStatus status,
    required Map<String, Object?> configurationData,
    required String configurationSchemaDigest,
    required SkillMemoryPolicy memoryPolicy,
    required List<String> connectorConnectionRefs,
    required int expectedRevision,
    required String clientRequestId,
  }) async {
    final current = _settings[skillId];
    if ((current?.revision ?? 0) != expectedRevision) {
      throw StateError('skill user setting revision conflict');
    }
    final now = DateTime.now().toUtc().toIso8601String();
    final next = SkillUserSetting(
      id: 'setting:$skillId',
      accountId: 'fixture_assistant',
      skillId: skillId,
      status: status,
      configurationData: Map<String, Object?>.unmodifiable(configurationData),
      configurationSchemaDigest: configurationSchemaDigest,
      memoryPolicy: memoryPolicy,
      connectorConnectionRefs: List<String>.unmodifiable(
        connectorConnectionRefs,
      ),
      revision: expectedRevision + 1,
      createdAt: current?.createdAt ?? now,
      updatedAt: now,
    );
    final changed = current?.status != next.status;
    _settings[skillId] = next;
    return PutSkillUserSettingReceipt(
      setting: next,
      changed: changed,
      replayed: false,
    );
  }
}
