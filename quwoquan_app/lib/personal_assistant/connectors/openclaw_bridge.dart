import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/personal_assistant/app/assistant_gateway.dart';
import 'package:quwoquan_app/personal_assistant/contracts/user_events.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_response.dart';

enum OpenClawRemoteStreamEventType { chunk, trace, userEvent, completed, failed }

class OpenClawRemoteStreamEvent {
  const OpenClawRemoteStreamEvent._({
    required this.type,
    this.chunkText,
    this.trace,
    this.userEvent,
    this.response,
    this.errorMessage,
  });

  factory OpenClawRemoteStreamEvent.chunk(String chunkText) =>
      OpenClawRemoteStreamEvent._(
        type: OpenClawRemoteStreamEventType.chunk,
        chunkText: chunkText,
      );

  factory OpenClawRemoteStreamEvent.trace(AssistantTraceEvent trace) =>
      OpenClawRemoteStreamEvent._(
        type: OpenClawRemoteStreamEventType.trace,
        trace: trace,
      );

  factory OpenClawRemoteStreamEvent.userEvent(UserEvent userEvent) =>
      OpenClawRemoteStreamEvent._(
        type: OpenClawRemoteStreamEventType.userEvent,
        userEvent: userEvent,
      );

  factory OpenClawRemoteStreamEvent.completed(AssistantRunResponse response) =>
      OpenClawRemoteStreamEvent._(
        type: OpenClawRemoteStreamEventType.completed,
        response: response,
      );

  factory OpenClawRemoteStreamEvent.failed(String errorMessage) =>
      OpenClawRemoteStreamEvent._(
        type: OpenClawRemoteStreamEventType.failed,
        errorMessage: errorMessage,
      );

  final OpenClawRemoteStreamEventType type;
  final String? chunkText;
  final AssistantTraceEvent? trace;
  final UserEvent? userEvent;
  final AssistantRunResponse? response;
  final String? errorMessage;
}

class OpenClawBridge {
  OpenClawBridge({required this.baseUrl, this.authToken});

  final String baseUrl;
  final String? authToken;
  AssistantGateway? _localGateway;

  bool get isRemoteConfigured => baseUrl.trim().isNotEmpty;

  void bindLocalGateway(AssistantGateway gateway) {
    _localGateway = gateway;
  }

  Map<String, String> _headers() {
    final headers = <String, String>{'Content-Type': 'application/json'};
    final token = authToken?.trim() ?? '';
    if (token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

  Future<AssistantRunResponse?> runRemote(AssistantRunRequest request) async {
    if (baseUrl.isEmpty) return null;
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/v1/run'),
        headers: _headers(),
        body: jsonEncode(<String, dynamic>{
          'messages': request.messages
              .map((m) => m.toJson())
              .toList(growable: false),
          'sessionId': request.sessionId,
          'userId': request.userId,
          'deviceProfile': request.deviceProfile,
          'channel': request.channel,
          'traceId': request.traceId,
          'capabilityCatalog': request.capabilityCatalog,
          'contextScopeHint': request.contextScopeHint,
          'privacyProfile': request.privacyProfile,
          'privacyPolicy': request.privacyPolicy,
        }),
      );
      if (response.statusCode >= 400) {
        final reason = _extractErrorMessage(response.body);
        return AssistantRunResponse(
          finalText:
              '远端模型调用失败: HTTP ${response.statusCode}${reason.isEmpty ? '' : ' - $reason'}',
          traces: const [],
          runId: request.traceId,
          traceId: request.traceId,
          degraded: true,
          errorCode: 'remote_model_http_${response.statusCode}',
        );
      }
      final body = jsonDecode(response.body);
      if (body is! Map<String, dynamic>) {
        return AssistantRunResponse(
          finalText: '远端模型返回格式异常',
          traces: const [],
          runId: request.traceId,
          traceId: request.traceId,
          degraded: true,
          errorCode: 'remote_model_invalid_payload',
        );
      }
      return AssistantRunResponse.fromJson(body);
    } catch (e) {
      return AssistantRunResponse(
        finalText: '远端模型调用异常: $e',
        traces: const [],
        runId: request.traceId,
        traceId: request.traceId,
        degraded: true,
        errorCode: 'remote_model_exception',
      );
    }
  }

