import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';
import 'package:quwoquan_app/assistant/cost/assistant_cost_ledger.dart';
import 'package:quwoquan_app/assistant/observability/assistant_observability_runtime.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_run_interaction_collector.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/providers/assistant_provider_runtime.dart';
import 'package:quwoquan_app/assistant/security/assistant_security_runtime.dart';
import 'package:quwoquan_app/assistant/spi/assistant_adapter_runtime.dart';

class AssistantApiGateway {
  AssistantApiGateway({
    required AssistantGateway assistantGateway,
    required AssistantProviderRegistry providerRegistry,
    required AssistantProviderPolicy providerPolicy,
    required AssistantProviderHealthService providerHealthService,
    required AssistantSloMonitor sloMonitor,
    required AssistantAlertDispatcher alertDispatcher,
    required AssistantCostLedger costLedger,
    required AssistantAuditLogger auditLogger,
    required AssistantAuthAcl authAcl,
    required AssistantAdapterRuntime adapterRuntime,
    this.port = 19191,
    this.authToken = '',
    Duration? autoDisableDuration,
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
       _autoDisableDuration =
           autoDisableDuration ?? const Duration(minutes: 10);

  final AssistantGateway _assistantGateway;
  final AssistantProviderRegistry _providerRegistry;
  final AssistantProviderPolicy _providerPolicy;
  final AssistantProviderHealthService _providerHealthService;
  final AssistantSloMonitor _sloMonitor;
  final AssistantAlertDispatcher _alertDispatcher;
  final AssistantCostLedger _costLedger;
  final AssistantAuditLogger _auditLogger;
  final AssistantAuthAcl _authAcl;
  final AssistantAdapterRuntime _adapterRuntime;
  final int port;
  final String authToken;
  final Duration _autoDisableDuration;
  final AssistantTokenMeter _tokenMeter = const AssistantTokenMeter();
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
      if (method == 'GET' && _matchesPath(path, '/v1/assistant/providers')) {
        final providers = _providerRegistry.listWithRuntimeState();
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{'providers': providers},
        );
        return;
      }
      if (method == 'GET' && _matchesPath(path, '/v1/assistant/models')) {
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{
            'currentModel': _assistantGateway.currentModel(),
            'selectedModels': _assistantGateway.selectedModels(),
            'availableModels': _assistantGateway.listAvailableModels(),
          },
        );
        return;
      }
      if (method == 'POST' &&
          _matchesPath(path, '/v1/assistant/models/select')) {
        final payload = await _decodeBody(request);
        final selectedModels =
            ((payload['selectedModels'] as List?) ?? const <dynamic>[])
                .whereType<String>()
                .map((item) => item.trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false);
        final modelRef = (payload['modelRef'] as String?)?.trim() ?? '';

        var selectedApplied = false;
        if (selectedModels.isNotEmpty) {
          selectedApplied = _assistantGateway.setSelectedModels(selectedModels);
        }

        final switchTarget = modelRef.isNotEmpty
            ? modelRef
            : (selectedModels.isNotEmpty ? selectedModels.first : '');
        var switched = false;
        if (switchTarget.isNotEmpty) {
          switched = _assistantGateway.switchModel(switchTarget);
        }

        if ((!selectedApplied && selectedModels.isNotEmpty) ||
            (!switched && switchTarget.isNotEmpty)) {
          await _writeJson(
            request: request,
            statusCode: HttpStatus.badRequest,
            data: <String, dynamic>{
              'error': 'model_select_failed',
              'availableModels': _assistantGateway.listAvailableModels(),
              'selectedModels': _assistantGateway.selectedModels(),
              'currentModel': _assistantGateway.currentModel(),
            },
          );
          return;
        }
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{
            'ok': true,
            'currentModel': _assistantGateway.currentModel(),
            'selectedModels': _assistantGateway.selectedModels(),
            'availableModels': _assistantGateway.listAvailableModels(),
          },
        );
        return;
      }
      if (method == 'POST' &&
          _startsWithPath(path, '/v1/assistant/providers/') &&
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
          AssistantAuditLog(
            event: 'provider_manual_recover',
            actor: 'assistant_operator',
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
      if (method == 'GET' && _matchesPath(path, '/v1/assistant/adapters')) {
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{'adapters': _adapterRuntime.listAdapterIds()},
        );
        return;
      }
      if (method == 'GET' && _matchesPath(path, '/v1/assistant/costs')) {
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
      if (method == 'GET' && _matchesPath(path, '/v1/assistant/alerts')) {
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
      if (method == 'GET' &&
          _matchesPath(path, '/v1/assistant/alerts/config')) {
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{'routing': _alertDispatcher.routingConfig()},
        );
        return;
      }
      if (method == 'POST' &&
          _matchesPath(path, '/v1/assistant/logs/export')) {
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
      if (method == 'POST' &&
          _matchesPath(path, '/v1/assistant/logs/boost')) {
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
      if (method == 'POST' &&
          _matchesPath(path, '/v1/assistant/alerts/test')) {
        final payload = await _decodeBody(request);
        final severityRaw =
            (payload['severity'] as String?)?.trim().toLowerCase() ?? 'warning';
        final severity = severityRaw == 'critical'
            ? AssistantSloAlertSeverity.critical
            : AssistantSloAlertSeverity.warning;
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
      if (method == 'GET' && _matchesPath(path, '/v1/assistant/skills')) {
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
      if (method == 'GET' && _matchesPath(path, '/v1/assistant/sessions')) {
        final sessions = await _assistantGateway.listSessions();
        await _writeJson(
          request: request,
          statusCode: HttpStatus.ok,
          data: <String, dynamic>{'sessions': sessions},
        );
        return;
      }
      if (method == 'POST' &&
          _matchesPath(path, '/v1/assistant/skills/invoke')) {
        final payload = await _decodeBody(request);
        final skillId = (payload['skill_id'] as String?)?.trim() ?? '';
        final actor = (payload['userId'] as String?)?.trim() ?? 'external';
        final channel = (payload['channel'] as String?)?.trim() ?? 'app';
        final acl = _authAcl.allow(
          AssistantAccessContext(
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
      if (method == 'POST' && _matchesPath(path, '/v1/assistant/runs')) {
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
          profileSubjectId: payload['profileSubjectId'] as String?,
          subAccountId: payload['subAccountId'] as String?,
          personaContextVersion: payload['personaContextVersion'] as String?,
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
          sourceSurfaceId: payload['sourceSurfaceId'] as String?,
          sourceQuery: payload['sourceQuery'] as String?,
          fromGlobalSearch: payload['fromGlobalSearch'] == true,
        );
        final requestedModelRef =
            (payload['modelRef'] as String?)?.trim() ?? '';
        final requestedSelectedModels =
            ((payload['selectedModels'] as List?) ?? const <dynamic>[])
                .whereType<String>()
                .map((item) => item.trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false);
        AssistantProviderDescriptor? selectedProvider;
        if (requestedSelectedModels.isNotEmpty) {
          _assistantGateway.setSelectedModels(requestedSelectedModels);
        }
        if (requestedModelRef.isNotEmpty) {
          final switched = _assistantGateway.switchModel(requestedModelRef);
          if (!switched) {
            await _writeJson(
              request: request,
              statusCode: HttpStatus.badRequest,
              data: <String, dynamic>{
                'error': 'invalid_model_ref',
                'requestedModelRef': requestedModelRef,
                'availableModels': _assistantGateway.listAvailableModels(),
              },
            );
            return;
          }
        } else {
          selectedProvider = await _selectProviderForRun(runReq);
          if (selectedProvider != null) {
            _assistantGateway.switchModel(selectedProvider.id);
          }
        }
        final runStartedAt = DateTime.now();
        final runRes = await _assistantGateway.run(runReq);
        final elapsedMs =
            DateTime.now().difference(runStartedAt).inMilliseconds;
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
          if (alert.severity == AssistantSloAlertSeverity.critical) {
            _providerRegistry.disableTemporarily(
              providerId: providerId,
              duration: _autoDisableDuration,
            );
            await _auditLogger.write(
              AssistantAuditLog(
                event: 'provider_auto_disabled',
                actor: 'assistant_system',
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
          AssistantCostRecord(
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
          AssistantAuditLog(
            event: 'assistant_run',
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
            ...runRes.toJson(),
            'runId': runRes.runId ?? requestId,
            'traceId': runRes.traceId ?? requestId,
            'provider': providerId,
            'slo': _sloMonitor
                .snapshotForProvider(providerId: providerId)
                .toJson(),
          },
        );
        return;
      }
      if (method == 'POST' &&
          _matchesPath(path, '/v1/assistant/runs/stream')) {
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
          profileSubjectId: payload['profileSubjectId'] as String?,
          subAccountId: payload['subAccountId'] as String?,
          personaContextVersion: payload['personaContextVersion'] as String?,
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
          sourceSurfaceId: payload['sourceSurfaceId'] as String?,
          sourceQuery: payload['sourceQuery'] as String?,
          fromGlobalSearch: payload['fromGlobalSearch'] == true,
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
        final finalPayload = runRes.toJson()..remove('traces');
        request.response.write('data: ${jsonEncode(finalPayload)}\n\n');
        await request.response.close();
        return;
      }
      if (method == 'POST' &&
          _startsWithPath(path, '/v1/assistant/channels/')) {
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
          sessionId: 'channel_${adapterId}_${DateTime.now().millisecondsSinceEpoch}',
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
    if (authToken.isEmpty) return true;
    final token = request.headers.value(HttpHeaders.authorizationHeader) ?? '';
    return token.trim() == 'Bearer $authToken';
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

  Future<AssistantProviderDescriptor?> _selectProviderForRun(
    AssistantRunRequest runReq,
  ) async {
    final candidates = _providerRegistry.list(
      type: AssistantProviderType.llm,
      enabled: true,
    );
    if (candidates.isEmpty) return null;
    for (final candidate in candidates) {
      await _providerHealthService.probe(candidate);
    }
    final healthMap = _providerHealthService.healthMap();
    final sloMap = <String, AssistantSloSnapshot>{};
    for (final candidate in candidates) {
      sloMap[candidate.id] = _sloMonitor.snapshotForProvider(
        providerId: candidate.id,
        windowMinutes: 5,
      );
    }
    final context = AssistantProviderRoutingContext(
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

  bool _matchesPath(String actual, String canonical) {
    return actual == canonical;
  }

  bool _startsWithPath(String actual, String canonicalPrefix) {
    return actual.startsWith(canonicalPrefix);
  }
}
