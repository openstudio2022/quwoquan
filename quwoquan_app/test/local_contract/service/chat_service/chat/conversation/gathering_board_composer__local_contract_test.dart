// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-002
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/gathering_board_composer.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';

final class _RecordingChatReader implements GatheringBoardChatReader {
  _RecordingChatReader(this.slice);

  final GatheringBoardChatSlice slice;
  final List<String> conversationIds = <String>[];

  @override
  Future<GatheringBoardChatSlice> loadChat(String conversationId) async {
    conversationIds.add(conversationId);
    return slice;
  }
}

final class _RecordingCircleReader implements GatheringBoardCircleReader {
  _RecordingCircleReader(this.slice);

  final GatheringBoardCircleSlice slice;
  final List<String> gatheringIds = <String>[];

  @override
  Future<GatheringBoardCircleSlice> loadCircle(String gatheringId) async {
    gatheringIds.add(gatheringId);
    return slice;
  }
}

const _chat = GatheringBoardChatSlice(
  access: GatheringBoardChatAccessSummary(
    gatheringId: 'gathering-1',
    conversationId: 'conversation-1',
    accessMode: GatheringBoardAccessMode.active,
    viewerRole: 'participant',
    canPost: true,
    statusLabel: 'active',
  ),
);

const _circle = GatheringBoardCircleSlice(
  activity: GatheringBoardActivitySlice(
    gatheringId: 'gathering-1',
    title: 'Gathering',
    scheduleLabel: 'schedule',
    placeLabel: 'place',
  ),
  participation: GatheringBoardParticipationSlice(
    activeCount: 2,
    maxParticipants: 4,
    remainingSeats: 2,
    summaryLabel: '2/4',
  ),
  plan: GatheringBoardPlanSlice(
    capability: GatheringBoardCapabilitySummary(
      state: GatheringBoardCapabilityState.unavailable,
      summaryLabel: 'plan',
      unavailableReason:
          GatheringBoardCapabilityUnavailableReason.notConfigured,
    ),
  ),
  mapCapability: GatheringBoardCapabilitySummary(
    state: GatheringBoardCapabilityState.unavailable,
    summaryLabel: 'map',
    unavailableReason: GatheringBoardCapabilityUnavailableReason.notConfigured,
  ),
  calendarCapability: GatheringBoardCapabilitySummary(
    state: GatheringBoardCapabilityState.unavailable,
    summaryLabel: 'calendar',
    unavailableReason: GatheringBoardCapabilityUnavailableReason.notConfigured,
  ),
);

void main() {
  test(
    'conversation resolves canonical gathering before Circle read',
    () async {
      final chat = _RecordingChatReader(_chat);
      final circle = _RecordingCircleReader(_circle);
      final composer = GatheringBoardComposer(
        chatReader: chat,
        circleReader: circle,
      );

      final snapshot = await composer.load(
        GatheringBoardQueryRequest(conversationId: 'conversation-1'),
      );

      expect(chat.conversationIds, <String>['conversation-1']);
      expect(circle.gatheringIds, <String>['gathering-1']);
      expect(snapshot.activity.gatheringId, 'gathering-1');
      expect(snapshot.chat.access.conversationId, 'conversation-1');
    },
  );

  test(
    'chat conversation identity drift is rejected before Circle read',
    () async {
      final chat = _RecordingChatReader(
        GatheringBoardChatSlice(
          access: GatheringBoardChatAccessSummary(
            gatheringId: 'gathering-1',
            conversationId: 'conversation-other',
            accessMode: GatheringBoardAccessMode.active,
            viewerRole: 'participant',
            canPost: true,
            statusLabel: 'active',
          ),
        ),
      );
      final circle = _RecordingCircleReader(_circle);
      final composer = GatheringBoardComposer(
        chatReader: chat,
        circleReader: circle,
      );

      await expectLater(
        composer.load(
          GatheringBoardQueryRequest(conversationId: 'conversation-1'),
        ),
        throwsStateError,
      );
      expect(circle.gatheringIds, isEmpty);
    },
  );

  test('Circle gathering identity drift is rejected', () async {
    final circle = _RecordingCircleReader(
      GatheringBoardCircleSlice(
        activity: GatheringBoardActivitySlice(
          gatheringId: 'gathering-other',
          title: 'Gathering',
          scheduleLabel: 'schedule',
          placeLabel: 'place',
        ),
        participation: GatheringBoardParticipationSlice(
          activeCount: 2,
          maxParticipants: 4,
          remainingSeats: 2,
          summaryLabel: '2/4',
        ),
        plan: GatheringBoardPlanSlice(
          capability: GatheringBoardCapabilitySummary(
            state: GatheringBoardCapabilityState.unavailable,
            summaryLabel: 'plan',
          ),
        ),
        mapCapability: GatheringBoardCapabilitySummary(
          state: GatheringBoardCapabilityState.unavailable,
          summaryLabel: 'map',
        ),
        calendarCapability: GatheringBoardCapabilitySummary(
          state: GatheringBoardCapabilityState.unavailable,
          summaryLabel: 'calendar',
        ),
      ),
    );
    final composer = GatheringBoardComposer(
      chatReader: _RecordingChatReader(_chat),
      circleReader: circle,
    );

    await expectLater(
      composer.load(
        GatheringBoardQueryRequest(conversationId: 'conversation-1'),
      ),
      throwsStateError,
    );
    expect(circle.gatheringIds, <String>['gathering-1']);
  });
}
