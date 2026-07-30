import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'learning fact client contract preserves identity and omits absent text',
    () {
      final payload =
          encodeAssistantAssistantLearningFactAppendAssistantLearningFactGeneratedRequest(
            AssistantLearningFactAppendCommand(
              eventId: 'fact-1',
              factType: 'user_feedback',
              assistantTurnId: 'turn-1',
              referralSource: 'assistant_conversation',
              domainId: 'assistant',
              feedbackType: 'useful',
              trainingEligible: false,
              occurredAt: DateTime.utc(2026, 7, 26),
            ),
          );

      final body = (payload.body! as Map).cast<String, Object?>();
      expect(body['eventId'], 'fact-1');
      expect(body['factType'], 'user_feedback');
      expect(body.containsKey('queryText'), isFalse);
      expect(body['occurredAt'], '2026-07-26T00:00:00.000Z');

      final receipt =
          decodeAssistantLearningFactAppendReceipt(<String, Object?>{
            'eventId': 'fact-1',
            'accepted': true,
            'deduplicated': false,
            'appendSequence': 7,
            'payloadDigest':
                '0000000000000000000000000000000000000000000000000000000000000000',
            'recordedAt': '2026-07-26T00:00:01Z',
          });
      expect(receipt.appendSequence, 7);
      expect(receipt.recordedAt, DateTime.utc(2026, 7, 26, 0, 0, 1));
    },
  );

  test('learning fact receipt rejects the retired event identity field', () {
    expect(
      () => decodeAssistantLearningFactAppendReceipt(<String, Object?>{
        'eventId': 'fact-1',
        // Retired eventVersion input must be rejected, never ignored.
        'eventVersion': 1,
        'accepted': true,
        'deduplicated': false,
        'appendSequence': 7,
        'payloadDigest':
            '0000000000000000000000000000000000000000000000000000000000000000',
        'recordedAt': '2026-07-26T00:00:01Z',
      }),
      throwsFormatException,
    );
  });

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
            searchQueryPlan: AssistantSkillSubscriptionSearchPlan(
              queries: const <String>['Shanghai travel'],
            ),
            trigger: AssistantSkillSubscriptionTrigger(cron: '0 8 * * *'),
            destination: AssistantSkillSubscriptionDestination(
              destinationType: 'user',
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
          ),
        );
    expect(update.pathParameters['subscriptionId'], 'subscription-1');
    expect((update.body! as Map)['status'], 'paused');
  });

  test(
    'skill subscription response decoder rejects weak or incomplete shapes',
    () {
      expect(
        () => decodeAssistantSkillSubscription(<String, Object?>{
          'subscriptionId': 'subscription-1',
        }),
        throwsFormatException,
      );
    },
  );

  test('skill catalog decoder exposes one strict client projection', () {
    final catalog = decodeAssistantSkillCatalogList(<String, Object?>{
      'items': <Object?>[
        <String, Object?>{
          'skillId': 'daily_assistant',
          'displayName': '每日助手',
          'description': '管理每日计划',
          'category': 'life',
          'requiresConsent': false,
          'iconHint': 'checkmark',
        },
      ],
    });

    expect(catalog.items.single.skillId, 'daily_assistant');
    expect(catalog.items.single.requiresConsent, isFalse);
    expect(
      () => decodeAssistantSkillCatalogList(<String, Object?>{
        'items': <Object?>[
          <String, Object?>{
            'skillId': 'daily_assistant',
            'displayName': '每日助手',
          },
        ],
      }),
      throwsFormatException,
    );
  });
}
