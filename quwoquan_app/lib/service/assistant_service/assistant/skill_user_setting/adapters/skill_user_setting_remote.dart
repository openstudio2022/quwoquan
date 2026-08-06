import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_user_setting/application/skill_user_setting_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AssistantSkillUserSettingInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
    });

/// SkillUserSetting 的 production generated-client adapter。
final class RemoteAssistantSkillUserSettingAdapter
    implements AssistantSkillUserSettingFacet {
  const RemoteAssistantSkillUserSettingAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AssistantSkillUserSettingInvocationContextFactory invocationContext;

  @override
  Future<List<SkillUserSetting>> listSkillUserSettings({
    int limit = kAssistantSkillUserSettingsDefaultLimit,
  }) async {
    final result = await client.assistantSkillUserSettingListSkillUserSettings(
      ListSkillUserSettingsQuery(limit: limit),
      context: invocationContext(AssistantRequestPageIds.listSkillUserSettings),
    );
    return result.items;
  }

  @override
  Future<SkillUserSetting> getSkillUserSetting({required String skillId}) {
    return client.assistantSkillUserSettingGetSkillUserSetting(
      GetSkillUserSettingQuery(skillId: skillId),
      context: invocationContext(AssistantRequestPageIds.getSkillUserSetting),
    );
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
  }) {
    return client.assistantSkillUserSettingPutSkillUserSetting(
      PutSkillUserSettingRequest(
        skillId: skillId,
        status: status,
        configurationData: configurationData,
        configurationSchemaDigest: configurationSchemaDigest,
        memoryPolicy: memoryPolicy,
        connectorConnectionRefs: connectorConnectionRefs,
        expectedRevision: expectedRevision,
      ),
      context: invocationContext(
        AssistantRequestPageIds.putSkillUserSetting,
        idempotencyKey: clientRequestId,
      ),
    );
  }
}