  Stream<OpenClawRemoteStreamEvent> runRemoteStream(
    AssistantRunRequest request,
  ) async* {
    if (baseUrl.isEmpty) return;
    final client = http.Client();
    try {
      final req = http.Request('POST', Uri.parse('$baseUrl/v1/run/stream'))
        ..headers.addAll(_headers())
        ..body = jsonEncode(<String, dynamic>{
          'messages': request.messages
              .map((m) => m.toJson())
              .toList(growable: false),
          'sessionId': request.sessionId,
          'userId': request.userId,
          'deviceProfile': request.deviceProfile,
          'channel': request.channel,
          'traceId': request.traceId,
          'capabilityCatalog': request.capabilityCatalog,
          'contextScopeHint': request.contextScopeHint,
          'privacyProfile': request.privacyProfile,
          'privacyPolicy': request.privacyPolicy,
        });
      final response = await client.send(req);
      if (response.statusCode >= 400) {
        final reason = _extractErrorMessage(
          await response.stream.bytesToString(),
        );
        yield OpenClawRemoteStreamEvent.failed(
          'remote stream failed: HTTP ${response.statusCode}${reason.isEmpty ? '' : ' - $reason'}',
        );
        return;
      }

      final buffer = StringBuffer();
      await for (final piece in response.stream.transform(utf8.decoder)) {
        buffer.write(piece);
        var current = buffer.toString();
        var splitIndex = current.indexOf('\n\n');
        while (splitIndex >= 0) {
          final frame = current.substring(0, splitIndex);
          current = current.substring(splitIndex + 2);
          final event = _parseSseFrame(frame);
          if (event != null) {
            yield event;
          }
          splitIndex = current.indexOf('\n\n');
        }
        buffer
          ..clear()
          ..write(current);
      }
      final tail = buffer.toString().trim();
      if (tail.isNotEmpty) {
        final event = _parseSseFrame(tail);
        if (event != null) yield event;
      }
    } catch (e) {
      yield OpenClawRemoteStreamEvent.failed('remote stream exception: $e');
    } finally {
      client.close();
    }
  }

