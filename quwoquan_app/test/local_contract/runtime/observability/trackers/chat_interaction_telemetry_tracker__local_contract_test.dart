import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/observability/trackers/chat_interaction_telemetry_tracker.dart';
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
}
