import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_request_wires.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/rtc/models/call_participant_dto.dart';
import 'package:quwoquan_app/cloud/rtc/models/call_session_dto.dart';
import 'package:quwoquan_app/cloud/rtc/models/rtc_repository_result_dtos.dart';
import 'package:quwoquan_app/cloud/services/rtc/mock/rtc_mock_data.dart';

abstract class RtcRepository {
  Future<RtcInitiateCallResultDto> initiateCall({
    required String callType,
    String? conversationId,
    String? circleId,
    required List<String> inviteeIds,
    int maxParticipants = CloudApiDefaults.callMaxParticipants,
  });

  Future<CallSessionDto> getCallSession(String callId);

  Future<RtcAnswerCallResultDto> answerCall(String callId);

  Future<void> rejectCall(String callId);

  Future<void> hangUp(String callId);

  Future<RtcJoinCredentialsDto> joinRtcToken(String callId);

  Future<void> muteToggle({required String callId, required bool muted});

  Future<void> cameraToggle({required String callId, required bool cameraOn});

  Future<void> startScreenShare(String callId);

  Future<void> stopScreenShare(String callId);

  Future<void> startRecording(String callId);

  Future<void> stopRecording(String callId);

  Future<List<CallSessionDto>> listCallHistory({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<List<CallParticipantDto>> listParticipants(String callId);

  Future<void> inviteToCall({
    required String callId,
    required List<String> inviteeIds,
  });

  /// 是否可在 Debug 下展示通话本地模拟控件（内嵌 RTC 桩为 true）。
  bool get supportsDevCallSimulation;
}

class MockRtcRepository implements RtcRepository {
  @override
  Future<RtcInitiateCallResultDto> initiateCall({
    required String callType,
    String? conversationId,
    String? circleId,
    required List<String> inviteeIds,
    int maxParticipants = CloudApiDefaults.callMaxParticipants,
  }) async {
    return RtcInitiateCallResultDto(
      session: kMockCallSessions.first,
      token: '',
    );
  }

  @override
  Future<CallSessionDto> getCallSession(String callId) async {
    for (final session in kMockCallSessions) {
      if (session.id == callId) {
        return session;
      }
    }
    return kMockCallSessions.first;
  }

  @override
  Future<RtcAnswerCallResultDto> answerCall(String callId) async {
    return RtcAnswerCallResultDto(
      session: kMockCallSessions.first.copyWith(status: 'in_call'),
    );
  }

  @override
  Future<void> rejectCall(String callId) async {}

  @override
  Future<void> hangUp(String callId) async {}

  @override
  Future<RtcJoinCredentialsDto> joinRtcToken(String callId) async {
    return kMockRtcJoinCredentials;
  }

  @override
  Future<void> muteToggle({
    required String callId,
    required bool muted,
  }) async {}

  @override
  Future<void> cameraToggle({
    required String callId,
    required bool cameraOn,
  }) async {}

  @override
  Future<void> startScreenShare(String callId) async {}

  @override
  Future<void> stopScreenShare(String callId) async {}

  @override
  Future<void> startRecording(String callId) async {}

  @override
  Future<void> stopRecording(String callId) async {}

  @override
  Future<List<CallSessionDto>> listCallHistory({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return kMockCallHistory
        .take(limit <= 0 ? kMockCallHistory.length : limit)
        .toList();
  }

  @override
  Future<List<CallParticipantDto>> listParticipants(String callId) async {
    for (final session in kMockCallSessions) {
      if (session.id == callId) {
        return session.participants;
      }
    }
    return [];
  }

  @override
  Future<void> inviteToCall({
    required String callId,
    required List<String> inviteeIds,
  }) async {}

  @override
  bool get supportsDevCallSimulation => true;
}

class RemoteRtcRepository implements RtcRepository {
  RemoteRtcRepository({http.Client? client})
    : _http = CloudHttpClient(client: client);

  final CloudHttpClient _http;

  static const _emptyPost = RtcEmptyPostBody();

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '${CloudRuntimeConfig.gatewayBaseUrl}$path',
    ).replace(queryParameters: queryParameters);
  }

  static CursorPage<CallSessionDto> _rtcListCallsCursorPage(CloudJsonMap obj) {
    final rawItems = obj['items'];
    if (rawItems is! List) {
      throw CloudErrorMapper.invalidResponse(
        message: 'Missing items: ${RtcRequestPageIds.listCalls}',
        requestPath: RtcRequestPageIds.listCalls,
        functionModule: 'rtc_repository',
      );
    }
    final items = <CallSessionDto>[];
    for (final raw in rawItems) {
      if (raw is! Map) continue;
      final m = raw is Map<String, dynamic>
          ? raw
          : Map<String, dynamic>.from(raw);
      items.add(CallSessionDto.fromMap(m));
    }
    final nextRaw = obj['nextCursor']?.toString() ?? obj['cursor']?.toString();
    final nextCursor = nextRaw != null && nextRaw.isEmpty ? null : nextRaw;
    return CursorPage<CallSessionDto>(items: items, nextCursor: nextCursor);
  }

  @override
  Future<RtcInitiateCallResultDto> initiateCall({
    required String callType,
    String? conversationId,
    String? circleId,
    required List<String> inviteeIds,
    int maxParticipants = CloudApiDefaults.callMaxParticipants,
  }) async {
    final body = RtcInitiateCallRequestWire(
      callType: callType,
      inviteeIds: inviteeIds,
      conversationId: conversationId,
      circleId: circleId,
      maxParticipants: maxParticipants,
    ).toJson();
    final decoded = await _http.postJson(
      _uri(RtcApiMetadata.initiateCallPath),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.initiateCall),
      body: body,
    );
    return RtcInitiateCallResultDto.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: RtcRequestPageIds.initiateCall,
      ),
    );
  }

  @override
  Future<CallSessionDto> getCallSession(String callId) async {
    final decoded = await _http.getJson(
      _uri(RtcApiMetadata.getCallPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.getCall),
    );
    return CallSessionDto.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: RtcRequestPageIds.getCall,
      ),
    );
  }

  @override
  Future<RtcAnswerCallResultDto> answerCall(String callId) async {
    final decoded = await _http.postJson(
      _uri(RtcApiMetadata.answerCallPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.answerCall),
      body: _emptyPost.toJson(),
    );
    return RtcAnswerCallResultDto.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: RtcRequestPageIds.answerCall,
      ),
    );
  }

  @override
  Future<void> rejectCall(String callId) async {
    await _http.postJson(
      _uri(RtcApiMetadata.rejectCallPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.rejectCall),
      body: _emptyPost.toJson(),
    );
  }

  @override
  Future<void> hangUp(String callId) async {
    await _http.postJson(
      _uri(RtcApiMetadata.hangupCallPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.hangupCall),
      body: _emptyPost.toJson(),
    );
  }

  @override
  Future<RtcJoinCredentialsDto> joinRtcToken(String callId) async {
    final decoded = await _http.postJson(
      _uri(RtcApiMetadata.joinCallPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.joinCall),
      body: _emptyPost.toJson(),
    );
    return RtcJoinCredentialsDto.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: RtcRequestPageIds.joinCall,
      ),
    );
  }

  @override
  Future<void> muteToggle({required String callId, required bool muted}) async {
    await _http.postJson(
      _uri(RtcApiMetadata.toggleMutePath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.toggleMute),
      body: RtcToggleMuteRequestWire(muted: muted).toJson(),
    );
  }

  @override
  Future<void> cameraToggle({
    required String callId,
    required bool cameraOn,
  }) async {
    await _http.postJson(
      _uri(RtcApiMetadata.toggleCameraPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.toggleCamera),
      body: RtcToggleCameraRequestWire(cameraOn: cameraOn).toJson(),
    );
  }

  @override
  Future<void> startScreenShare(String callId) async {
    await _http.postJson(
      _uri(RtcApiMetadata.startScreenSharePath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.startScreenShare),
      body: _emptyPost.toJson(),
    );
  }

  @override
  Future<void> stopScreenShare(String callId) async {
    await _http.postJson(
      _uri(RtcApiMetadata.stopScreenSharePath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.stopScreenShare),
      body: _emptyPost.toJson(),
    );
  }

  @override
  Future<void> startRecording(String callId) async {
    await _http.postJson(
      _uri(RtcApiMetadata.startRecordingPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.startRecording),
      body: _emptyPost.toJson(),
    );
  }

  @override
  Future<void> stopRecording(String callId) async {
    await _http.postJson(
      _uri(RtcApiMetadata.stopRecordingPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.stopRecording),
      body: _emptyPost.toJson(),
    );
  }

  @override
  Future<List<CallSessionDto>> listCallHistory({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{'limit': '$limit', 'cursor': ?cursor};
    final decoded = await _http.getJson(
      _uri(RtcApiMetadata.listCallsPath, queryParameters: params),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.listCalls),
    );
    final page = _rtcListCallsCursorPage(
      CloudResponseDecoder.asObject(
        decoded,
        context: RtcRequestPageIds.listCalls,
      ),
    );
    return page.items;
  }

  @override
  Future<List<CallParticipantDto>> listParticipants(String callId) async {
    final decoded = await _http.getJson(
      _uri(RtcApiMetadata.getCallPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.getCall),
    );
    final session = CallSessionDto.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: RtcRequestPageIds.getCall,
      ),
    );
    return session.participants;
  }

  @override
  Future<void> inviteToCall({
    required String callId,
    required List<String> inviteeIds,
  }) async {
    await _http.postJson(
      _uri(RtcApiMetadata.inviteToCallPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.inviteToCall),
      body: RtcInviteToCallRequestWire(inviteeIds: inviteeIds).toJson(),
    );
  }

  @override
  bool get supportsDevCallSimulation => false;
}
