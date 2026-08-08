// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-002
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-003
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-008
// readiness_case: call_session_initiate_call_app_local
// readiness_case: call_session_answer_call_app_local
// readiness_case: call_session_reject_call_app_local
// readiness_case: call_session_cancel_call_app_local
// readiness_case: call_session_hangup_call_app_local
// readiness_case: call_session_join_call_app_local
// readiness_case: call_session_leave_call_app_local
// readiness_case: call_session_report_media_connected_app_local
// readiness_case: call_session_invite_to_call_app_local
// readiness_case: call_session_get_call_app_local
// readiness_case: call_session_list_calls_app_local
// readiness_case: call_session_toggle_mute_app_local
// readiness_case: call_session_toggle_camera_app_local
// readiness_case: call_session_start_screen_share_app_local
// readiness_case: call_session_stop_screen_share_app_local

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/rtc/rtc_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/adapters/call_lifecycle_remote.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/adapters/call_media_control_remote.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/adapters/call_participant_remote.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/adapters/call_query_remote.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/adapters/call_screen_share_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('CallSession production Remote generated HTTP contract', () {
    late _RtcRemoteHarness harness;
    late RemoteCallLifecycleCommandWriter lifecycle;
    late RemoteCallParticipantCommandWriter participants;
    late RemoteCallQuery query;
    late RemoteCallMediaControlWriter media;
    late RemoteCallScreenShareWriter screenShare;

    setUp(() {
      harness = _RtcRemoteHarness();
      lifecycle = RemoteCallLifecycleCommandWriter(
        client: harness.client,
        invocationContext: _context,
      );
      participants = RemoteCallParticipantCommandWriter(
        client: harness.client,
        invocationContext: _context,
      );
      query = RemoteCallQuery(
        client: harness.client,
        invocationContext: _context,
      );
      media = RemoteCallMediaControlWriter(
        client: harness.client,
        invocationContext: _context,
      );
      screenShare = RemoteCallScreenShareWriter(
        client: harness.client,
        invocationContext: _context,
      );
    });

    test(
      'lifecycle commands preserve canonical wire and typed states',
      () async {
        final initiated = await lifecycle.initiateCall(
          RtcInitiateCallCommand(
            callType: CallType.video,
            inviteeIds: const <String>['persona-2'],
            conversationId: 'conversation-1',
            maxParticipants: 2,
          ),
        );
        final answered = await lifecycle.answerCall(
          RtcCallIdCommand(callId: 'call-answer'),
        );
        final rejected = await lifecycle.rejectCall(
          RtcCallIdCommand(callId: 'call-reject'),
        );
        final cancelled = await lifecycle.cancelCall(
          RtcCallIdCommand(callId: 'call-cancel'),
        );
        final hungUp = await lifecycle.hangupCall(
          RtcCallIdCommand(callId: 'call-hangup'),
        );

        _expectRequest(
          harness.requests[0],
          method: 'POST',
          path: '/rtc/calls',
          operationId: AppCloudOperationIds.rtcCallSessionInitiateCall,
          clientPageId: RtcRequestPageIds.initiateCall,
          idempotencyKey: _intent(RtcRequestPageIds.initiateCall),
          body: const <String, Object?>{
            'callType': 'video',
            'inviteeIds': <String>['persona-2'],
            'conversationId': 'conversation-1',
            'maxParticipants': 2,
          },
        );
        _expectCallIdCommand(
          harness.requests[1],
          path: '/rtc/calls/call-answer/answer',
          operationId: AppCloudOperationIds.rtcCallSessionAnswerCall,
          clientPageId: RtcRequestPageIds.answerCall,
        );
        _expectCallIdCommand(
          harness.requests[2],
          path: '/rtc/calls/call-reject/reject',
          operationId: AppCloudOperationIds.rtcCallSessionRejectCall,
          clientPageId: RtcRequestPageIds.rejectCall,
        );
        _expectCallIdCommand(
          harness.requests[3],
          path: '/rtc/calls/call-cancel/cancel',
          operationId: AppCloudOperationIds.rtcCallSessionCancelCall,
          clientPageId: RtcRequestPageIds.cancelCall,
        );
        _expectCallIdCommand(
          harness.requests[4],
          path: '/rtc/calls/call-hangup/hangup',
          operationId: AppCloudOperationIds.rtcCallSessionHangupCall,
          clientPageId: RtcRequestPageIds.hangupCall,
        );

        expect(initiated.session.id, 'call-initiate');
        expect(initiated.session.callType, CallType.video);
        expect(initiated.session.status, CallStatus.ringing);
        expect(initiated.mediaAccess.accessToken, 'media-initiate');
        expect(answered.session.id, 'call-answer');
        expect(answered.session.status, CallStatus.connecting);
        expect(answered.mediaAccess.accessToken, 'media-answer');
        expect(rejected.endReason, EndReason.rejected);
        expect(cancelled.endReason, EndReason.cancelled);
        expect(hungUp.endReason, EndReason.normal);
      },
    );

    test(
      'participant commands preserve membership wire and receipts',
      () async {
        final joined = await participants.joinCall(
          RtcCallIdCommand(callId: 'call-join'),
        );
        final left = await participants.leaveCall(
          RtcCallIdCommand(callId: 'call-leave'),
        );
        final connected = await participants.reportMediaConnected(
          RtcCallIdCommand(callId: 'call-connected'),
        );
        final invited = await participants.inviteToCall(
          RtcInviteToCallCommand(
            callId: 'call-invite',
            inviteeIds: const <String>['persona-3'],
          ),
        );

        _expectCallIdCommand(
          harness.requests[0],
          path: '/rtc/calls/call-join/join',
          operationId: AppCloudOperationIds.rtcCallSessionJoinCall,
          clientPageId: RtcRequestPageIds.joinCall,
        );
        _expectCallIdCommand(
          harness.requests[1],
          path: '/rtc/calls/call-leave/leave',
          operationId: AppCloudOperationIds.rtcCallSessionLeaveCall,
          clientPageId: RtcRequestPageIds.leaveCall,
        );
        _expectRequest(
          harness.requests[2],
          method: 'POST',
          path: '/rtc/calls/call-connected/connected',
          operationId: AppCloudOperationIds.rtcCallSessionReportMediaConnected,
          clientPageId: RtcRequestPageIds.reportMediaConnected,
          idempotencyKey: 'rtc-media-connected:call-connected',
        );
        _expectRequest(
          harness.requests[3],
          method: 'POST',
          path: '/rtc/calls/call-invite/invite',
          operationId: AppCloudOperationIds.rtcCallSessionInviteToCall,
          clientPageId: RtcRequestPageIds.inviteToCall,
          idempotencyKey: _intent(RtcRequestPageIds.inviteToCall),
          body: const <String, Object?>{
            'inviteeIds': <String>['persona-3'],
          },
        );

        expect(joined.session.id, 'call-join');
        expect(joined.mediaAccess.accessToken, 'media-join');
        expect(left.status, CallStatus.ended);
        expect(left.endReason, EndReason.lastLeave);
        expect(connected.status, CallStatus.inCall);
        expect(connected.startedAt, DateTime.parse('2026-08-08T10:01:00Z'));
        final invitedParticipant = invited.participants!.singleWhere(
          (participant) => participant.userId == 'persona-3',
        );
        expect(invitedParticipant.inviteStatus, CallInviteStatus.pending);
        expect(invitedParticipant.invitedBy, 'persona-1');
      },
    );

    test('query operations preserve path, filters and nonempty page', () async {
      final call = await query.getCall(RtcGetCallQuery(callId: 'call-get'));
      final page = await query.listCalls(
        RtcListCallsQuery(
          cursor: 'cursor-current',
          limit: 7,
          status: CallStatus.inCall,
          missedOnly: true,
        ),
      );

      _expectRequest(
        harness.requests[0],
        method: 'GET',
        path: '/rtc/calls/call-get',
        operationId: AppCloudOperationIds.rtcCallSessionGetCall,
        clientPageId: RtcRequestPageIds.getCall,
      );
      _expectRequest(
        harness.requests[1],
        method: 'GET',
        path: '/rtc/calls',
        operationId: AppCloudOperationIds.rtcCallSessionListCalls,
        clientPageId: RtcRequestPageIds.listCalls,
        query: const <String, String>{
          'cursor': 'cursor-current',
          'limit': '7',
          'status': 'in_call',
          'missed': 'true',
        },
      );

      expect(call.id, 'call-get');
      expect(call.status, CallStatus.inCall);
      expect(call.participants, isNotEmpty);
      expect(page.items, hasLength(1));
      expect(page.items.single.id, 'call-history');
      expect(page.items.single.endReason, EndReason.normal);
      expect(page.nextCursor, 'cursor-next');
    });

    test(
      'media controls preserve typed booleans and participant state',
      () async {
        final muted = await media.toggleMute(
          RtcToggleMuteCommand(callId: 'call-mute', muted: true),
        );
        final camera = await media.toggleCamera(
          RtcToggleCameraCommand(callId: 'call-camera', cameraOn: true),
        );

        _expectRequest(
          harness.requests[0],
          method: 'POST',
          path: '/rtc/calls/call-mute/mute',
          operationId: AppCloudOperationIds.rtcCallSessionToggleMute,
          clientPageId: RtcRequestPageIds.toggleMute,
          idempotencyKey: _intent(RtcRequestPageIds.toggleMute),
          body: const <String, Object?>{'muted': true},
        );
        _expectRequest(
          harness.requests[1],
          method: 'POST',
          path: '/rtc/calls/call-camera/camera',
          operationId: AppCloudOperationIds.rtcCallSessionToggleCamera,
          clientPageId: RtcRequestPageIds.toggleCamera,
          idempotencyKey: _intent(RtcRequestPageIds.toggleCamera),
          body: const <String, Object?>{'cameraOn': true},
        );

        expect(muted.participants!.single.isMuted, isTrue);
        expect(camera.participants!.single.isCameraOn, isTrue);
      },
    );

    test(
      'screen share commands preserve named paths and aggregate state',
      () async {
        final started = await screenShare.startScreenShare(
          RtcCallIdCommand(callId: 'call-share-start'),
        );
        final stopped = await screenShare.stopScreenShare(
          RtcCallIdCommand(callId: 'call-share-stop'),
        );

        _expectCallIdCommand(
          harness.requests[0],
          path: '/rtc/calls/call-share-start/screen-share/start',
          operationId: AppCloudOperationIds.rtcCallSessionStartScreenShare,
          clientPageId: RtcRequestPageIds.startScreenShare,
        );
        _expectCallIdCommand(
          harness.requests[1],
          path: '/rtc/calls/call-share-stop/screen-share/stop',
          operationId: AppCloudOperationIds.rtcCallSessionStopScreenShare,
          clientPageId: RtcRequestPageIds.stopScreenShare,
        );

        expect(started.isScreenSharing, isTrue);
        expect(started.screenShareUserId, 'persona-1');
        expect(stopped.isScreenSharing, isFalse);
        expect(stopped.screenShareUserId, isNull);
      },
    );

    test(
      'malformed response fails closed without synthesized CallSession',
      () async {
        final malformed = _RtcRemoteHarness(
          responseOverride: (_) => const <String, Object?>{
            'id': 'call-malformed',
          },
        );
        final malformedQuery = RemoteCallQuery(
          client: malformed.client,
          invocationContext: _context,
        );

        await expectLater(
          malformedQuery.getCall(RtcGetCallQuery(callId: 'call-malformed')),
          throwsA(
            isA<CloudException>().having(
              (error) => error.runtimeFailure.code,
              'runtime failure code',
              'APP.CONTRACT.invalid_json',
            ),
          ),
        );
      },
    );

    test(
      'all operations preserve canonical account-security failure',
      () async {
        final denied = _RtcRemoteHarness(
          statusCode: 401,
          responseOverride: (_) => const <String, Object?>{
            'code': 'RTC.USER.account_security_denied',
            'reason': 'unauthorized',
            'origin': 'user',
            'kind': 'auth',
            'nature': 'requiresUserAction',
            'requestId': 'rtc-denied-request',
            'traceId': 'rtc-denied-trace',
            'userMessage': 'Your sign-in credential is no longer valid',
            'location': <String, Object?>{
              'businessObject': 'call_session',
              'functionModule': 'call_facade',
            },
            'context': <String, Object?>{'attributes': <Map<String, String>>[]},
            'recovery': <String, Object?>{
              'action': 'surface',
              'disruptionLevel': 'inlineCard',
            },
          },
        );
        final deniedLifecycle = RemoteCallLifecycleCommandWriter(
          client: denied.client,
          invocationContext: _context,
        );
        final deniedParticipants = RemoteCallParticipantCommandWriter(
          client: denied.client,
          invocationContext: _context,
        );
        final deniedQuery = RemoteCallQuery(
          client: denied.client,
          invocationContext: _context,
        );
        final deniedMedia = RemoteCallMediaControlWriter(
          client: denied.client,
          invocationContext: _context,
        );
        final deniedScreenShare = RemoteCallScreenShareWriter(
          client: denied.client,
          invocationContext: _context,
        );
        final invocations = <String, Future<Object?> Function()>{
          AppCloudOperationIds.rtcCallSessionInitiateCall: () =>
              deniedLifecycle.initiateCall(
                RtcInitiateCallCommand(
                  callType: CallType.video,
                  inviteeIds: const <String>['persona-2'],
                  maxParticipants: 2,
                ),
              ),
          AppCloudOperationIds.rtcCallSessionAnswerCall: () => deniedLifecycle
              .answerCall(RtcCallIdCommand(callId: 'call-answer')),
          AppCloudOperationIds.rtcCallSessionRejectCall: () => deniedLifecycle
              .rejectCall(RtcCallIdCommand(callId: 'call-reject')),
          AppCloudOperationIds.rtcCallSessionCancelCall: () => deniedLifecycle
              .cancelCall(RtcCallIdCommand(callId: 'call-cancel')),
          AppCloudOperationIds.rtcCallSessionHangupCall: () => deniedLifecycle
              .hangupCall(RtcCallIdCommand(callId: 'call-hangup')),
          AppCloudOperationIds.rtcCallSessionJoinCall: () => deniedParticipants
              .joinCall(RtcCallIdCommand(callId: 'call-join')),
          AppCloudOperationIds.rtcCallSessionLeaveCall: () => deniedParticipants
              .leaveCall(RtcCallIdCommand(callId: 'call-leave')),
          AppCloudOperationIds.rtcCallSessionReportMediaConnected: () =>
              deniedParticipants.reportMediaConnected(
                RtcCallIdCommand(callId: 'call-connected'),
              ),
          AppCloudOperationIds.rtcCallSessionInviteToCall: () =>
              deniedParticipants.inviteToCall(
                RtcInviteToCallCommand(
                  callId: 'call-invite',
                  inviteeIds: const <String>['persona-3'],
                ),
              ),
          AppCloudOperationIds.rtcCallSessionGetCall: () =>
              deniedQuery.getCall(RtcGetCallQuery(callId: 'call-get')),
          AppCloudOperationIds.rtcCallSessionListCalls: () =>
              deniedQuery.listCalls(RtcListCallsQuery(limit: 7)),
          AppCloudOperationIds.rtcCallSessionToggleMute: () =>
              deniedMedia.toggleMute(
                RtcToggleMuteCommand(callId: 'call-mute', muted: true),
              ),
          AppCloudOperationIds.rtcCallSessionToggleCamera: () =>
              deniedMedia.toggleCamera(
                RtcToggleCameraCommand(callId: 'call-camera', cameraOn: true),
              ),
          AppCloudOperationIds.rtcCallSessionStartScreenShare: () =>
              deniedScreenShare.startScreenShare(
                RtcCallIdCommand(callId: 'call-share-start'),
              ),
          AppCloudOperationIds.rtcCallSessionStopScreenShare: () =>
              deniedScreenShare.stopScreenShare(
                RtcCallIdCommand(callId: 'call-share-stop'),
              ),
        };

        for (final invocation in invocations.entries) {
          try {
            await invocation.value();
            fail('${invocation.key} must not synthesize a successful result');
          } on CloudException catch (error) {
            expect(error.type, CloudErrorType.unauthorized);
            expect(error.statusCode, 401);
            expect(error.code, 'RTC.USER.account_security_denied');
            expect(error.runtimeFailure.code, error.code);
            expect(error.runtimeFailure.semanticReason, 'unauthorized');
            expect(error.runtimeFailure.recovery.action, 'surface');
            expect(
              error.userMessage,
              'Your sign-in credential is no longer valid',
            );
            expect(error.requestId, 'rtc-denied-request');
            expect(error.traceId, 'rtc-denied-trace');
            expect(error.sourceOperationId, invocation.key);
          }
        }

        expect(
          denied.requests
              .map((request) => request.headers['X-Client-Operation-Id'])
              .toSet(),
          invocations.keys.toSet(),
        );
      },
    );
  });
}

