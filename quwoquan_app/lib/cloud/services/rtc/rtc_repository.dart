import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/rtc/mock/rtc_mock_data.dart';

abstract class RtcRepository {
  Future<Map<String, dynamic>> initiateCall({
    required String callType,
    String? conversationId,
    String? circleId,
    required List<String> inviteeIds,
    int maxParticipants = CloudApiDefaults.callMaxParticipants,
  });

  Future<Map<String, dynamic>> getCallSession(String callId);

  Future<Map<String, dynamic>> answerCall(String callId);

  Future<void> rejectCall(String callId);

  Future<void> hangUp(String callId);

  Future<Map<String, dynamic>> joinRtcToken(String callId);

  Future<void> muteToggle({required String callId, required bool muted});

  Future<void> cameraToggle({required String callId, required bool cameraOn});

  Future<void> startScreenShare(String callId);

  Future<void> stopScreenShare(String callId);

  Future<void> startRecording(String callId);

  Future<void> stopRecording(String callId);

  Future<List<Map<String, dynamic>>> listCallHistory({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<List<Map<String, dynamic>>> listParticipants(String callId);

  Future<void> inviteToCall({
    required String callId,
    required List<String> userIds,
  });
}

class MockRtcRepository implements RtcRepository {
  @override
  Future<Map<String, dynamic>> initiateCall({
    required String callType,
    String? conversationId,
    String? circleId,
    required List<String> inviteeIds,
    int maxParticipants = CloudApiDefaults.callMaxParticipants,
  }) async {
    return Map<String, dynamic>.from(kMockCallSessions.first);
  }

  @override
  Future<Map<String, dynamic>> getCallSession(String callId) async {
    for (final session in kMockCallSessions) {
      if (session['_id'] == callId) {
        return Map<String, dynamic>.from(session);
      }
    }
    return Map<String, dynamic>.from(kMockCallSessions.first);
  }

  @override
  Future<Map<String, dynamic>> answerCall(String callId) async {
    final session = Map<String, dynamic>.from(kMockCallSessions.first);
    session['status'] = 'active';
    return session;
  }

  @override
  Future<void> rejectCall(String callId) async {}

  @override
  Future<void> hangUp(String callId) async {}

  @override
  Future<Map<String, dynamic>> joinRtcToken(String callId) async {
    return Map<String, dynamic>.from(kMockRtcToken);
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
  Future<List<Map<String, dynamic>>> listCallHistory({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return kMockCallHistory.map((e) => Map<String, dynamic>.from(e)).toList();
  }

  @override
  Future<List<Map<String, dynamic>>> listParticipants(String callId) async {
    for (final session in kMockCallSessions) {
      if (session['_id'] == callId) {
        final participants = session['participants'] as List;
        return participants
            .map((p) => Map<String, dynamic>.from(p as Map))
            .toList();
      }
    }
    return [];
  }

  @override
  Future<void> inviteToCall({
    required String callId,
    required List<String> userIds,
  }) async {}
}

class RemoteRtcRepository implements RtcRepository {
  RemoteRtcRepository({http.Client? client})
    : _http = CloudHttpClient(client: client);

  final CloudHttpClient _http;

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '${CloudRuntimeConfig.gatewayBaseUrl}$path',
    ).replace(queryParameters: queryParameters);
  }

  @override
  Future<Map<String, dynamic>> initiateCall({
    required String callType,
    String? conversationId,
    String? circleId,
    required List<String> inviteeIds,
    int maxParticipants = CloudApiDefaults.callMaxParticipants,
  }) async {
    final body = <String, dynamic>{
      'callType': callType,
      'conversationId': ?conversationId,
      'circleId': ?circleId,
      'inviteeIds': inviteeIds,
      'maxParticipants': maxParticipants,
    };
    final decoded = await _http.postJson(
      _uri(RtcApiMetadata.initiateCallPath),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.initiateCall),
      body: body,
    );
    return CloudResponseDecoder.asObject(decoded, context: 'initiateCall');
  }

  @override
  Future<Map<String, dynamic>> getCallSession(String callId) async {
    final decoded = await _http.getJson(
      _uri(RtcApiMetadata.getCallPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.getCall),
    );
    return CloudResponseDecoder.asObject(decoded, context: 'getCallSession');
  }

  @override
  Future<Map<String, dynamic>> answerCall(String callId) async {
    final decoded = await _http.postJson(
      _uri(RtcApiMetadata.answerCallPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.answerCall),
      body: const <String, dynamic>{},
    );
    return CloudResponseDecoder.asObject(decoded, context: 'answerCall');
  }

  @override
  Future<void> rejectCall(String callId) async {
    await _http.postJson(
      _uri(RtcApiMetadata.rejectCallPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.rejectCall),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<void> hangUp(String callId) async {
    await _http.postJson(
      _uri(RtcApiMetadata.hangupCallPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.hangupCall),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<Map<String, dynamic>> joinRtcToken(String callId) async {
    final decoded = await _http.postJson(
      _uri(RtcApiMetadata.joinCallPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.joinCall),
      body: const <String, dynamic>{},
    );
    return CloudResponseDecoder.asObject(decoded, context: 'joinRtcToken');
  }

  @override
  Future<void> muteToggle({required String callId, required bool muted}) async {
    await _http.patchJson(
      _uri(RtcApiMetadata.toggleMutePath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.toggleMute),
      body: {'muted': muted},
    );
  }

  @override
  Future<void> cameraToggle({
    required String callId,
    required bool cameraOn,
  }) async {
    await _http.patchJson(
      _uri(RtcApiMetadata.toggleCameraPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.toggleCamera),
      body: {'enabled': cameraOn},
    );
  }

  @override
  Future<void> startScreenShare(String callId) async {
    await _http.postJson(
      _uri(RtcApiMetadata.startScreenSharePath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.startScreenShare),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<void> stopScreenShare(String callId) async {
    await _http.postJson(
      _uri(RtcApiMetadata.stopScreenSharePath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.stopScreenShare),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<void> startRecording(String callId) async {
    await _http.postJson(
      _uri(RtcApiMetadata.startRecordingPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.startRecording),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<void> stopRecording(String callId) async {
    await _http.postJson(
      _uri(RtcApiMetadata.stopRecordingPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.stopRecording),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<List<Map<String, dynamic>>> listCallHistory({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{'limit': '$limit', 'cursor': ?cursor};
    final decoded = await _http.getJson(
      _uri(RtcApiMetadata.listCallsPath, queryParameters: params),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.listCalls),
    );
    final page = CloudResponseDecoder.asCursorPage(
      decoded,
      context: 'listCallHistory',
    );
    return page.items;
  }

  @override
  Future<List<Map<String, dynamic>>> listParticipants(String callId) async {
    final decoded = await _http.getJson(
      _uri(RtcApiMetadata.getCallPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.getCall),
    );
    final call = CloudResponseDecoder.asObject(decoded, context: 'listParticipants');
    final participants = call['participants'];
    if (participants is List) {
      return participants.cast<Map<String, dynamic>>();
    }
    return const <Map<String, dynamic>>[];
  }

  @override
  Future<void> inviteToCall({
    required String callId,
    required List<String> userIds,
  }) async {
    await _http.postJson(
      _uri(RtcApiMetadata.inviteToCallPath(callId: callId)),
      headers: CloudRequestHeaders.forPage(RtcRequestPageIds.inviteToCall),
      body: {'userIds': userIds},
    );
  }
}
