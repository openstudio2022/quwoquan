import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const int kAssistantSkillSubscriptionsDefaultLimit = 20;

/// SkillSubscription 的对象级 command/query facade。
abstract class AssistantSkillSubscriptionFacet {
  Future<List<SkillSubscriptionWire>> listSkillSubscriptions({
    int limit = kAssistantSkillSubscriptionsDefaultLimit,
    String status = '',
  });

  Future<SkillSubscriptionWire> getSkillSubscription({
    required String subscriptionId,
  });

  Future<SkillSubscriptionWire> createSkillSubscription({
    required String skillId,
    String domainId = 'assistant',
    List<String> tagRefs = const <String>[],
    required String rawText,
    List<String> queries = const <String>[],
    String cron = '0 8 * * *',
    String timezone = 'Asia/Shanghai',
    required String clientRequestId,
  });

  Future<SkillSubscriptionWire> updateSkillSubscriptionStatus({
    required String subscriptionId,
    required String status,
    required String clientRequestId,
  });
}