CloudOperationInvocationContext _context(
  String clientPageId, {
  required bool command,
}) => CloudOperationInvocationContext(
  surfaceId: _surfaceForPage(clientPageId).id,
  routeId: _surfaceForPage(clientPageId).routeId,
  clientPageId: clientPageId,
  actor: const CloudOperationActorContext(
    accountId: 'account-1',
    personaId: 'persona-1',
    deviceActorId: 'device-1',
  ),
  idempotencyKey: command ? _intent(clientPageId) : null,
);

String _intent(String clientPageId) => 'rtc-$clientPageId-intent';

void _expectCallIdCommand(
  http.Request request, {
  required String path,
  required String operationId,
  required String clientPageId,
}) {
  _expectRequest(
    request,
    method: 'POST',
    path: path,
    operationId: operationId,
    clientPageId: clientPageId,
    idempotencyKey: _intent(clientPageId),
  );
}

void _expectRequest(
  http.Request request, {
  required String method,
  required String path,
  required String operationId,
  required String clientPageId,
  String? idempotencyKey,
  Map<String, String> query = const <String, String>{},
  Map<String, Object?>? body,
}) {
  expect(request.method, method);
  expect(request.url.path, path);
  expect(request.url.queryParameters, query);
  expect(request.headers['Authorization'], 'Bearer rtc-contract-token');
  expect(request.headers['X-Client-Operation-Id'], operationId);
  expect(request.headers['X-Client-Page-Id'], clientPageId);
  expect(
    request.headers['X-Client-Surface-Id'],
    _surfaceForPage(clientPageId).id,
  );
  expect(
    request.headers['X-Client-Route-Id'],
    _surfaceForPage(clientPageId).routeId,
  );
  expect(request.headers['Idempotency-Key'], idempotencyKey);
  expect(request.headers['X-Trace-Id'], contains(operationId));
  expect(request.headers['X-Request-Id'], contains(operationId));
  if (body == null) {
    expect(request.body, isEmpty);
  } else {
    expect(request.headers['Content-Type'], 'application/json');
    expect(jsonDecode(request.body), body);
  }
}

