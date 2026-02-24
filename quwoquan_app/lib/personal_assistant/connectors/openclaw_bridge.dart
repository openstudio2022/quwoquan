import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/personal_assistant/app/assistant_gateway.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_response.dart';

class OpenClawBridge {
  OpenClawBridge({
    required this.baseUrl,
    this.authToken,
  });

  final String baseUrl;
  final String? authToken;
  AssistantGateway? _localGateway;

  bool get isRemoteConfigured => baseUrl.trim().isNotEmpty;

  void bindLocalGateway(AssistantGateway gateway) {
    _localGateway = gateway;
  }

  Map<String, String> _headers() {
    final headers = <String, String>{
      'Content-Type': 'application/json',
    };
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
          'messages': request.messages.map((m) => m.toJson()).toList(growable: false),
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
        'toolArgs': <String, dynamic>{
          'query': trimmed,
        },
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
