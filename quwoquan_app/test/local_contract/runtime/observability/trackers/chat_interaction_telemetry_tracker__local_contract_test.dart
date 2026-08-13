import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/observability/trackers/chat_interaction_telemetry_tracker.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';

void main() {
  test('群聊漏斗只记录 metadata 枚举与低基数分桶', () async {
    final recorder = RecordingAppTelemetryRecorder();
    final tracker = ChatInteractionTelemetryTracker(
      telemetryReporter: recorder,
    );

    await tracker.track(
      action: ChatInteractionAction.groupGovernance,
      outcome: ChatInteractionOutcome.succeeded,
      source: ChatInteractionSource.settings,
      mentionScope: ChatMentionScope.none,
      governanceAction: ChatGovernanceAction.ownershipTransfer,
      watermarkResult: ChatWatermarkResult.none,
      memberCount: 501,
      unreadCount: 6,
      pageName: 'chat_transfer_ownership',
      surfaceId: 'chatTransferOwnership',
      duration: const Duration(milliseconds: 240),
    );

    expect(recorder.recorded, hasLength(1));
    final recorded = recorder.recorded.single;
    expect(recorded.pageName, 'chat_transfer_ownership');
    expect(recorded.eventType, 'chat_interaction_outcome');
    expect(recorded.extensions, <String, Object?>{
      'chatAction': 'group_governance',
      'chatOutcome': 'succeeded',
      'chatSource': 'settings',
      'mentionScope': 'none',
      'governanceAction': 'ownership_transfer',
      'watermarkResult': 'none',
      'memberCountBucket': 'five_hundred_one_to_one_thousand',
      'unreadCountBucket': 'six_to_fifty',
      'surfaceId': 'chatTransferOwnership',
      'durationMs': 240,
    });
    expect(recorded.extensions.keys, isNot(contains('conversationId')));
    expect(recorded.extensions.keys, isNot(contains('messageId')));
    expect(recorded.extensions.keys, isNot(contains('userId')));
  });

  test('失败结局从 error 派生 failReasonCode 与 recoveryAction', () async {
    final recorder = RecordingAppTelemetryRecorder();
    final tracker = ChatInteractionTelemetryTracker(
      telemetryReporter: recorder,
    );

    await tracker.track(
      action: ChatInteractionAction.groupCreate,
      outcome: ChatInteractionOutcome.failed,
      pageName: 'chat_group_create',
      surfaceId: 'chatGroupCreate',
      memberCount: 1,
      error: const RuntimeFailure(
        code: 'CHAT.SYSTEM.conversation_store_unavailable',
        origin: RuntimeFailureOrigin.remoteDependency,
        kind: RuntimeFailureKind.unavailable,
        nature: RuntimeFailureNature.transient,
        location: RuntimeFailureLocation(
          businessObject: 'chat.conversation',
          functionModule: 'create_group',
        ),
        context: RuntimeFailureContext(),
        recovery: RuntimeRecoveryDirective(
          action: 'retry',
          disruptionLevel: 'surface',
        ),
      ),
    );

    final recorded = recorder.recorded.single;
    expect(recorded.extensions['chatOutcome'], 'failed');
    expect(
      recorded.extensions['failReasonCode'],
      'CHAT.SYSTEM.conversation_store_unavailable',
    );
    expect(recorded.extensions['recoveryAction'], 'retry');
    expect(recorded.extensions['memberCountBucket'], 'one');
  });

  test('计数分桶覆盖边界且 recorder 抛错不外溢', () async {
    final failing = RecordingAppTelemetryRecorder(
      recordError: StateError('outbox unavailable'),
    );
    await expectLater(
      ChatInteractionTelemetryTracker(telemetryReporter: failing).track(
        action: ChatInteractionAction.mentionSend,
        outcome: ChatInteractionOutcome.succeeded,
        pageName: 'chat_detail',
        surfaceId: 'chatDetail',
      ),
      completes,
    );

    final recorder = RecordingAppTelemetryRecorder();
    final tracker = ChatInteractionTelemetryTracker(
      telemetryReporter: recorder,
    );
    for (final entry in <int, String>{
      0: 'zero',
      1: 'one',
      5: 'two_to_five',
      50: 'six_to_fifty',
      500: 'fifty_one_to_five_hundred',
      501: 'five_hundred_one_to_one_thousand',
    }.entries) {
      await tracker.track(
        action: ChatInteractionAction.mentionSend,
        outcome: ChatInteractionOutcome.succeeded,
        pageName: 'chat_detail',
        surfaceId: 'chatDetail',
        unreadCount: entry.key,
      );
      expect(
        recorder.recorded.last.extensions['unreadCountBucket'],
        entry.value,
        reason: 'unreadCount=${entry.key}',
      );
    }
  });
}
