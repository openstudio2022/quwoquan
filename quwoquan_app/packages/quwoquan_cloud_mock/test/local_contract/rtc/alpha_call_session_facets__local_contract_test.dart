import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';
import 'package:test/test.dart';

void main() {
  group('AlphaRtcCallSessionFacets', () {
    late AlphaRtcCallSessionFacets facets;

    setUp(() {
      facets = AlphaRtcCallSessionFacets();
    });

    test('immutable bundle seeds voice and video sessions', () async {
      final page = await facets.listCalls(RtcListCallsQuery());

      expect(
        page.items.map((item) => item.callType),
        containsAll(<String>['audio', 'video']),
      );
      expect(page.items.map((item) => item.callId), everyElement(isNotEmpty));
      expect(
        page.items.map((item) => item.status),
        everyElement(
          isIn(<String>[
            'initiated',
            'ringing',
            'connecting',
            'in_call',
            'ended',
          ]),
        ),
      );
    });

    test(
      'lifecycle commands preserve typed response and livekit config',
      () async {
        final initiated = await facets.initiateCall(
          RtcInitiateCallCommand(
            callType: 'video',
            inviteeIds: const <String>['fixture_user_friend'],
            conversationId: 'fixture_conversation',
          ),
        );

        expect(initiated.session.status, 'ringing');
        expect(initiated.livekitUrl, isNotEmpty);
        final answered = await facets.answerCall(
          RtcCallIdCommand(callId: initiated.session.callId),
        );
        expect(answered.session.status, 'in_call');
        expect(answered.token, isNotEmpty);
      },
    );

    test(
      'participant and media facets update the same CallSession aggregate',
      () async {
        final initiated = await facets.initiateCall(
          RtcInitiateCallCommand(
            callType: 'audio',
            inviteeIds: const <String>['fixture_user_friend'],
          ),
        );
        final callId = initiated.session.callId;

        await facets.inviteToCall(
          RtcInviteToCallCommand(
            callId: callId,
            inviteeIds: const <String>['fixture_user_weekend_1'],
          ),
        );
        await facets.toggleMute(
          RtcToggleMuteCommand(callId: callId, muted: true),
        );
        final session = await facets.getCall(RtcGetCallQuery(callId: callId));

        expect(session.participants, hasLength(3));
        expect(
          session.participants
              .singleWhere((item) => item.userId == 'fixture_user_current')
              .isMuted,
          isTrue,
        );
      },
    );

    test('missing call fails instead of returning an unrelated fixture', () {
      expect(
        () => facets.getCall(RtcGetCallQuery(callId: 'missing')),
        throwsA(isA<StateError>()),
      );
    });
  });
}
