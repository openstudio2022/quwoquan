import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/rtc/mock/rtc_mock_data.dart';

abstract class RtcRepository {
  Future<Map<String, dynamic>> initiateCall({
    required String callType,
    String? conversationId,
    String? circleId,
    required List<String> inviteeIds,
    int maxParticipants = 32,
  });

  Future<Map<String, dynamic>> getCallSession(String callId);

  Future<Map<String, dynamic>> answerCall(String callId);

  Future<void> rejectCall(String callId);

  Future<void> hangUp(String callId);

  Future<Map<String, dynamic>> joinRtcToken(String callId);

  Future<void> muteToggle({
    required String callId,
    required bool muted,
  });

  Future<void> cameraToggle({
    required String callId,
    required bool cameraOn,
  });

  Future<void> startScreenShare(String callId);

  Future<void> stopScreenShare(String callId);

  Future<void> startRecording(String callId);

  Future<void> stopRecording(String callId);

  Future<List<Map<String, dynamic>>> listCallHistory({
    String? cursor,
    int limit = 20,
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
    int maxParticipants = 32,
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
    int limit = 20,
  }) async {
    return kMockCallHistory
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
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

  static String _base() => '${CloudRuntimeConfig.gatewayBaseUrl}/v1/rtc';

  @override
  Future<Map<String, dynamic>> initiateCall({
    required String callType,
    String? conversationId,
    String? circleId,
    required List<String> inviteeIds,
    int maxParticipants = 32,
  }) async {
    final body = <String, dynamic>{
      'callType': callType,
      if (conversationId != null) 'conversationId': conversationId,
      if (circleId != null) 'circleId': circleId,
      'inviteeIds': inviteeIds,
      'maxParticipants': maxParticipants,
    };
    final decoded = await _http.postJson(
      Uri.parse('${_base()}/calls'),
      headers: CloudRequestHeaders.forPage('rtc.initiate'),
      body: body,
    );
    return CloudResponseDecoder.asObject(decoded, context: 'initiateCall');
  }

  @override
  Future<Map<String, dynamic>> getCallSession(String callId) async {
    final decoded = await _http.getJson(
      Uri.parse('${_base()}/calls/$callId'),
      headers: CloudRequestHeaders.forPage('rtc.session'),
    );
    return CloudResponseDecoder.asObject(decoded, context: 'getCallSession');
  }

  @override
  Future<Map<String, dynamic>> answerCall(String callId) async {
    final decoded = await _http.postJson(
      Uri.parse('${_base()}/calls/$callId/answer'),
      headers: CloudRequestHeaders.forPage('rtc.answer'),
      body: const <String, dynamic>{},
    );
    return CloudResponseDecoder.asObject(decoded, context: 'answerCall');
  }

  @override
  Future<void> rejectCall(String callId) async {
    await _http.postJson(
      Uri.parse('${_base()}/calls/$callId/reject'),
      headers: CloudRequestHeaders.forPage('rtc.reject'),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<void> hangUp(String callId) async {
    await _http.postJson(
      Uri.parse('${_base()}/calls/$callId/hangup'),
      headers: CloudRequestHeaders.forPage('rtc.hangup'),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<Map<String, dynamic>> joinRtcToken(String callId) async {
    final decoded = await _http.postJson(
      Uri.parse('${_base()}/calls/$callId/token'),
      headers: CloudRequestHeaders.forPage('rtc.token'),
      body: const <String, dynamic>{},
    );
    return CloudResponseDecoder.asObject(decoded, context: 'joinRtcToken');
  }

  @override
  Future<void> muteToggle({
    required String callId,
    required bool muted,
  }) async {
    await _http.patchJson(
      Uri.parse('${_base()}/calls/$callId/media'),
      headers: CloudRequestHeaders.forPage('rtc.media'),
      body: {'muted': muted},
    );
  }

  @override
  Future<void> cameraToggle({
    required String callId,
    required bool cameraOn,
  }) async {
    await _http.patchJson(
      Uri.parse('${_base()}/calls/$callId/media'),
      headers: CloudRequestHeaders.forPage('rtc.media'),
      body: {'cameraOn': cameraOn},
    );
  }

  @override
  Future<void> startScreenShare(String callId) async {
    await _http.postJson(
      Uri.parse('${_base()}/calls/$callId/screen-share/start'),
      headers: CloudRequestHeaders.forPage('rtc.screenShare'),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<void> stopScreenShare(String callId) async {
    await _http.postJson(
      Uri.parse('${_base()}/calls/$callId/screen-share/stop'),
      headers: CloudRequestHeaders.forPage('rtc.screenShare'),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<void> startRecording(String callId) async {
    await _http.postJson(
      Uri.parse('${_base()}/calls/$callId/recording/start'),
      headers: CloudRequestHeaders.forPage('rtc.recording'),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<void> stopRecording(String callId) async {
    await _http.postJson(
      Uri.parse('${_base()}/calls/$callId/recording/stop'),
      headers: CloudRequestHeaders.forPage('rtc.recording'),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<List<Map<String, dynamic>>> listCallHistory({
    String? cursor,
    int limit = 20,
  }) async {
    final params = <String, String>{
      'limit': '$limit',
      if (cursor != null) 'cursor': cursor,
    };
    final decoded = await _http.getJson(
      Uri.parse('${_base()}/calls/history').replace(queryParameters: params),
      headers: CloudRequestHeaders.forPage('rtc.history'),
    );
    final page =
        CloudResponseDecoder.asCursorPage(decoded, context: 'listCallHistory');
    return page.items;
  }

  @override
  Future<List<Map<String, dynamic>>> listParticipants(String callId) async {
    final decoded = await _http.getJson(
      Uri.parse('${_base()}/calls/$callId/participants'),
      headers: CloudRequestHeaders.forPage('rtc.participants'),
    );
    final page = CloudResponseDecoder.asCursorPage(decoded,
        context: 'listParticipants');
    return page.items;
  }

  @override
  Future<void> inviteToCall({
    required String callId,
    required List<String> userIds,
  }) async {
    await _http.postJson(
      Uri.parse('${_base()}/calls/$callId/invite'),
      headers: CloudRequestHeaders.forPage('rtc.invite'),
      body: {'userIds': userIds},
    );
  }
}
