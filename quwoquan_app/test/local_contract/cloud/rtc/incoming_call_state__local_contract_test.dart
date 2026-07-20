import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('ringing payload paints first frame before GetCall completes', () {
    final query = _CallQuery();
    final container = ProviderContainer(
      overrides: [rtcCallQueryProvider.overrideWith((ref, surface) => query)],
    );
    addTearDown(container.dispose);

    container
        .read(callSessionProvider.notifier)
        .seedIncomingCall(
          callId: 'call-incoming',
          callType: 'video',
          initiatorId: 'persona-caller',
          callerName: '契约好友',
          callerAvatarUrl: 'https://cdn.example/avatar.png',
          conversationId: 'conversation-1',
          sourceLabel: '当前会话',
          trustRelation: 'known',
          expiresAt: '2026-07-19T23:59:59Z',
        );

    final state = container.read(callSessionProvider);
    expect(state.status, CallStatus.ringing);
    expect(state.session?.callId, 'call-incoming');
    expect(state.session?.initiatorId, 'persona-caller');
    expect(state.incomingPresentation?.displayName, '契约好友');
    expect(
      state.incomingPresentation?.avatarUrl,
      'https://cdn.example/avatar.png',
    );
  });

  test(
    'GetCall replaces transient roster while preserving presentation',
    () async {
      final query = _CallQuery();
      final container = ProviderContainer(
        overrides: [rtcCallQueryProvider.overrideWith((ref, surface) => query)],
      );
      addTearDown(container.dispose);
      final notifier = container.read(callSessionProvider.notifier);
      notifier.seedIncomingCall(
        callId: 'call-incoming',
        callType: 'audio',
        initiatorId: 'persona-caller',
        callerName: '契约好友',
      );

      await notifier.refreshIncomingCall('call-incoming');

      final state = container.read(callSessionProvider);
      expect(query.requestedCallId, 'call-incoming');
      expect(state.session?.roomId, 'rtc-room-call-incoming');
      expect(state.session?.participants, hasLength(2));
      expect(state.incomingPresentation?.displayName, '契约好友');
    },
  );

  test(
    'GetCall failure retains ringing first frame and exposes error',
    () async {
      final query = _CallQuery(fail: true);
      final container = ProviderContainer(
        overrides: [rtcCallQueryProvider.overrideWith((ref, surface) => query)],
      );
      addTearDown(container.dispose);
      final notifier = container.read(callSessionProvider.notifier);
      notifier.seedIncomingCall(
        callId: 'call-incoming',
        callType: 'audio',
        initiatorId: 'persona-caller',
        callerName: '契约好友',
      );

      await notifier.refreshIncomingCall('call-incoming');

      final state = container.read(callSessionProvider);
      expect(state.status, CallStatus.ringing);
      expect(state.session?.callId, 'call-incoming');
      expect(state.error, isNotEmpty);
    },
  );
}

final class _CallQuery implements CallQuery {
  _CallQuery({this.fail = false});

  final bool fail;
  String? requestedCallId;

  @override
  Future<CallSessionDto> getCall(RtcGetCallQuery query) async {
    requestedCallId = query.callId;
    if (fail) {
      throw StateError('fixture get call failed');
    }
    final now = DateTime.utc(2026, 7, 19);
    return CallSessionDto(
      callId: query.callId,
      callType: 'audio',
      status: 'ringing',
      initiatorId: 'persona-caller',
      roomId: 'rtc-room-${query.callId}',
      maxParticipants: 2,
      participantCount: 2,
      participants: <CallParticipantDto>[
        const CallParticipantDto(
          userId: 'persona-caller',
          role: 'initiator',
          status: 'ringing',
        ),
        const CallParticipantDto(
          userId: 'persona-current',
          role: 'invitee',
          status: 'ringing',
        ),
      ],
      createdAt: now,
      updatedAt: now,
    );
  }

  @override
  Future<RtcCallHistoryPage> listCalls(RtcListCallsQuery query) async =>
      const RtcCallHistoryPage(items: <CallSessionDto>[]);
}
