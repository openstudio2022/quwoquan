import 'package:quwoquan_app/assistant/assistant/assistant_learning_fact/adapters/assistant_learning_fact_remote.dart';
import 'package:quwoquan_app/assistant/assistant/skill_activity_view/adapters/skill_activity_remote.dart';
import 'package:quwoquan_app/assistant/assistant/skill_catalog/adapters/skill_catalog_remote.dart';
import 'package:quwoquan_app/assistant/assistant/skill_consent/adapters/skill_consent_remote.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_consent_store.dart';
import 'package:quwoquan_app/assistant/assistant/skill_data_control_request/adapters/skill_data_control_remote.dart';
import 'package:quwoquan_app/assistant/assistant/skill_subscription/adapters/skill_subscription_remote.dart';
import 'package:quwoquan_app/assistant/assistant/skill_user_setting/adapters/skill_user_setting_remote.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// assistant domain 的 production Remote adapter 种类。
///
/// 只有本文件可以命名 `Remote*` 实现；Provider 侧只声明 typed port 泛型。
enum AssistantProductionAdapter {
  learningFactAppend,
  skillActivity,
  skillCatalog,
  skillConsent,
  skillDataControl,
  skillSubscription,
  skillUserSetting,
}

/// assistant domain 的唯一 production 装配入口。
final class AssistantProductionComposition {
  const AssistantProductionComposition._();

  /// skill_consent 的 production 形态是「Remote + 成功态本地快照装饰器」。
  ///
  /// 快照只在写成功后落盘，用于离线只读回显；它不是 fallback，Remote 失败仍向上
  /// 抛结构化失败，不会用快照伪造成功。
  static AssistantSkillConsentFacet skillConsentFacet({
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
    required String accountId,
  }) {
    return AssistantConsentStore.decorateRemoteSuccess(
      accountId: accountId,
      remote: generatedAdapter<AssistantSkillConsentFacet>(
        AssistantProductionAdapter.skillConsent,
        client: client,
        invocationContext: invocationContext,
      ),
    );
  }

  static T generatedAdapter<T>(
    AssistantProductionAdapter adapter, {
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    final dynamic context = invocationContext;
    final Object result = switch (adapter) {
      AssistantProductionAdapter.learningFactAppend =>
        RemoteAssistantLearningFactAppendAdapter(
          client: client,
          invocationContext: context,
        ),
      AssistantProductionAdapter.skillActivity =>
        RemoteAssistantSkillActivityAdapter(
          client: client,
          invocationContext: context,
        ),
      AssistantProductionAdapter.skillCatalog =>
        RemoteAssistantSkillCatalogAdapter(
          client: client,
          invocationContext: context,
        ),
      AssistantProductionAdapter.skillConsent =>
        RemoteAssistantSkillConsentAdapter(
          client: client,
          invocationContext: context,
        ),
      AssistantProductionAdapter.skillDataControl =>
        RemoteAssistantSkillDataControlAdapter(
          client: client,
          invocationContext: context,
        ),
      AssistantProductionAdapter.skillSubscription =>
        RemoteAssistantSkillSubscriptionAdapter(
          client: client,
          invocationContext: context,
        ),
      AssistantProductionAdapter.skillUserSetting =>
        RemoteAssistantSkillUserSettingAdapter(
          client: client,
          invocationContext: context,
        ),
    };
    return result as T;
  }
}