({String id, String routeId}) _surfaceForPage(String clientPageId) {
  final surface = switch (clientPageId) {
    RtcRequestPageIds.initiateCall => AppUiSurfaces.chatDetail,
    RtcRequestPageIds.inviteToCall => AppUiSurfaces.rtcPickParticipants,
    RtcRequestPageIds.answerCall ||
    RtcRequestPageIds.rejectCall => AppUiSurfaces.rtcIncoming,
    RtcRequestPageIds.cancelCall => AppUiSurfaces.rtcOutgoing,
    RtcRequestPageIds.listCalls => AppUiSurfaces.chatList,
    _ => AppUiSurfaces.rtcVoice,
  };
  return (id: surface.id, routeId: surface.routeId);
}

final class _RtcRemoteHarness {
  _RtcRemoteHarness({this.responseOverride, this.statusCode = 200}) {
    client = buildGeneratedCloudOperationClient(
      httpClient: CloudHttpClient(
        client: MockClient((request) async {
          requests.add(request);
          final response =
              responseOverride?.call(request) ??
              _responseFor(request.headers['X-Client-Operation-Id']);
          return http.Response(
            jsonEncode(response),
            statusCode,
            headers: const <String, String>{'content-type': 'application/json'},
          );
        }),
        authTokenProvider: const _RtcTokenProvider(),
      ),
      clientContextProvider: const _RtcClientContext(),
      telemetrySink: const _RtcTelemetrySink(),
      environment: CloudRuntimeEnvironment(
        environment: CloudEnvironment.alpha,
        gatewayBaseUri: Uri.parse('https://rtc-contract.test'),
      ),
    );
  }

