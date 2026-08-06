import 'package:quwoquan_app/assistant/assistant/skill_activity_view/application/skill_activity_query.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// SkillActivityView 的 production generated-client query adapter。
///
/// 身份与授权只来自 [CloudOperationInvocationContext]；App 不读取响应中的
/// owner/raw run reference，也不根据 sourceObjectRef 动态调用 operation。
final class RemoteAssistantSkillActivityAdapter
    implements AssistantSkillActivityQuery {
  const RemoteAssistantSkillActivityAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final CloudOperationInvocationContext Function(String clientPageId)
  invocationContext;

  @override
  Future<SkillActivitySlice> listSkillActivities({
    required String skillId,
    String cursor = '',
    int limit = kAssistantSkillActivityDefaultLimit,
  }) {
    return client.assistantSkillActivityViewListSkillActivities(
      ListSkillActivitiesQuery(
        skillId: skillId,
        cursor: cursor.isEmpty ? null : cursor,
        limit: limit,
      ),
      context: invocationContext(AssistantRequestPageIds.listSkillActivities),
    );
  }
}
