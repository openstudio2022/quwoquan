import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/personal_assistant/app/assistant_gateway.dart';
import 'package:quwoquan_app/personal_assistant/contracts/user_events.dart';
import 'package:quwoquan_app/personal_assistant/engine/process_journal_bus.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';

class AssistantHttpGateway {
  AssistantHttpGateway({
    required AssistantGateway gateway,
    this.port = 18181,
    String? authToken,
  })  : _gateway = gateway,
        authToken =
            authToken ?? const String.fromEnvironment('PERSONAL_ASSISTANT_GATEWAY_TOKEN');

  final AssistantGateway _gateway;
  final int port;
  final String authToken;
  HttpServer? _server;
  final _SimpleRateLimiter _rateLimiter = _SimpleRateLimiter();

  Future<void> start() async {
    _server ??= await HttpServer.bind(InternetAddress.loopbackIPv4, port);
    _server!.listen(_handleRequest);
  }

  Future<void> stop() async {
    await _server?.close(force: true);
    _server = null;
  }

  Future<void> _handleRequest(HttpRequest request) async {
    try {
      final requestId = DateTime.now().microsecondsSinceEpoch.toString();
      final auditKey = _auditKey(request);
      if (!_isAuthorized(request)) {
        request.response.statusCode = HttpStatus.unauthorized;
        request.response.write(jsonEncode(<String, dynamic>{'error': 'unauthorized'}));
        _audit('unauthorized', requestId, request, auditKey, HttpStatus.unauthorized);
        await request.response.close();
        return;
      }
      if (!_rateLimiter.allow(auditKey)) {
        request.response.statusCode = HttpStatus.tooManyRequests;
        request.response.headers.contentType = ContentType.json;
        request.response.write(
          jsonEncode(
            <String, dynamic>{
              'error': 'rate_limited',
              'message': 'too many requests',
            },
          ),
        );
        _audit('rate_limited', requestId, request, auditKey, HttpStatus.tooManyRequests);
        await request.response.close();
        return;
      }
      final method = request.method.toUpperCase();
      final path = request.uri.path;
      if (method == 'GET' && path == '/v1/skills') {
        final channel = request.uri.queryParameters['channel'];
        final skills = channel == null || channel.trim().isEmpty
            ? await _gateway.listSkills()
            : await _gateway.listSkillsByChannel(channel.trim());
        request.response.headers.contentType = ContentType.json;
        request.response.write(
          jsonEncode(
            skills
                .map((s) => <String, dynamic>{
                      'id': s.manifest.id,
                      'name': s.manifest.name,
                      'description': s.manifest.description,
                      'executionTarget': s.manifest.executionTarget,
                      'enabled': s.enabled,
                      'visibility': s.manifest.visibility,
                      'tier': s.tier,
                      'channelScopes': s.manifest.channelScopes,
                      'deviceScopes': s.manifest.deviceScopes,
                      'defaultFree': s.isDefaultFree,
                    })
                .toList(growable: false),
          ),
        );
        _audit('list_skills', requestId, request, auditKey, HttpStatus.ok);
        await request.response.close();
        return;
      }
      if (method == 'GET' && path == '/v1/sessions') {
        final sessions = await _gateway.listSessions();
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode(sessions));
        _audit('list_sessions', requestId, request, auditKey, HttpStatus.ok);
        await request.response.close();
        return;
      }
      if (method == 'GET' && path.startsWith('/v1/sessions/')) {
        final sessionId = path.replaceFirst('/v1/sessions/', '').trim();
        if (sessionId.isEmpty) {
          request.response.statusCode = HttpStatus.badRequest;
          request.response.headers.contentType = ContentType.json;
          request.response.write(jsonEncode(<String, dynamic>{'error': 'invalid_session_id'}));
          await request.response.close();
          return;
        }
        final detail = await _gateway.sessionDetail(sessionId);
        if (detail == null) {
          request.response.statusCode = HttpStatus.notFound;
          request.response.headers.contentType = ContentType.json;
          request.response.write(jsonEncode(<String, dynamic>{'error': 'session_not_found'}));
          await request.response.close();
          return;
        }
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode(detail));
        _audit('session_detail', requestId, request, auditKey, HttpStatus.ok);
        await request.response.close();
        return;
      }
      if (method == 'POST' && path == '/v1/skills/invoke') {
        final body = await utf8.decoder.bind(request).join();
        final json = (jsonDecode(body) as Map).cast<String, dynamic>();
        final skillId = (json['skill_id'] as String?) ?? '';
        if (skillId.trim().isEmpty) {
          request.response.statusCode = HttpStatus.badRequest;
          request.response.headers.contentType = ContentType.json;
          request.response.write(
            jsonEncode(
              <String, dynamic>{'error': 'invalid_request', 'message': 'skill_id is required'},
            ),
          );
          _audit('invoke_skill_invalid', requestId, request, auditKey, HttpStatus.badRequest);
          await request.response.close();
          return;
        }
        final args = (json['arguments'] as Map?)?.cast<String, dynamic>() ?? <String, dynamic>{};
        final deviceProfile = (json['deviceProfile'] as String?) ?? 'mobile';
        final channel = (json['channel'] as String?) ?? 'app';
        final result = await _gateway.invokeSkill(
          skillId: skillId,
          arguments: args,
          deviceProfile: deviceProfile,
          channel: channel,
        );
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode(result.toJson()));
        _audit('invoke_skill', requestId, request, auditKey, HttpStatus.ok);
        await request.response.close();
        return;
      }
      if (method == 'POST' && path == '/v1/run') {
        final body = await utf8.decoder.bind(request).join();
        final json = (jsonDecode(body) as Map).cast<String, dynamic>();
        final rawMessages = (json['messages'] as List?) ?? const <dynamic>[];
        if (rawMessages.isEmpty) {
          request.response.statusCode = HttpStatus.badRequest;
          request.response.headers.contentType = ContentType.json;
          request.response.write(
            jsonEncode(
              <String, dynamic>{'error': 'invalid_request', 'message': 'messages is required'},
            ),
          );
          _audit('run_invalid', requestId, request, auditKey, HttpStatus.badRequest);
          await request.response.close();
          return;
        }
        final messages = rawMessages
            .whereType<Map>()
            .map(
              (m) => AssistantRunMessage(
                role: m['role']?.toString() ?? 'user',
                content: m['content']?.toString() ?? '',
              ),
            )
            .toList(growable: false);
        final response = await _gateway.run(
          AssistantRunRequest(
            messages: messages,
            sessionId: json['sessionId'] as String?,
            userId: json['userId'] as String?,
            deviceProfile: (json['deviceProfile'] as String?) ?? 'mobile',
            channel: (json['channel'] as String?) ?? 'app',
            traceId: json['traceId'] as String?,
            maxIterations: (json['maxIterations'] as int?) ?? 6,
          ),
        );
        final includeTraces = json['includeTraces'] == true;
        final payload = response.toJson();
        if (!includeTraces) {
          payload.remove('traces');
        }
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode(payload));
        _audit('run', requestId, request, auditKey, HttpStatus.ok);
        await request.response.close();
        return;
      }
      if (method == 'POST' && path == '/v1/run/stream') {
        final body = await utf8.decoder.bind(request).join();
        final json = (jsonDecode(body) as Map).cast<String, dynamic>();
        final rawMessages = (json['messages'] as List?) ?? const <dynamic>[];
        final messages = rawMessages
            .whereType<Map>()
            .map(
              (m) => AssistantRunMessage(
                role: m['role']?.toString() ?? 'user',
                content: m['content']?.toString() ?? '',
              ),
            )
            .toList(growable: false);
        request.response.headers.set(HttpHeaders.contentTypeHeader, 'text/event-stream');
        request.response.headers.set(HttpHeaders.cacheControlHeader, 'no-cache');
        request.response.bufferOutput = false;
        final journalBus = ProcessJournalBus(
          userGoalSummary: _latestUserMessage(messages),
        );
        final runRequest = AssistantRunRequest(
          messages: messages,
          sessionId: json['sessionId'] as String?,
          userId: json['userId'] as String?,
          deviceProfile: (json['deviceProfile'] as String?) ?? 'mobile',
          channel: (json['channel'] as String?) ?? 'app',
          traceId: json['traceId'] as String?,
          maxIterations: (json['maxIterations'] as int?) ?? 6,
        );
        final response = await _gateway.runWithTraceStream(
          runRequest,
          onTraceEvent: (trace) {
            final journalEvents = journalBus.consumeTrace(trace);
            final legacyEvents = ProcessJournalBus.toLegacyUserEvents(journalEvents);
            for (final event in legacyEvents) {
              final eventName = event.type == UserEventType.answerDelta
                  ? 'answer_delta'
                  : 'user_event';
              request.response.write('event: $eventName\n');
              request.response.write('data: ${jsonEncode(event.toJson())}\n\n');
            }
          },
        );
        request.response.write('event: final\n');
        final responseJson = response.toJson()..remove('traces');
        request.response.write(
          'data: ${jsonEncode(responseJson)}\n\n',
        );
        await request.response.close();
        _audit('run_stream', requestId, request, auditKey, HttpStatus.ok);
        return;
      }
      request.response.statusCode = HttpStatus.notFound;
      _audit('not_found', requestId, request, auditKey, HttpStatus.notFound);
      await request.response.close();
    } catch (error) {
      request.response.statusCode = HttpStatus.internalServerError;
      request.response.write(jsonEncode(<String, dynamic>{'error': '$error'}));
      _audit('internal_error', DateTime.now().microsecondsSinceEpoch.toString(), request,
          _auditKey(request), HttpStatus.internalServerError);
      await request.response.close();
    }
  }

  bool _isAuthorized(HttpRequest request) {
    if (authToken.isEmpty) return true;
    final token = request.headers.value(HttpHeaders.authorizationHeader) ?? '';
    return token.trim() == 'Bearer $authToken';
  }

  String _auditKey(HttpRequest request) {
    final token = request.headers.value(HttpHeaders.authorizationHeader) ?? '';
    if (token.isNotEmpty) return token;
    return request.connectionInfo?.remoteAddress.address ?? 'unknown';
  }

  void _audit(
    String event,
    String requestId,
    HttpRequest request,
    String actor,
    int statusCode,
  ) {
    stdout.writeln(
      '[assistant_gateway] event=$event requestId=$requestId method=${request.method} path=${request.uri.path} actor=$actor status=$statusCode',
    );
  }

  static String _latestUserMessage(List<AssistantRunMessage> messages) {
    for (var i = messages.length - 1; i >= 0; i--) {
      final item = messages[i];
      if (item.role == 'user' && item.content.trim().isNotEmpty) {
        return item.content.trim();
      }
    }
    return '';
  }
}

class _SimpleRateLimiter {
  _SimpleRateLimiter();

  static const int maxRequestsPerMinute = 30;
  final Map<String, List<int>> _history = <String, List<int>>{};

  bool allow(String key) {
    final now = DateTime.now().millisecondsSinceEpoch;
    final windowStart = now - const Duration(minutes: 1).inMilliseconds;
    final events = _history.putIfAbsent(key, () => <int>[]);
    events.removeWhere((ts) => ts < windowStart);
    if (events.length >= maxRequestsPerMinute) {
      return false;
    }
    events.add(now);
    return true;
  }
}
