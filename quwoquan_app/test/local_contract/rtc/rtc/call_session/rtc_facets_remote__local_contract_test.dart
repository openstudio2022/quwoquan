import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/rtc/rtc/call_session/adapters/call_lifecycle_remote.dart';
import 'package:quwoquan_app/rtc/rtc/call_session/adapters/call_media_control_remote.dart';
import 'package:quwoquan_app/rtc/rtc/call_session/adapters/call_participant_remote.dart';
import 'package:quwoquan_app/rtc/rtc/call_session/adapters/call_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('RTC generated Remote Facets', () {
    late _CapturingExecutor executor;
    late GeneratedCloudOperationClient client;

    setUp(() {
      executor = _CapturingExecutor();
      client = GeneratedCloudOperationClient(executor);
    });

    test('15 个 CallSession operation 对受控 Remote 验证均显式可执行', () {
      const operationIds = <String>[
        AppCloudOperationIds.rtcCallSessionInitiateCall,
        AppCloudOperationIds.rtcCallSessionAnswerCall,
        AppCloudOperationIds.rtcCallSessionRejectCall,
        AppCloudOperationIds.rtcCallSessionCancelCall,
        AppCloudOperationIds.rtcCallSessionHangupCall,
        AppCloudOperationIds.rtcCallSessionJoinCall,
        AppCloudOperationIds.rtcCallSessionLeaveCall,
        AppCloudOperationIds.rtcCallSessionReportMediaConnected,
        AppCloudOperationIds.rtcCallSessionInviteToCall,
        AppCloudOperationIds.rtcCallSessionGetCall,
        AppCloudOperationIds.rtcCallSessionListCalls,
        AppCloudOperationIds.rtcCallSessionToggleMute,
        AppCloudOperationIds.rtcCallSessionToggleCamera,
        AppCloudOperationIds.rtcCallSessionStartScreenShare,
        AppCloudOperationIds.rtcCallSessionStopScreenShare,
      ];

      for (final operationId in operationIds) {
        final contract = appCloudOperationContracts[operationId];
        expect(contract, isNotNull, reason: '$operationId must be generated');
        expect(contract!.commercialStatus, 'ready');
        expect(contract.commercialBlockReason, isEmpty);
      }
    });

    test('InitiateCall 使用 canonical operation 与 typed body', () async {
      executor.responses[AppCloudOperationIds.rtcCallSessionInitiateCall] =
          <String, Object?>{
            'session': _session('call-init'),
            'mediaAccess': <String, Object?>{'accessToken': 'token-init'},
          };
      final facet = RemoteCallLifecycleCommandWriter(
        client: client,
        invocationContext: _context,
      );

      final result = await facet.initiateCall(
        RtcInitiateCallCommand(
          callType: CallType.audio,
          inviteeIds: const <String>['user-2'],
          maxParticipants: 8,
        ),
      );

      expect(executor.operation?.method, 'POST');
      expect(executor.operation?.pathTemplate, '/rtc/calls');
      expect(executor.payload?.body, <String, Object?>{
        'callType': 'audio',
        'inviteeIds': const <String>['user-2'],
        'maxParticipants': 8,
      });
      expect(result.session.id, 'call-init');
      expect(result.mediaAccess.accessToken, 'token-init');
      expect(executor.context?.idempotencyKey, 'rtc-test-intent');
    });

    test('CallQuery 编码 path/query 且只认 nextCursor', () async {
      executor.responses[AppCloudOperationIds.rtcCallSessionGetCall] = _session(
        'call-get',
      );
      executor.responses[AppCloudOperationIds.rtcCallSessionListCalls] =
          <String, Object?>{
            'items': <Object?>[_session('call-history')],
            'nextCursor': 'cursor-next',
          };
      final query = RemoteCallQuery(
        client: client,
        invocationContext: _context,
      );

      final call = await query.getCall(RtcGetCallQuery(callId: 'call-get'));
      expect(call.id, 'call-get');
      expect(executor.payload?.pathParameters, <String, String>{
        'callId': 'call-get',
      });

      final page = await query.listCalls(
        RtcListCallsQuery(limit: 10, missedOnly: true),
      );
      expect(executor.payload?.queryParameters, <String, String>{
        'limit': '10',
        'missed': 'true',
      });
      expect(page.items.single.id, 'call-history');
      expect(page.nextCursor, 'cursor-next');
    });

    test('participant/media command encoders use canonical keys', () async {
      executor.responses[AppCloudOperationIds.rtcCallSessionInviteToCall] =
          _session('call-1');
      final participants = RemoteCallParticipantCommandWriter(
        client: client,
        invocationContext: _context,
      );
      await participants.inviteToCall(
        RtcInviteToCallCommand(
          callId: 'call-1',
          inviteeIds: const <String>['user-9'],
        ),
      );
      expect(executor.payload?.pathParameters['callId'], 'call-1');
      expect(executor.payload?.body, <String, Object?>{
        'inviteeIds': const <String>['user-9'],
      });

      executor.responses[AppCloudOperationIds
          .rtcCallSessionReportMediaConnected] = _session(
        'call-1',
      );
      await participants.reportMediaConnected(
        RtcCallIdCommand(callId: 'call-1'),
      );
      expect(executor.operation?.pathTemplate, '/rtc/calls/{callId}/connected');
      expect(executor.payload?.pathParameters['callId'], 'call-1');

      executor.responses[AppCloudOperationIds.rtcCallSessionToggleCamera] =
          _session('call-1');
      final media = RemoteCallMediaControlWriter(
        client: client,
        invocationContext: _context,
      );
      await media.toggleCamera(
        RtcToggleCameraCommand(callId: 'call-1', cameraOn: true),
      );
      expect(executor.payload?.body, <String, Object?>{'cameraOn': true});
    });

    test('ReportMediaConnected 对同一 call 使用稳定幂等 key', () async {
      executor.responses[AppCloudOperationIds
          .rtcCallSessionReportMediaConnected] = _session(
        'call-1',
      );
      final participants = RemoteCallParticipantCommandWriter(
        client: client,
        invocationContext: _context,
      );

      await participants.reportMediaConnected(
        RtcCallIdCommand(callId: 'call-1'),
      );
      await participants.reportMediaConnected(
        RtcCallIdCommand(callId: 'call-1'),
      );

      expect(
        executor.contexts.map((context) => context.idempotencyKey),
        everyElement('rtc-media-connected:call-1'),
      );
    });

    test('malformed response fails closed with FormatException', () {
      executor.responses[AppCloudOperationIds.rtcCallSessionGetCall] =
          <String, Object?>{'unexpected': true};
      final query = RemoteCallQuery(
        client: client,
        invocationContext: _context,
      );

      expectLater(
        query.getCall(RtcGetCallQuery(callId: 'call-bad')),
        throwsA(isA<FormatException>()),
      );
    });
  });
}