  final Object? Function(http.Request request)? responseOverride;
  final int statusCode;
  final List<http.Request> requests = <http.Request>[];
  late final GeneratedCloudOperationClient client;
}

Object _responseFor(String? operationId) => switch (operationId) {
  AppCloudOperationIds.rtcCallSessionInitiateCall => <String, Object?>{
    'session': _session(
      id: 'call-initiate',
      status: 'ringing',
      callType: 'video',
    ),
    'mediaAccess': const <String, Object?>{'accessToken': 'media-initiate'},
  },
  AppCloudOperationIds.rtcCallSessionAnswerCall => <String, Object?>{
    'session': _session(id: 'call-answer', status: 'connecting'),
    'mediaAccess': const <String, Object?>{'accessToken': 'media-answer'},
  },
  AppCloudOperationIds.rtcCallSessionRejectCall => _session(
    id: 'call-reject',
    status: 'ended',
    endReason: 'rejected',
  ),
  AppCloudOperationIds.rtcCallSessionCancelCall => _session(
    id: 'call-cancel',
    status: 'ended',
    endReason: 'cancelled',
  ),
  AppCloudOperationIds.rtcCallSessionHangupCall => _session(
    id: 'call-hangup',
    status: 'ended',
    endReason: 'normal',
  ),
  AppCloudOperationIds.rtcCallSessionJoinCall => <String, Object?>{
    'session': _session(id: 'call-join', status: 'connecting'),
    'mediaAccess': const <String, Object?>{'accessToken': 'media-join'},
  },
  AppCloudOperationIds.rtcCallSessionLeaveCall => _session(
    id: 'call-leave',
    status: 'ended',
    endReason: 'last_leave',
  ),
  AppCloudOperationIds.rtcCallSessionReportMediaConnected => _session(
    id: 'call-connected',
    status: 'in_call',
    startedAt: '2026-08-08T10:01:00Z',
  ),
  AppCloudOperationIds.rtcCallSessionInviteToCall => _session(
    id: 'call-invite',
    status: 'ringing',
    participants: <Object?>[
      _participant(),
      _participant(
        userId: 'persona-3',
        role: 'invitee',
        status: 'invited',
        inviteStatus: 'pending',
        invitedBy: 'persona-1',
      ),
    ],
  ),
  AppCloudOperationIds.rtcCallSessionGetCall => _session(
    id: 'call-get',
    status: 'in_call',
    startedAt: '2026-08-08T10:01:00Z',
  ),
  AppCloudOperationIds.rtcCallSessionListCalls => <String, Object?>{
    'items': <Object?>[
      _session(id: 'call-history', status: 'ended', endReason: 'normal'),
    ],
    'nextCursor': 'cursor-next',
  },
  AppCloudOperationIds.rtcCallSessionToggleMute => _session(
    id: 'call-mute',
    status: 'in_call',
    participantMuted: true,
  ),
  AppCloudOperationIds.rtcCallSessionToggleCamera => _session(
    id: 'call-camera',
    status: 'in_call',
    participantCameraOn: true,
  ),
  AppCloudOperationIds.rtcCallSessionStartScreenShare => _session(
    id: 'call-share-start',
    status: 'in_call',
    isScreenSharing: true,
    screenShareUserId: 'persona-1',
  ),
  AppCloudOperationIds.rtcCallSessionStopScreenShare => _session(
    id: 'call-share-stop',
    status: 'in_call',
  ),
  _ => throw StateError('unexpected RTC operation $operationId'),
};

