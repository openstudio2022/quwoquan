import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/personal_assistant/app/assistant_gateway.dart';
import 'package:quwoquan_app/personal_assistant/cost/assistent_cost_ledger.dart';
import 'package:quwoquan_app/personal_assistant/cost/assistent_token_meter.dart';
import 'package:quwoquan_app/personal_assistant/observability/assistent_alert_dispatcher.dart';
import 'package:quwoquan_app/personal_assistant/observability/assistent_slo_monitor.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_run_interaction_collector.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/providers/assistent_provider_health.dart';
import 'package:quwoquan_app/personal_assistant/providers/assistent_provider_policy.dart';
import 'package:quwoquan_app/personal_assistant/providers/assistent_provider_registry.dart';
import 'package:quwoquan_app/personal_assistant/security/assistent_audit_logger.dart';
import 'package:quwoquan_app/personal_assistant/security/assistent_auth_acl.dart';
import 'package:quwoquan_app/personal_assistant/spi/assistent_adapter_runtime.dart';

class AssistentApiGateway {
  AssistentApiGateway({
    required AssistantGateway assistantGateway,
    required AssistentProviderRegistry providerRegistry,
    required AssistentProviderPolicy providerPolicy,
    required AssistentProviderHealthService providerHealthService,
    required AssistentSloMonitor sloMonitor,
    required AssistentAlertDispatcher alertDispatcher,
    required AssistentCostLedger costLedger,
    required AssistentAuditLogger auditLogger,
    required AssistentAuthAcl authAcl,
    required AssistentAdapterRuntime adapterRuntime,
    this.port = 19191,
    String? authToken,
  }) : _assistantGateway = assistantGateway,
       _providerRegistry = providerRegistry,
       _providerPolicy = providerPolicy,
       _providerHealthService = providerHealthService,
       _sloMonitor = sloMonitor,
       _alertDispatcher = alertDispatcher,
       _costLedger = costLedger,
       _auditLogger = auditLogger,
       _authAcl = authAcl,
       _adapterRuntime = adapterRuntime,
       _authToken =
           authToken ??
           const String.fromEnvironment('PERSONAL_ASSISTANT_GATEWAY_TOKEN');

  final AssistantGateway _assistantGateway;
  final AssistentProviderRegistry _providerRegistry;
  final AssistentProviderPolicy _providerPolicy;
  final AssistentProviderHealthService _providerHealthService;
  final AssistentSloMonitor _sloMonitor;
  final AssistentAlertDispatcher _alertDispatcher;
  final AssistentCostLedger _costLedger;
  final AssistentAuditLogger _auditLogger;
  final AssistentAuthAcl _authAcl;
  final AssistentAdapterRuntime _adapterRuntime;
  final int port;
  final String _authToken;
  final AssistentTokenMeter _tokenMeter = const AssistentTokenMeter();
  final Duration _autoDisableDuration = Duration(
    minutes: const int.fromEnvironment(
      'ASSISTENT_ALERT_AUTO_DISABLE_MINUTES',
      defaultValue: 10,
    ),
  );
  HttpServer? _server;

  Future<void> start() async {
    _server ??= await HttpServer.bind(InternetAddress.loopbackIPv4, port);
    _server!.listen(_handleRequest);
  }

  Future<void> stop() async {
    await _server?.close(force: true);
    _server = null;
  }

