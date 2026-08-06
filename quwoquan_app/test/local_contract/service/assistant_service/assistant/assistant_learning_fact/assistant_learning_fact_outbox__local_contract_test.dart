// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/learning-event-ingestion/spec.md#gwt-001
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_learning_fact/application/assistant_learning_fact_append_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_learning_fact/application/assistant_learning_fact_outbox.dart';
import 'package:quwoquan_app/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/runtime/transport/actor_queue/actor_queue_storage.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  late Directory tempDirectory;
  late ActorQueueStorage storage;
  late ActorQueuePartition partition;

  setUp(() async {
    tempDirectory = await Directory.systemTemp.createTemp(
      'assistant_learning_fact_outbox_test_',
    );
    Hive.init(tempDirectory.path);
    storage = ActorQueueStorage(keyStore: _MemoryActorQueueKeyStore());
    partition = ActorQueuePartition(
      environment: 'gamma',
      accountId: 'account-1',
      personaId: 'persona-1',
      deviceId: 'device-1',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
    if (await tempDirectory.exists()) {
      await tempDirectory.delete(recursive: true);
    }
  });

  test('restart retains a fact until the exact receipt is confirmed', () async {
    final unavailable = _LearningFactRemote(available: false);
    final first = AssistantLearningFactOutbox(partition, storage, unavailable);
    final fact = _fact();

    expect(await first.enqueue(fact), isTrue);
    await first.flush();
    expect(await first.pendingCount(), 1);

    final recoveredRemote = _LearningFactRemote(available: true);
    final recovered = AssistantLearningFactOutbox(
      partition,
      storage,
      recoveredRemote,
    );
    await recovered.flush();

    expect(recoveredRemote.requests, hasLength(1));
    expect(recoveredRemote.requests.single.eventId, fact.eventId);
    expect(await recovered.pendingCount(), 0);
  });

  test('receipt identity mismatch moves poison record to DLQ', () async {
    final remote = _LearningFactRemote(
      available: true,
      receiptEventId: 'different-event',
    );
    final outbox = AssistantLearningFactOutbox(partition, storage, remote);
    await outbox.enqueue(_fact());

    await outbox.flush();

    expect(await outbox.pendingCount(), 0);
    final dlq = await storage.open(
      partition,
      '${kAssistantLearningFactOutboxName}_dlq',
    );
    expect(dlq, isNotNull);
    expect(dlq, hasLength(1));
  });

  test(
    'same identity with a different payload cannot overwrite pending fact',
    () async {
      final remote = _LearningFactRemote(available: true);
      final outbox = AssistantLearningFactOutbox(partition, storage, remote);

      expect(await outbox.enqueue(_fact()), isTrue);
      expect(await outbox.enqueue(_fact(feedbackScore: -1)), isFalse);
      await outbox.flush();

      expect(remote.requests, hasLength(1));
      expect(remote.requests.single.feedbackScore, 1);
    },
  );
}

AssistantLearningFactAppendCommand _fact({double feedbackScore = 1}) =>
    AssistantLearningFactAppendCommand(
      eventId: 'feedback:turn-1:useful',
      factType: AssistantLearningFactType.userFeedback.wireName,
      assistantTurnId: 'turn-1',
      referralSource: AssistantReferralSource.assistantSession.wireName,
      domainId: 'assistant',
      feedbackType: FeedbackType.useful.wireName,
      feedbackScore: feedbackScore,
      trainingEligible: false,
      occurredAt: DateTime.utc(2026, 7, 26),
    );

final class _LearningFactRemote implements AssistantLearningFactAppendFacet {
  _LearningFactRemote({required this.available, this.receiptEventId});

  final bool available;
  final String? receiptEventId;
  final List<AssistantLearningFactAppendCommand> requests =
      <AssistantLearningFactAppendCommand>[];

  @override
  Future<AssistantLearningFactReceipt> appendUserFact({
    required AssistantLearningFactAppendCommand request,
  }) async {
    if (!available) {
      throw StateError('network unavailable');
    }
    requests.add(request);
    return AssistantLearningFactReceipt(
      eventId: receiptEventId ?? request.eventId,
      accepted: true,
      deduplicated: false,
      appendSequence: 1,
      payloadDigest:
          '0000000000000000000000000000000000000000000000000000000000000000',
      recordedAt: DateTime.utc(2026, 7, 26).toIso8601String(),
    );
  }
}

final class _MemoryActorQueueKeyStore implements ActorQueueEncryptionKeyStore {
  final Map<String, String> values = <String, String>{};

  @override
  Future<void> delete(String key) async {
    values.remove(key);
  }

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String value) async {
    values[key] = value;
  }
}