Map<String, Object?> _session({
  required String id,
  required String status,
  String callType = 'audio',
  String? endReason,
  String? startedAt,
  bool participantMuted = false,
  bool participantCameraOn = false,
  bool isScreenSharing = false,
  String? screenShareUserId,
  List<Object?>? participants,
}) {
  final typedParticipants =
      participants ??
      <Object?>[
        _participant(
          muted: participantMuted,
          cameraOn: participantCameraOn,
          status: status == 'in_call' ? 'connected' : 'connecting',
        ),
      ];
  return <String, Object?>{
    'id': id,
    'callType': callType,
    'status': status,
    'initiatorId': 'persona-1',
    'conversationId': 'conversation-1',
    'roomId': 'room-$id',
    'maxParticipants': 32,
    'participantCount': typedParticipants.length,
    'participants': typedParticipants,
    'isScreenSharing': isScreenSharing,
    'screenShareUserId': ?screenShareUserId,
    'endReason': ?endReason,
    'startedAt': ?startedAt,
    if (status == 'ended') 'endedAt': '2026-08-08T10:02:00Z',
    'createdAt': '2026-08-08T10:00:00Z',
    'updatedAt': '2026-08-08T10:02:00Z',
  };
}

Map<String, Object?> _participant({
  String userId = 'persona-1',
  String role = 'initiator',
  String status = 'connecting',
  bool muted = false,
  bool cameraOn = false,
  String? inviteStatus,
  String? invitedBy,
}) => <String, Object?>{
  'userId': userId,
  'role': role,
  'status': status,
  'isMuted': muted,
  'isCameraOn': cameraOn,
  'inviteStatus': ?inviteStatus,
  'invitedBy': ?invitedBy,
};

final class _RtcTokenProvider implements CloudAuthTokenProvider {
  const _RtcTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'rtc-contract-token';
}

final class _RtcClientContext implements CloudClientContextProvider {
  const _RtcClientContext();

  @override
  CloudClientContextSnapshot snapshot() => const CloudClientContextSnapshot(
    sessionId: 'rtc-contract-session',
    deviceActorId: 'rtc-contract-device',
    platform: 'test',
    appVersion: 'test',
    locale: 'zh-CN',
  );
}

final class _RtcTelemetrySink implements CloudOperationTelemetrySink {
  const _RtcTelemetrySink();

  @override
  void record(CloudOperationTelemetryEvent event) {}
}