  Future<void> _handleRequest(HttpRequest request) async {
    final requestId = DateTime.now().microsecondsSinceEpoch.toString();
    final path = request.uri.path;
    final method = request.method.toUpperCase();
    try {
      if (!_authorize(request)) {
        await _writeJson(
          request: request,
          statusCode: HttpStatus.unauthorized,
          data: <String, dynamic>{'error': 'unauthorized'},
        );
        return;
      }
      if (method == 'GET' && path == '/v1/assistent/providers') {
        final providers = _providerRegistry.listWithRuntimeState();
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{'providers': providers},
        );
        return;
      }
      if (method == 'POST' &&
          path.startsWith('/v1/assistent/providers/') &&
          path.endsWith('/recover')) {
        final parts = path.split('/');
        if (parts.length < 5) {
          await _writeJson(
            request: request,
            statusCode: HttpStatus.badRequest,
            data: <String, dynamic>{'error': 'invalid_provider_path'},
          );
          return;
        }
        final providerId = parts[4];
        _providerRegistry.clearTemporaryDisable(providerId);
        await _auditLogger.write(
          AssistentAuditLog(
            event: 'provider_manual_recover',
            actor: 'assistent_operator',
            channel: 'system',
            runId: 'manual',
            traceId: 'manual',
            statusCode: HttpStatus.ok,
            timestamp: DateTime.now(),
            metadata: <String, dynamic>{'providerId': providerId},
          ),
        );
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{'ok': true, 'providerId': providerId},
        );
        return;
      }
      if (method == 'GET' && path == '/v1/assistent/adapters') {
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{'adapters': _adapterRuntime.listAdapterIds()},
        );
        return;
      }
      if (method == 'GET' && path == '/v1/assistent/costs') {
        final summary = await _costLedger.summary();
        final recent = await _costLedger.listRecent(limit: 50);
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{
            'summary': summary.toJson(),
            'recent': recent
                .map((record) => record.toJson())
                .toList(growable: false),
          },
        );
        return;
      }
      if (method == 'GET' && path == '/v1/assistent/alerts') {
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{
            'alerts': _alertDispatcher
                .listRecent(limit: 100)
                .map((alert) => alert.toJson())
                .toList(growable: false),
          },
        );
        return;
      }
      if (method == 'GET' && path == '/v1/assistent/alerts/config') {
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{'routing': _alertDispatcher.routingConfig()},
        );
        return;
      }
      if (method == 'POST' && path == '/v1/assistent/logs/export') {
        final payload = await _decodeBody(request);
        final targetDirectory =
            (payload['targetDirectory'] as String?)?.trim().isNotEmpty == true
            ? (payload['targetDirectory'] as String).trim()
            : '/Users/zhaoyuxi/Projects/quwoquan/quwoquan_app/app_log';
        final result = await _assistantGateway.exportLogsToWorkspace(
          targetDirectory: targetDirectory,
        );
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{'ok': true, 'result': result.toJson()},
        );
        return;
      }
      if (method == 'POST' && path == '/v1/assistent/logs/boost') {
        final payload = await _decodeBody(request);
        final sessionId = (payload['sessionId'] as String?)?.trim() ?? '';
        final runId = (payload['runId'] as String?)?.trim() ?? '';
        final clear = payload['clear'] == true;
        if (clear) {
          AppLogService.instance.clearBoosts();
        } else {
          if (sessionId.isNotEmpty) {
            AppLogService.instance.boostSession(sessionId);
          }
          if (runId.isNotEmpty) {
            AppLogService.instance.boostRun(runId);
          }
        }
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{
            'ok': true,
            'clear': clear,
            'sessionId': sessionId,
            'runId': runId,
          },
        );
        return;
      }
      if (method == 'POST' && path == '/v1/assistent/alerts/test') {
        final payload = await _decodeBody(request);
        final severityRaw =
            (payload['severity'] as String?)?.trim().toLowerCase() ?? 'warning';
        final severity = severityRaw == 'critical'
            ? AssistentSloAlertSeverity.critical
            : AssistentSloAlertSeverity.warning;
        final providerId =
            (payload['providerId'] as String?)?.trim().isNotEmpty == true
            ? (payload['providerId'] as String).trim()
            : 'synthetic_provider';
        final message =
            (payload['message'] as String?)?.trim().isNotEmpty == true
            ? (payload['message'] as String).trim()
            : 'synthetic alert for routing verification';
        final alert = await _alertDispatcher.dispatchSynthetic(
          providerId: providerId,
          severity: severity,
          message: message,
        );
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{'ok': true, 'alert': alert.toJson()},
        );
        return;
      }
      if (method == 'GET' && path == '/v1/assistent/skills') {
        final channel = request.uri.queryParameters['channel'] ?? 'app';
        final skills = await _assistantGateway.listSkillsByChannel(channel);
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{
            'skills': skills
                .map(
                  (s) => <String, dynamic>{
                    'id': s.manifest.id,
                    'name': s.manifest.name,
                    'description': s.manifest.description,
                    'tier': s.tier,
                    'enabled': s.enabled,
                    'channelScopes': s.manifest.channelScopes,
                    'deviceScopes': s.manifest.deviceScopes,
                  },
                )
                .toList(growable: false),
          },
        );
        return;
      }
      if (method == 'GET' && path == '/v1/assistent/sessions') {
        final sessions = await _assistantGateway.listSessions();
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{'sessions': sessions},
        );
        return;
      }
      if (method == 'POST' && path == '/v1/assistent/skills/invoke') {
        final payload = await _decodeBody(request);
        final skillId = (payload['skill_id'] as String?)?.trim() ?? '';
        final actor = (payload['userId'] as String?)?.trim() ?? 'external';
        final channel = (payload['channel'] as String?)?.trim() ?? 'app';
        final acl = _authAcl.allow(
          AssistentAccessContext(
            channel: channel,
            actorId: actor,
            resource: 'skills/$skillId',
            action: 'invoke',
          ),
        );
        if (!acl || skillId.isEmpty) {
          await _writeJson(
            request: request,
            statusCode: HttpStatus.forbidden,
            data: <String, dynamic>{'error': 'forbidden'},
          );
          return;
        }
        final result = await _assistantGateway.invokeSkill(
          skillId: skillId,
          arguments:
              (payload['arguments'] as Map?)?.cast<String, dynamic>() ??
              <String, dynamic>{},
          deviceProfile:
              (payload['deviceProfile'] as String?)?.trim() ?? 'mobile',
          channel: channel,
        );
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{
            'runId': requestId,
            'traceId': payload['traceId'] ?? requestId,
            ...result.toJson(),
          },
        );
        return;
      }
      if (method == 'POST' && path == '/v1/assistent/runs') {
        final payload = await _decodeBody(request);
        final messages = ((payload['messages'] as List?) ?? const <dynamic>[])
            .whereType<Map>()
            .map(
              (m) => AssistantRunMessage(
                role: m['role']?.toString() ?? 'user',
                content: m['content']?.toString() ?? '',
              ),
            )
            .toList(growable: false);
        if (messages.isEmpty) {
          await _writeJson(
            request: request,
            statusCode: HttpStatus.badRequest,
            data: <String, dynamic>{'error': 'messages_required'},
          );
          return;
        }
        final runReq = AssistantRunRequest(
          messages: messages,
          sessionId: payload['sessionId'] as String?,
          userId: payload['userId'] as String?,
          channel: (payload['channel'] as String?) ?? 'app',
          deviceProfile: (payload['deviceProfile'] as String?) ?? 'mobile',
          traceId: payload['traceId'] as String?,
          maxIterations: (payload['maxIterations'] as int?) ?? 8,
          capabilityCatalog:
              (payload['capabilityCatalog'] as List?)
                  ?.whereType<String>()
                  .map((item) => item.trim())
                  .where((item) => item.isNotEmpty)
                  .toList(growable: false) ??
              const <String>[],
          contextScopeHint:
              (payload['contextScopeHint'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
          privacyProfile:
              (payload['privacyProfile'] as String?)?.trim().isNotEmpty == true
              ? (payload['privacyProfile'] as String).trim()
              : 'default',
          privacyPolicy:
              (payload['privacyPolicy'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
        );
        final selectedProvider = await _selectProviderForRun(runReq);
        if (selectedProvider != null) {
          _assistantGateway.switchModel(selectedProvider.id);
        }
        final runStartedAt = DateTime.now();
        final runRes = await _assistantGateway.run(runReq);
        final elapsedMs = DateTime.now()
            .difference(runStartedAt)
            .inMilliseconds;
        final providerId =
            selectedProvider?.id ??
            _assistantGateway.currentModel() ??
            'local_heuristic';
        _sloMonitor.record(
          providerId: providerId,
          latencyMs: elapsedMs,
          success: !runRes.degraded,
        );
        final alert = _sloMonitor.evaluateAlert(
          providerId: providerId,
          windowMinutes: 5,
        );
        if (alert != null) {
          await _alertDispatcher.dispatch(alert);
          if (alert.severity == AssistentSloAlertSeverity.critical) {
            _providerRegistry.disableTemporarily(
              providerId: providerId,
              duration: _autoDisableDuration,
            );
            await _auditLogger.write(
              AssistentAuditLog(
                event: 'provider_auto_disabled',
                actor: 'assistent_system',
                channel: runReq.channel,
                runId: runRes.runId ?? requestId,
                traceId: runRes.traceId ?? requestId,
                statusCode: HttpStatus.ok,
                timestamp: DateTime.now(),
                metadata: <String, dynamic>{
                  'providerId': providerId,
                  'disabledMinutes': _autoDisableDuration.inMinutes,
                  'reason': alert.message,
                },
              ),
            );
          }
        }
        final usage = _tokenMeter.estimate(
          inputText: messages.map((m) => m.content).join('\n'),
          outputText: runRes.finalText,
        );
        await _costLedger.append(
          AssistentCostRecord(
            runId: runRes.runId ?? requestId,
            traceId: runRes.traceId ?? requestId,
            provider: providerId,
            modelRef: _assistantGateway.currentModel() ?? 'local',
            tokenUsage: usage.totalTokens,
            estimatedCostUsd: usage.totalTokens * 0.000002,
            timestamp: DateTime.now(),
          ),
        );
        await _auditLogger.write(
          AssistentAuditLog(
            event: 'assistent_run',
            actor: runReq.userId ?? 'external',
            channel: runReq.channel,
            runId: runRes.runId ?? requestId,
            traceId: runRes.traceId ?? requestId,
            statusCode: HttpStatus.ok,
            timestamp: DateTime.now(),
          ),
        );
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{
            'runId': runRes.runId ?? requestId,
            'traceId': runRes.traceId ?? requestId,
            'finalText': runRes.finalText,
            'degraded': runRes.degraded,
            'errorCode': runRes.errorCode,
            'provider': providerId,
            'slo': _sloMonitor
                .snapshotForProvider(providerId: providerId)
                .toJson(),
            'traces': runRes.traces
                .map((e) => e.toJson())
                .toList(growable: false),
          },
        );
        return;
      }
      if (method == 'POST' && path == '/v1/assistent/runs/stream') {
        final payload = await _decodeBody(request);
        final messages = ((payload['messages'] as List?) ?? const <dynamic>[])
            .whereType<Map>()
            .map(
              (m) => AssistantRunMessage(
                role: m['role']?.toString() ?? 'user',
                content: m['content']?.toString() ?? '',
              ),
            )
            .toList(growable: false);
        final runReq = AssistantRunRequest(
          messages: messages,
          sessionId: payload['sessionId'] as String?,
          userId: payload['userId'] as String?,
          channel: (payload['channel'] as String?) ?? 'app',
          deviceProfile: (payload['deviceProfile'] as String?) ?? 'mobile',
          traceId: payload['traceId'] as String?,
          maxIterations: (payload['maxIterations'] as int?) ?? 8,
          capabilityCatalog:
              (payload['capabilityCatalog'] as List?)
                  ?.whereType<String>()
                  .map((item) => item.trim())
                  .where((item) => item.isNotEmpty)
                  .toList(growable: false) ??
              const <String>[],
          contextScopeHint:
              (payload['contextScopeHint'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
          privacyProfile:
              (payload['privacyProfile'] as String?)?.trim().isNotEmpty == true
              ? (payload['privacyProfile'] as String).trim()
              : 'default',
          privacyPolicy:
              (payload['privacyPolicy'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
        );
        final runRes = await _assistantGateway.run(runReq);
        request.response.headers.set(
          HttpHeaders.contentTypeHeader,
          'text/event-stream',
        );
        request.response.headers.set(
          HttpHeaders.cacheControlHeader,
          'no-cache',
        );
        for (final trace in runRes.traces) {
          request.response.write('event: trace\n');
          request.response.write('data: ${jsonEncode(trace.toJson())}\n\n');
        }
        request.response.write('event: final\n');
        request.response.write(
          'data: ${jsonEncode(<String, dynamic>{"runId": runRes.runId, "traceId": runRes.traceId, "finalText": runRes.finalText, "degraded": runRes.degraded, "errorCode": runRes.errorCode})}\n\n',
        );
        await request.response.close();
        return;
      }
      if (method == 'POST' && path.startsWith('/v1/assistent/channels/')) {
        final parts = path.split('/');
        final adapterId = parts.isNotEmpty ? parts.last : '';
        if (adapterId.trim().isEmpty) {
          await _writeJson(
            request: request,
            statusCode: HttpStatus.badRequest,
            data: <String, dynamic>{'error': 'adapter_id_required'},
          );
          return;
        }
        final rawBody = await utf8.decoder.bind(request).join();
        final headers = <String, String>{};
        request.headers.forEach((name, values) {
          if (values.isNotEmpty) headers[name.toLowerCase()] = values.first;
        });
        final event = await _adapterRuntime.parseIncoming(
          adapterId: adapterId,
          headers: headers,
          rawBody: rawBody,
        );
        if (event == null) {
          await _writeJson(
            request: request,
            statusCode: HttpStatus.unauthorized,
            data: <String, dynamic>{'error': 'adapter_verify_failed'},
          );
          return;
        }
        final text = event.payload['text']?.toString() ?? '';
        final runReq = AssistantRunRequest(
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: text),
          ],
          sessionId:
              'channel_${adapterId}_${DateTime.now().millisecondsSinceEpoch}',
          userId: 'channel_user',
          channel: adapterId,
          deviceProfile: 'pc',
          maxIterations: 8,
        );
        final runRes = await _assistantGateway.run(runReq);
        final dispatch = await _adapterRuntime.dispatch(
          adapterId: adapterId,
          sourceEvent: event,
          responseEnvelope: <String, dynamic>{
            'runId': runRes.runId,
            'traceId': runRes.traceId,
            'finalText': runRes.finalText,
            'degraded': runRes.degraded,
            'errorCode': runRes.errorCode,
          },
        );
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{
            'adapter': adapterId,
            'runId': runRes.runId,
            'traceId': runRes.traceId,
            'finalText': runRes.finalText,
            'dispatch': dispatch?.payload ?? <String, dynamic>{},
          },
        );
        return;
      }
      await _writeJson(
        request: request,
        statusCode: HttpStatus.notFound,
        data: <String, dynamic>{'error': 'not_found'},
      );
    } catch (error) {
      await _writeJson(
        request: request,
        statusCode: HttpStatus.internalServerError,
        data: <String, dynamic>{'error': '$error'},
      );
    }
  }

  bool _authorize(HttpRequest request) {
    if (_authToken.isEmpty) return true;
    final token = request.headers.value(HttpHeaders.authorizationHeader) ?? '';
    return token.trim() == 'Bearer $_authToken';
  }

  Future<Map<String, dynamic>> _decodeBody(HttpRequest request) async {
    final body = await utf8.decoder.bind(request).join();
    final decoded = jsonDecode(body);
    if (decoded is Map<String, dynamic>) return decoded;
    if (decoded is Map) return decoded.cast<String, dynamic>();
    return <String, dynamic>{};
  }

  Future<void> _writeJson({
    required HttpRequest request,
    required int statusCode,
    required Map<String, dynamic> data,
  }) async {
    request.response.statusCode = statusCode;
    request.response.headers.contentType = ContentType.json;
    request.response.write(jsonEncode(data));
    await request.response.close();
    final runId = (data['runId'] as String?)?.trim() ?? '';
    final traceId = (data['traceId'] as String?)?.trim() ?? '';
    final payload = <String, dynamic>{
      'kind': 'cloud_api',
      'request': <String, dynamic>{
        'method': request.method.toUpperCase(),
        'path': request.uri.path,
        'query': request.uri.queryParameters,
        'headers': _flattenHeaders(request.headers),
      },
      'response': <String, dynamic>{'statusCode': statusCode, 'body': data},
    };
    if (runId.isNotEmpty) {
      AppRunInteractionCollector.instance.add(
        runId: runId,
        interaction: <String, dynamic>{
          'ts': DateTime.now().toIso8601String(),
          ...payload,
        },
      );
    }
    await AppLogService.instance.writeEvent(
      logType: AppLogType.cloudApi,
      level: statusCode >= 400 ? AppLogLevel.error : AppLogLevel.info,
      context: AppLogContext(
        sessionId: AppTraceContextStore.instance.sessionId,
        runId: runId,
        traceId: traceId,
        requestId: AppTraceContextStore.instance.newRequestId(),
      ),
      payload: payload,
      summaryPayload: <String, dynamic>{
        'kind': 'cloud_api',
        'method': request.method.toUpperCase(),
        'path': request.uri.path,
        'statusCode': statusCode,
      },
      hasError: statusCode >= 400,
    );
  }

  Map<String, String> _flattenHeaders(HttpHeaders headers) {
    final out = <String, String>{};
    headers.forEach((name, values) {
      out[name] = values.join(';');
    });
    return out;
  }

  Future<AssistentProviderDescriptor?> _selectProviderForRun(
    AssistantRunRequest runReq,
  ) async {
    final candidates = _providerRegistry.list(
      type: AssistentProviderType.llm,
      enabled: true,
    );
    if (candidates.isEmpty) return null;
    for (final candidate in candidates) {
      await _providerHealthService.probe(candidate);
    }
    final healthMap = _providerHealthService.healthMap();
    final sloMap = <String, AssistentSloSnapshot>{};
    for (final candidate in candidates) {
      sloMap[candidate.id] = _sloMonitor.snapshotForProvider(
        providerId: candidate.id,
        windowMinutes: 5,
      );
    }
    final context = AssistentProviderRoutingContext(
      capability: 'run',
      channel: runReq.channel,
      deviceProfile: runReq.deviceProfile,
      latencySensitive: runReq.channel != 'app',
      costSensitive: runReq.channel == 'app',
      availabilityThreshold: 0.97,
    );
    return _providerPolicy.pickProvider(
      context: context,
      candidates: candidates,
      healthMap: healthMap,
      sloMap: sloMap,
    );
  }
}