  Future<Map<String, dynamic>?> invokeSkillRemote({
    required String skillId,
    required Map<String, dynamic> arguments,
  }) async {
    if (baseUrl.isEmpty) return null;
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/v1/skills/invoke'),
        headers: _headers(),
        body: jsonEncode(<String, dynamic>{
          'skill_id': skillId,
          'arguments': arguments,
        }),
      );
      if (response.statusCode >= 400) return null;
      final body = jsonDecode(response.body);
      if (body is Map<String, dynamic>) return body;
      return null;
    } catch (_) {
      return null;
    }
  }

  String _extractErrorMessage(String body) {
    if (body.trim().isEmpty) return '';
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map) {
        final error = decoded['error'];
        if (error is Map) {
          final msg = (error['message'] as String?)?.trim() ?? '';
          if (msg.isNotEmpty) return msg;
        }
        final msg = (decoded['message'] as String?)?.trim() ?? '';
        if (msg.isNotEmpty) return msg;
      }
    } catch (_) {
      // ignore
    }
    final trimmed = body.trim();
    if (trimmed.length <= 160) return trimmed;
    return '${trimmed.substring(0, 160)}...';
  }

  OpenClawRemoteStreamEvent? _parseSseFrame(String frame) {
    if (frame.trim().isEmpty) return null;
    var eventName = '';
    final dataLines = <String>[];
    for (final rawLine in frame.split('\n')) {
      final line = rawLine.trimRight();
      if (line.startsWith('event:')) {
        eventName = line.substring('event:'.length).trim();
      } else if (line.startsWith('data:')) {
        dataLines.add(line.substring('data:'.length).trim());
      }
    }
    if (dataLines.isEmpty) return null;
    final payloadRaw = dataLines.join('\n');
    final decoded = _tryDecodeMap(payloadRaw);

    if (eventName == 'trace') {
      if (decoded != null) {
        return OpenClawRemoteStreamEvent.trace(
          AssistantTraceEvent.fromJson(decoded),
        );
      }
      return null;
    }
    if (eventName == 'user_event' ||
        eventName == 'process_replace' ||
        eventName == 'process_append' ||
        eventName == 'process_commit') {
      final eventJson = decoded != null
          ? <String, dynamic>{
              if (decoded.containsKey('type'))
                ...decoded
              else ...<String, dynamic>{
                'type': eventName == 'user_event'
                    ? (decoded['type'] as String? ?? 'process_append')
                    : eventName,
                'scope': (decoded['scope'] as String? ?? 'root'),
                'message': (decoded['message'] as String?)?.trim() ?? payloadRaw,
                'nodeId': (decoded['nodeId'] as String? ?? ''),
                'runId': (decoded['runId'] as String? ?? ''),
                'payload':
                    (decoded['payload'] as Map?)?.cast<String, dynamic>() ??
                    decoded,
              },
            }
          : <String, dynamic>{
              'type': eventName == 'user_event' ? 'process_append' : eventName,
              'scope': 'root',
              'message': payloadRaw,
              'payload': const <String, dynamic>{},
            };
      return OpenClawRemoteStreamEvent.userEvent(UserEvent.fromJson(eventJson));
    }
    if (eventName == 'answer_delta') {
      if (decoded != null &&
          (decoded['scope'] != null || decoded['type'] != null)) {
        final eventJson = <String, dynamic>{
          'type': 'answer_delta',
          'scope': (decoded['scope'] as String? ?? 'aggregation'),
          'message':
              (decoded['message'] as String?)?.trim() ??
              (decoded['text'] as String?)?.trim() ??
              '',
          'nodeId': (decoded['nodeId'] as String? ?? ''),
          'runId': (decoded['runId'] as String? ?? ''),
          'payload':
              (decoded['payload'] as Map?)?.cast<String, dynamic>() ?? decoded,
        };
        return OpenClawRemoteStreamEvent.userEvent(UserEvent.fromJson(eventJson));
      }
      final chunk = decoded != null
          ? ((decoded['chunk'] as String?)?.trim().isNotEmpty == true
                ? (decoded['chunk'] as String)
                : ((decoded['text'] as String?) ?? payloadRaw))
          : payloadRaw;
      if (chunk.isNotEmpty) {
        return OpenClawRemoteStreamEvent.chunk(chunk);
      }
      return null;
    }
    if (eventName == 'chunk' || eventName == 'delta' || eventName == 'token') {
      if (decoded != null) {
        final chunk = (decoded['chunk'] as String?)?.trim().isNotEmpty == true
            ? (decoded['chunk'] as String)
            : ((decoded['text'] as String?) ?? '');
        if (chunk.isNotEmpty) return OpenClawRemoteStreamEvent.chunk(chunk);
      }
      return OpenClawRemoteStreamEvent.chunk(payloadRaw);
    }
    if (eventName == 'final' || eventName == 'completed') {
      if (decoded != null) {
        return OpenClawRemoteStreamEvent.completed(
          AssistantRunResponse.fromJson(decoded),
        );
      }
      return OpenClawRemoteStreamEvent.failed(
        'remote completed payload is not valid json',
      );
    }
    if (decoded != null && decoded.containsKey('finalText')) {
      return OpenClawRemoteStreamEvent.completed(
        AssistantRunResponse.fromJson(decoded),
      );
    }
    return null;
  }

  Map<String, dynamic>? _tryDecodeMap(String body) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map<String, dynamic>) return decoded;
      if (decoded is Map) return decoded.cast<String, dynamic>();
      return null;
    } catch (_) {
      return null;
    }
  }

  Future<Map<String, dynamic>> invokeSkillLocally({
    required String skillId,
    required Map<String, dynamic> arguments,
    String deviceProfile = 'mobile',
  }) async {
    final gateway = _localGateway;
    if (gateway == null) {
      return <String, dynamic>{
        'success': false,
        'message': 'local gateway not bound',
      };
    }
    final result = await gateway.invokeSkill(
      skillId: skillId,
      arguments: arguments,
      deviceProfile: deviceProfile,
    );
    return result.toJson();
  }

  Future<AssistantRunResponse?> runLocal(AssistantRunRequest request) async {
    final gateway = _localGateway;
    if (gateway == null) return null;
    return gateway.run(request);
  }

  /// Simulate Feishu voice command text routing through OpenClaw.
  Future<String?> handleVoiceCommandForKnowledgeQa(String voiceText) async {
    final trimmed = voiceText.trim();
    if (trimmed.isEmpty) return null;
    final result = await invokeSkillRemote(
      skillId: 'web.quick_search',
      arguments: <String, dynamic>{
        'toolName': 'web_search',
        'toolArgs': <String, dynamic>{'query': trimmed},
      },
    );
    if (result == null) {
      return 'bridge invoke unavailable';
    }
    final success = result['success'] == true;
    if (!success) {
      return result['message']?.toString();
    }
    return result['message']?.toString();
  }
}
