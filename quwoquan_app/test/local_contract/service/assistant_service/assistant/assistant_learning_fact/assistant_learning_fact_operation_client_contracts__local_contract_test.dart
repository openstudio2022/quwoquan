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
              referralSource: 'assistant_session',
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

      final receipt = decodeAssistantLearningFactReceipt(<String, Object?>{
        'eventId': 'fact-1',
        'accepted': true,
        'deduplicated': false,
        'appendSequence': 7,
        'payloadDigest':
            '0000000000000000000000000000000000000000000000000000000000000000',
        'recordedAt': '2026-07-26T00:00:01Z',
      });
      expect(receipt.appendSequence, 7);
      expect(receipt.recordedAt, '2026-07-26T00:00:01Z');
    },
  );

  test('learning fact receipt rejects the retired event identity field', () {
    expect(
      () => decodeAssistantLearningFactReceipt(<String, Object?>{
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
}
