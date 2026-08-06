import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('skill subscription client contracts encode path/query and typed body', () {
    final list =
        encodeAssistantSkillSubscriptionListSkillSubscriptionsGeneratedRequest(
          AssistantSkillSubscriptionListQuery(limit: 20, status: 'active'),
        );
    expect(list.queryParameters, <String, String>{
      'limit': '20',
      'status': 'active',
    });

    final create =
        encodeAssistantSkillSubscriptionCreateSkillSubscriptionGeneratedRequest(
          CreateAssistantSkillSubscriptionCommand(
            skillId: 'daily_digest',
            domainId: 'assistant',
            tagRefs: const <String>['travel'],
            searchQueryPlan: SkillSubscriptionSearchQueryPlanWire(
              queries: const <String>['Shanghai travel'],
            ),
            trigger: SkillSubscriptionTriggerWire(
              cron: '0 8 * * *',
              timezone: 'Asia/Shanghai',
            ),
            destination: SkillSubscriptionDestinationWire(
              destinationType: SkillSubscriptionDestinationType.user,
            ),
            clientRequestId: 'intent-1',
          ),
        );
    final body = (create.body! as Map).cast<String, Object?>();
    expect(body['clientRequestId'], 'intent-1');
    expect(body['tagRefs'], <String>['travel']);

    final update =
        encodeAssistantSkillSubscriptionUpdateSkillSubscriptionStatusGeneratedRequest(
          UpdateAssistantSkillSubscriptionStatusCommand(
            subscriptionId: 'subscription-1',
            status: 'paused',
            clientRequestId: 'intent-2',
          ),
        );
    expect(update.pathParameters['subscriptionId'], 'subscription-1');
    expect((update.body! as Map)['status'], 'paused');
  });

  test(
    'skill subscription response decoder rejects weak or incomplete shapes',
    () {
      expect(
        () => decodeSkillSubscriptionWire(<String, Object?>{
          'subscriptionId': 'subscription-1',
        }),
        throwsFormatException,
      );
    },
  );
}