CloudOperationInvocationContext _context(
  String pageId, {
  required bool command,
}) => CloudOperationInvocationContext(
  surfaceId: 'rtcVoice',
  clientPageId: pageId,
  routeId: 'rtcVoice',
  idempotencyKey: command ? 'rtc-test-intent' : null,
  actor: const CloudOperationActorContext(
    accountId: 'account-1',
    personaId: 'persona-1',
  ),
);

Map<String, Object?> _session(String callId) => <String, Object?>{
  'id': callId,
  'callType': 'audio',
  'status': 'ringing',
  'initiatorId': 'persona-1',
  'roomId': 'rtc-room-$callId',
  'maxParticipants': 2,
  'participantCount': 2,
  'participants': <Object?>[
    <String, Object?>{
      'userId': 'persona-1',
      'role': 'initiator',
      'status': 'connecting',
      'isMuted': false,
      'isCameraOn': false,
    },
  ],
  'isScreenSharing': false,
  'createdAt': '2026-07-19T00:00:00Z',
  'updatedAt': '2026-07-19T00:00:00Z',
};

final class _CapturingExecutor implements CloudOperationExecutor {
  final Map<String, Object?> responses = <String, Object?>{};
  final List<CloudOperationInvocationContext> contexts =
      <CloudOperationInvocationContext>[];
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  CloudOperationRequestPayload? payload;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    this.context = context;
    contexts.add(context);
    payload = requestEncoder();
    return responseDecoder(responses[operation.canonicalOperationId]);
  }
}
