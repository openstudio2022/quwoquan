import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/personal_assistant/contracts/runtime_policies.dart';
import 'package:quwoquan_app/personal_assistant/engine/model_config.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_run_interaction_collector.dart';
import 'package:quwoquan_app/personal_assistant/template_runtime/template_runtime.dart';
import 'package:quwoquan_app/personal_assistant/tools/metadata/tool_metadata_registry.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

class AssistantModelOutput {
  const AssistantModelOutput({
    required this.text,
    this.toolCalls = const <AssistantToolCall>[],
    this.degraded = false,
    this.modelPath = '',
    this.failureCode = '',
    this.rawAssistantToolCallsMessage,
  });

  final String text;
  final List<AssistantToolCall> toolCalls;
  final bool degraded;
  final String modelPath;
  final String failureCode;
  /// 当模型走 native function calling 时，保存 assistant message 原文（含 tool_calls 字段），
  /// 用于下一轮 LLM 请求时正确构建 OpenAI 协议的消息历史。
  final Map<String, dynamic>? rawAssistantToolCallsMessage;

  bool get hasToolCalls => toolCalls.isNotEmpty;

  AssistantModelOutput copyWith({
    String? text,
    List<AssistantToolCall>? toolCalls,
    bool? degraded,
    String? modelPath,
    String? failureCode,
    Map<String, dynamic>? rawAssistantToolCallsMessage,
  }) {
    return AssistantModelOutput(
      text: text ?? this.text,
      toolCalls: toolCalls ?? this.toolCalls,
      degraded: degraded ?? this.degraded,
      modelPath: modelPath ?? this.modelPath,
      failureCode: failureCode ?? this.failureCode,
      rawAssistantToolCallsMessage:
          rawAssistantToolCallsMessage ?? this.rawAssistantToolCallsMessage,
    );
  }
}

class AssistantFailureCode {
  const AssistantFailureCode._();

  static const String none = '';
  static const String templateMissing = 'template_missing';
  static const String modelHttp = 'model_http_error';
  static const String modelException = 'model_exception';
  static const String modelResponseInvalid = 'model_response_invalid';
  static const String modelUnavailable = 'model_unavailable';
  static const String heuristicFallback = 'heuristic_fallback';
}

abstract class AssistantLlmProvider {
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  });
}

/// Options to customize per-call LLM behaviour (temperature, tokens, JSON mode, timeout).
class LlmCallOptions {
  const LlmCallOptions({
    this.temperature,
    this.maxTokens,
    this.forceJsonObject = false,
    this.timeoutSeconds,
  });

  /// Synthesis / structured-answer stage defaults.
  const LlmCallOptions.synthesis()
      : temperature = 0.2,
        maxTokens = 4096,
        forceJsonObject = true,
        timeoutSeconds = 45;

  /// Default planning / ReAct stage defaults (mirrors legacy hard-coded values).
  const LlmCallOptions.planning()
      : temperature = 0.3,
        maxTokens = null,
        forceJsonObject = false,
        timeoutSeconds = 30;

  final double? temperature;
  final int? maxTokens;
  final bool forceJsonObject;
  final int? timeoutSeconds;
}

class _ResolvedPromptStack {
  const _ResolvedPromptStack({
    required this.content,
    required this.missingVariables,
    required this.templateLog,
  });

  _ResolvedPromptStack.empty({
    required String templateId,
    required String templateVersion,
  }) : content = '',
       missingVariables = const <String>['__template_not_found__'],
       templateLog = <String, dynamic>{
         'templateId': templateId,
         'templateVersion': templateVersion,
         'bucket': 'control',
         'missingVariables': const <String>['__template_not_found__'],
         'stackLayers': const <Map<String, dynamic>>[],
       };

  final String content;
  final List<String> missingVariables;
  final Map<String, dynamic> templateLog;
}

class OpenAiCompatibleLlmProvider implements AssistantLlmProvider {
  OpenAiCompatibleLlmProvider({
    required this.modelId,
    required this.baseUrl,
    required this.apiKey,
    this.templateRuntime,
    this.toolMetadataRegistry,
    this.plannerTemplateVersion = '',
  });

  final String modelId;
  final String baseUrl;
  final String apiKey;
  final PromptTemplateRuntime? templateRuntime;
  final ToolMetadataRegistry? toolMetadataRegistry;
  final String plannerTemplateVersion;
  static const String _reactPolicyPath =
      'assets/personal_assistant/config/react_policy.json';
  ReactPolicy _reactPolicy = ReactPolicy.defaults;
  Future<void>? _reactPolicyLoading;

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    final opts = callOptions ?? const LlmCallOptions.planning();
    await toolMetadataRegistry?.ensureLoaded();
    await _ensureReactPolicyLoaded();
    final resolvedPrompt = await _resolvePlannerPrompt(
      templateContext: templateContext,
      templateVariables: templateVariables,
      templateId: templateId,
      templateVersion: templateVersion,
    );
    if (resolvedPrompt.missingVariables.contains('__template_not_found__') ||
        resolvedPrompt.content.trim().isEmpty) {
      return AssistantModelOutput(
        text: '模板渲染失败: $templateId 模板缺失或为空。',
        degraded: true,
        failureCode: AssistantFailureCode.templateMissing,
      );
    }
    final requestMessages = <Map<String, dynamic>>[
      <String, String>{'role': 'system', 'content': resolvedPrompt.content},
      ...messages,
    ];
    final toolSchemas = _buildToolSchemas(availableTools);

    if (onDelta != null) {
      return _requestCompletionStreaming(
        requestMessages: requestMessages,
        toolSchemas: toolSchemas,
        enableTools: toolSchemas.isNotEmpty,
        resolvedPrompt: resolvedPrompt,
        callOptions: opts,
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        onDelta: onDelta,
      );
    }

    final withTools = await _requestCompletion(
      requestMessages: requestMessages,
      toolSchemas: toolSchemas,
      enableTools: toolSchemas.isNotEmpty,
      resolvedPrompt: resolvedPrompt,
      callOptions: opts,
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
    );
    if (!withTools.degraded) return withTools;
    if (toolSchemas.isEmpty) return withTools;
    if (!_shouldRetryWithoutTools(withTools.text)) return withTools;
    final plain = await _requestCompletion(
      requestMessages: requestMessages,
      toolSchemas: const <Map<String, dynamic>>[],
      enableTools: false,
      resolvedPrompt: resolvedPrompt,
      callOptions: opts,
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
    );
    if (!plain.degraded) return plain;
    return withTools;
  }

  String _normalizeBaseUrl(String value) {
    final v = value.trim();
    if (v.endsWith('/')) return v.substring(0, v.length - 1);
    return v;
  }

  String _extractErrorMessage(String rawBody) {
    if (rawBody.trim().isEmpty) return '';
    try {
      final decoded = jsonDecode(rawBody);
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
      // ignore parse error, fallback to raw text
    }
    final text = rawBody.trim();
    if (text.length <= 180) return text;
    return '${text.substring(0, 180)}...';
  }

  Future<AssistantModelOutput> _requestCompletion({
    required List<Map<String, dynamic>> requestMessages,
    required List<Map<String, dynamic>> toolSchemas,
    required bool enableTools,
    required _ResolvedPromptStack resolvedPrompt,
    required String sessionId,
    required String runId,
    required String traceId,
    LlmCallOptions callOptions = const LlmCallOptions.planning(),
  }) async {
    final endpoint = '${_normalizeBaseUrl(baseUrl)}/chat/completions';
    final requestHeaders = <String, String>{
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $apiKey',
    };
    final requestBody = <String, dynamic>{
      'model': modelId,
      'messages': requestMessages,
      if (enableTools && toolSchemas.isNotEmpty) 'tools': toolSchemas,
      if (enableTools && toolSchemas.isNotEmpty) 'tool_choice': 'auto',
      'temperature': callOptions.temperature ?? 0.3,
      if (callOptions.maxTokens != null) 'max_tokens': callOptions.maxTokens,
      if (callOptions.forceJsonObject)
        'response_format': const <String, dynamic>{'type': 'json_object'},
    };
    final timeoutDuration = Duration(
      seconds: callOptions.timeoutSeconds ?? 30,
    );
    try {
      final startAt = DateTime.now();
      final response = await http
          .post(
            Uri.parse(endpoint),
            headers: requestHeaders,
            body: jsonEncode(requestBody),
          )
          .timeout(timeoutDuration);
      final elapsedMs = DateTime.now().difference(startAt).inMilliseconds;
      if (response.statusCode >= 400) {
        final serverMessage = _extractErrorMessage(response.body);
        await _logLlmInteraction(
          sessionId: sessionId,
          runId: runId,
          traceId: traceId,
          payload: <String, dynamic>{
            'kind': 'llm',
            'provider': 'openai_compatible',
            'model': modelId,
            'template': resolvedPrompt.templateLog,
            'request': <String, dynamic>{
              'url': endpoint,
              'method': 'POST',
              'headers': requestHeaders,
              'body': requestBody,
            },
            'response': <String, dynamic>{
              'statusCode': response.statusCode,
              'body': response.body,
            },
            'latencyMs': elapsedMs,
            'error':
                'HTTP ${response.statusCode}${serverMessage.isEmpty ? '' : ' - $serverMessage'}',
          },
          hasError: true,
        );
        return AssistantModelOutput(
          text:
              '模型调用失败: HTTP ${response.statusCode}${serverMessage.isEmpty ? '' : ' - $serverMessage'}',
          degraded: true,
          failureCode: AssistantFailureCode.modelHttp,
        );
      }
      final decoded = jsonDecode(response.body);
      await _logLlmInteraction(
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        payload: <String, dynamic>{
          'kind': 'llm',
          'provider': 'openai_compatible',
          'model': modelId,
          'template': resolvedPrompt.templateLog,
          'request': <String, dynamic>{
            'url': endpoint,
            'method': 'POST',
            'headers': requestHeaders,
            'body': requestBody,
          },
          'response': <String, dynamic>{
            'statusCode': response.statusCode,
            'body': decoded,
          },
          'latencyMs': elapsedMs,
        },
      );
      return _parseModelOutput(decoded);
    } catch (error) {
      await _logLlmInteraction(
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        payload: <String, dynamic>{
          'kind': 'llm',
          'provider': 'openai_compatible',
          'model': modelId,
          'template': resolvedPrompt.templateLog,
          'request': <String, dynamic>{
            'url': endpoint,
            'method': 'POST',
            'headers': requestHeaders,
            'body': requestBody,
          },
          'error': error.toString(),
        },
        hasError: true,
      );
      return AssistantModelOutput(
        text: '模型调用异常: $error',
        degraded: true,
        failureCode: AssistantFailureCode.modelException,
      );
    }
  }

  /// Streaming variant of [_requestCompletion].  Streams deltas via [onDelta]
  /// while accumulating the full response.  Supports both text and tool_calls
  /// in streamed chunks.  Also extracts `thinkingText` from `<think>` tags or
  /// JSON `thinkingText` field and emits those via [onDelta].
  Future<AssistantModelOutput> _requestCompletionStreaming({
    required List<Map<String, dynamic>> requestMessages,
    required List<Map<String, dynamic>> toolSchemas,
    required bool enableTools,
    required _ResolvedPromptStack resolvedPrompt,
    required String sessionId,
    required String runId,
    required String traceId,
    required void Function(String delta) onDelta,
    LlmCallOptions callOptions = const LlmCallOptions.planning(),
  }) async {
    final endpoint = '${_normalizeBaseUrl(baseUrl)}/chat/completions';
    final requestHeaders = <String, String>{
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $apiKey',
      'Accept': 'text/event-stream',
    };
    final requestBody = <String, dynamic>{
      'model': modelId,
      'messages': requestMessages,
      if (enableTools && toolSchemas.isNotEmpty) 'tools': toolSchemas,
      if (enableTools && toolSchemas.isNotEmpty) 'tool_choice': 'auto',
      'temperature': callOptions.temperature ?? 0.3,
      if (callOptions.maxTokens != null) 'max_tokens': callOptions.maxTokens,
      'stream': true,
    };
    final timeoutDuration = Duration(
      seconds: (callOptions.timeoutSeconds ?? 30) * 2,
    );
    try {
      final startAt = DateTime.now();
      final request = http.Request('POST', Uri.parse(endpoint));
      request.headers.addAll(requestHeaders);
      request.body = jsonEncode(requestBody);
      final streamedResponse = await request.send().timeout(timeoutDuration);
      final elapsedMs = DateTime.now().difference(startAt).inMilliseconds;
      if (streamedResponse.statusCode >= 400) {
        await _logLlmInteraction(
          sessionId: sessionId,
          runId: runId,
          traceId: traceId,
          payload: <String, dynamic>{
            'kind': 'llm_stream',
            'provider': 'openai_compatible',
            'model': modelId,
            'template': resolvedPrompt.templateLog,
            'latencyMs': elapsedMs,
            'error': 'HTTP ${streamedResponse.statusCode}',
          },
          hasError: true,
        );
        return AssistantModelOutput(
          text: '模型调用失败: HTTP ${streamedResponse.statusCode}',
          degraded: true,
          failureCode: AssistantFailureCode.modelHttp,
        );
      }

      final contentBuffer = StringBuffer();
      final toolCallAccum = <String, _StreamingToolCallAccum>{};

      await for (final line
          in streamedResponse.stream.transform(const _SseLineTransformer())) {
        if (!line.startsWith('data:')) continue;
        final data = line.substring(5).trim();
        if (data == '[DONE]') break;
        try {
          final decoded = jsonDecode(data);
          if (decoded is! Map) continue;
          final choices = decoded['choices'] as List?;
          if (choices == null || choices.isEmpty) continue;
          final choice = choices.first as Map?;
          if (choice == null) continue;
          final delta = choice['delta'] as Map?;
          if (delta == null) continue;

          final textDelta = (delta['content'] as String?) ?? '';
          if (textDelta.isNotEmpty) {
            contentBuffer.write(textDelta);
            final thinkingDelta = _extractStreamingThinking(textDelta);
            if (thinkingDelta.isNotEmpty) {
              onDelta(thinkingDelta);
            }
          }

          final tcRaw = delta['tool_calls'] as List?;
          if (tcRaw != null) {
            for (final tc in tcRaw) {
              if (tc is! Map) continue;
              final idx = tc['index']?.toString() ?? '0';
              final accum = toolCallAccum.putIfAbsent(
                idx,
                () => _StreamingToolCallAccum(),
              );
              if (tc['id'] != null) accum.id = tc['id'] as String;
              final fn = tc['function'] as Map?;
              if (fn != null) {
                if (fn['name'] != null) accum.name = fn['name'] as String;
                if (fn['arguments'] != null) {
                  accum.argsBuffer.write(fn['arguments'] as String);
                }
              }
            }
          }
        } catch (_) {
          // skip malformed SSE chunks
        }
      }

      final fullText = contentBuffer.toString();
      final toolCalls = <AssistantToolCall>[];
      Map<String, dynamic>? rawAssistantMsg;

      for (final accum in toolCallAccum.values) {
        if (accum.name.isEmpty) continue;
        Map<String, dynamic> argsMap = <String, dynamic>{};
        final argsStr = accum.argsBuffer.toString();
        if (argsStr.isNotEmpty) {
          try {
            final parsed = jsonDecode(argsStr);
            if (parsed is Map) argsMap = parsed.cast<String, dynamic>();
          } catch (_) {
            argsMap = <String, dynamic>{'raw': argsStr};
          }
        }
        toolCalls.add(AssistantToolCall(
          name: accum.name,
          arguments: argsMap,
          id: accum.id,
        ));
      }

      if (toolCalls.isNotEmpty) {
        rawAssistantMsg = <String, dynamic>{
          'role': 'assistant',
          'content': fullText.isEmpty ? null : fullText,
          'tool_calls': toolCalls
              .map((tc) => <String, dynamic>{
                    'id': tc.id,
                    'type': 'function',
                    'function': <String, dynamic>{
                      'name': tc.name,
                      'arguments': jsonEncode(tc.arguments),
                    },
                  })
              .toList(),
        };
      }

      await _logLlmInteraction(
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        payload: <String, dynamic>{
          'kind': 'llm_stream',
          'provider': 'openai_compatible',
          'model': modelId,
          'template': resolvedPrompt.templateLog,
          'latencyMs': DateTime.now().difference(startAt).inMilliseconds,
          'streaming': true,
          'toolCallCount': toolCalls.length,
          'contentLength': fullText.length,
        },
      );

      return AssistantModelOutput(
        text: fullText.isEmpty ? '已完成模型推理。' : fullText,
        toolCalls: toolCalls,
        modelPath: 'remote',
        rawAssistantToolCallsMessage: rawAssistantMsg,
      );
    } catch (error) {
      await _logLlmInteraction(
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        payload: <String, dynamic>{
          'kind': 'llm_stream',
          'provider': 'openai_compatible',
          'model': modelId,
          'template': resolvedPrompt.templateLog,
          'error': error.toString(),
        },
        hasError: true,
      );
      return AssistantModelOutput(
        text: '模型调用异常: $error',
        degraded: true,
        failureCode: AssistantFailureCode.modelException,
      );
    }
  }

  // Accumulator for streamed tool_call fragments.
  static final RegExp _thinkTagOpen = RegExp(r'<think>');
  static final RegExp _thinkTagClose = RegExp(r'</think>');
  bool _inThinkBlock = false;

  /// Extracts user-visible thinking content from streaming deltas.
  /// Supports `<think>...</think>` tag pairs (DeepSeek-R1 style).
  String _extractStreamingThinking(String delta) {
    final buf = StringBuffer();
    var remaining = delta;

    while (remaining.isNotEmpty) {
      if (_inThinkBlock) {
        final closeMatch = _thinkTagClose.firstMatch(remaining);
        if (closeMatch != null) {
          buf.write(remaining.substring(0, closeMatch.start));
          remaining = remaining.substring(closeMatch.end);
          _inThinkBlock = false;
        } else {
          buf.write(remaining);
          remaining = '';
        }
      } else {
        final openMatch = _thinkTagOpen.firstMatch(remaining);
        if (openMatch != null) {
          remaining = remaining.substring(openMatch.end);
          _inThinkBlock = true;
        } else {
          remaining = '';
        }
      }
    }
    return buf.toString();
  }

  /// Streams synthesis tokens via SSE. Calls [onDelta] for each text chunk.
  /// Returns the accumulated full text when done.
  Future<String> reasonStream({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    required void Function(String delta) onDelta,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'synthesizer.final_answer',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
  }) async {
    final resolvedPrompt = await _resolvePlannerPrompt(
      templateContext: templateContext,
      templateVariables: templateVariables,
      templateId: templateId,
      templateVersion: templateVersion,
    );
    if (resolvedPrompt.missingVariables.contains('__template_not_found__') ||
        resolvedPrompt.content.trim().isEmpty) {
      return '';
    }
    final requestMessages = <Map<String, dynamic>>[
      <String, String>{'role': 'system', 'content': resolvedPrompt.content},
      ...messages,
    ];
    final endpoint = '${_normalizeBaseUrl(baseUrl)}/chat/completions';
    final requestHeaders = <String, String>{
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $apiKey',
      'Accept': 'text/event-stream',
    };
    final requestBody = <String, dynamic>{
      'model': modelId,
      'messages': requestMessages,
      'temperature': 0.2,
      'max_tokens': 4096,
      'stream': true,
      'response_format': const <String, dynamic>{'type': 'json_object'},
    };
    try {
      final request = http.Request('POST', Uri.parse(endpoint));
      request.headers.addAll(requestHeaders);
      request.body = jsonEncode(requestBody);
      final streamedResponse = await request
          .send()
          .timeout(const Duration(seconds: 60));
      if (streamedResponse.statusCode >= 400) {
        return '';
      }
      final buffer = StringBuffer();
      await for (final chunk in streamedResponse.stream
          .transform(const _SseLineTransformer())) {
        final delta = _parseSseDelta(chunk);
        if (delta != null && delta.isNotEmpty) {
          onDelta(delta);
          buffer.write(delta);
        }
      }
      return buffer.toString();
    } catch (_) {
      return '';
    }
  }

  /// Parses a single SSE line and returns the text delta, or null if not applicable.
  String? _parseSseDelta(String line) {
    if (!line.startsWith('data:')) return null;
    final data = line.substring(5).trim();
    if (data == '[DONE]') return null;
    try {
      final decoded = jsonDecode(data);
      if (decoded is! Map) return null;
      final choices = decoded['choices'] as List?;
      if (choices == null || choices.isEmpty) return null;
      final choice = choices.first as Map?;
      if (choice == null) return null;
      final choiceMap = choice.cast<String, dynamic>();
      final delta = choiceMap['delta'] as Map?;
      if (delta == null) return null;
      return (delta['content'] as String?) ?? '';
    } catch (_) {
      return null;
    }
  }

  Future<_ResolvedPromptStack> _resolvePlannerPrompt({
    required Map<String, dynamic> templateContext,
    required Map<String, dynamic> templateVariables,
    required String templateId,
    required String templateVersion,
  }) async {
    final runtime = templateRuntime;
    if (runtime == null) {
      return _ResolvedPromptStack.empty(
        templateId: templateId,
        templateVersion: templateVersion,
      );
    }
    final defaultVersion = templateVersion.isEmpty
        ? plannerTemplateVersion
        : templateVersion;
    final stagePrompt = await runtime.renderTemplate(
      templateId: templateId,
      defaultVersion: defaultVersion,
      variables: templateVariables,
      selectionContext: templateContext,
    );
    final stackLayers = <String>[];
    final layerRefs = <Map<String, dynamic>>[];
    final missing = <String>[...stagePrompt.missingVariables];
    Future<void> appendLayer(String id) async {
      final rendered = await runtime.renderTemplate(
        templateId: id,
        defaultVersion: defaultVersion,
        variables: templateVariables,
        selectionContext: templateContext,
      );
      if (rendered.missingVariables.isNotEmpty) {
        final hasTemplateNotFound = rendered.missingVariables.contains(
          '__template_not_found__',
        );
        final hasContent = rendered.rendered.content.trim().isNotEmpty;
        // Stack layers are optional; only escalate missing variables when layer
        // actually returns content, or when missing reason is not template absence.
        if (!hasTemplateNotFound || hasContent) {
          missing.addAll(rendered.missingVariables);
        }
      }
      final text = rendered.rendered.content.trim();
      if (text.isEmpty) return;
      layerRefs.add(<String, dynamic>{
        'templateId': rendered.rendered.templateId,
        'templateVersion': rendered.rendered.templateVersion,
        'bucket': rendered.bucket,
      });
      stackLayers.add(text);
    }

    // v2 prompt ordering: identity → safety → task → output_contract → persona → tool_policy
    // Stable prefix (§1-§2) maximizes cache hits; instructions precede data.
    await appendLayer('stack.identity');
    await appendLayer('stack.safety');
    // §3: Stage-specific task prompt (planner / synthesizer / etc.)
    final stageText = stagePrompt.rendered.content.trim();
    if (stageText.isNotEmpty) {
      stackLayers.add(stageText);
      layerRefs.add(<String, dynamic>{
        'templateId': stagePrompt.rendered.templateId,
        'templateVersion': stagePrompt.rendered.templateVersion,
        'bucket': stagePrompt.bucket,
      });
    }
    // §4: Phase-specific output contract
    final phaseContractId = _phaseContractForTemplate(templateId);
    if (phaseContractId.isNotEmpty) {
      await appendLayer(phaseContractId);
    }
    // §5: Persona (global baseline + skill overlay)
    await appendLayer('stack.persona');
    // §6: Tool policy + runtime constraints
    await appendLayer('stack.tool_policy');
    // Legacy layers (kept for backward compatibility during migration)
    await appendLayer('stack.global_system');
    await appendLayer('stack.runtime_policy');
    await appendLayer('stack.recovery_policy');
    await appendLayer('stack.output_contract');
    return _ResolvedPromptStack(
      content: stackLayers.join('\n\n'),
      missingVariables: missing.toSet().toList(growable: false),
      templateLog: <String, dynamic>{
        'templateId': stagePrompt.rendered.templateId,
        'templateVersion': stagePrompt.rendered.templateVersion,
        'variableBindings': stagePrompt.rendered.variableBindings,
        'bucket': stagePrompt.bucket,
        'missingVariables': missing.toSet().toList(growable: false),
        'stackLayers': layerRefs,
      },
    );
  }

  static String _phaseContractForTemplate(String templateId) {
    switch (templateId) {
      case 'planner.global_plan':
      case 'planner.postcondition_check':
        return 'phase.output_contract.plan';
      case 'synthesizer.final_answer':
      case 'synthesizer.multi_skill_fusion':
        return 'phase.output_contract.answer';
      default:
        return '';
    }
  }

  Future<void> _logLlmInteraction({
    required String sessionId,
    required String runId,
    required String traceId,
    required Map<String, dynamic> payload,
    bool hasError = false,
  }) async {
    final entry = <String, dynamic>{
      'ts': DateTime.now().toIso8601String(),
      ...payload,
    };
    if (runId.isNotEmpty) {
      AppRunInteractionCollector.instance.add(runId: runId, interaction: entry);
    }
    await AppLogService.instance.writeEvent(
      logType: AppLogType.llm,
      level: hasError ? AppLogLevel.error : AppLogLevel.info,
      context: AppLogContext(
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        correlationId: runId,
        sourceDomain: 'assistant',
        sourceService: 'quwoquan_app',
        component: 'llm_provider',
        target: 'llm',
        action: 'call_llm',
      ),
      payload: entry,
      summaryPayload: <String, dynamic>{
        'kind': 'llm',
        'provider': payload['provider'] ?? '',
        'model': payload['model'] ?? '',
        'statusCode': ((payload['response'] as Map?)?['statusCode']) ?? 0,
        'hasError': hasError,
      },
      hasError: hasError,
    );
  }

  AssistantModelOutput _parseModelOutput(dynamic decoded) {
    if (decoded is! Map) {
      return const AssistantModelOutput(
        text: '模型调用失败: 返回格式异常（非 JSON 对象）',
        degraded: true,
        failureCode: AssistantFailureCode.modelResponseInvalid,
      );
    }
    final choices = decoded['choices'];
    if (choices is! List || choices.isEmpty) {
      return const AssistantModelOutput(
        text: '模型调用失败: 响应中缺少 choices',
        degraded: true,
        failureCode: AssistantFailureCode.modelResponseInvalid,
      );
    }
    final first = choices.first;
    if (first is! Map) {
      return const AssistantModelOutput(
        text: '模型调用失败: choices[0] 结构不可解析',
        degraded: true,
        failureCode: AssistantFailureCode.modelResponseInvalid,
      );
    }
    final message = first['message'];
    if (message is! Map) {
      return const AssistantModelOutput(
        text: '模型调用失败: choices[0].message 缺失',
        degraded: true,
        failureCode: AssistantFailureCode.modelResponseInvalid,
      );
    }
    final content = (message['content'] as String?)?.trim() ?? '';
    final toolCallsRaw = message['tool_calls'];
    final toolCalls = <AssistantToolCall>[];
    Map<String, dynamic>? rawAssistantMsg;
    if (toolCallsRaw is List) {
      for (final t in toolCallsRaw) {
        if (t is! Map) continue;
        final function = t['function'];
        if (function is! Map) continue;
        final name = (function['name'] as String?)?.trim() ?? '';
        if (name.isEmpty) continue;
        final callId = (t['id'] as String?)?.trim() ?? '';
        final argsRaw = function['arguments'];
        Map<String, dynamic> argsMap = <String, dynamic>{};
        if (argsRaw is String && argsRaw.isNotEmpty) {
          try {
            final argsDecoded = jsonDecode(argsRaw);
            if (argsDecoded is Map) {
              argsMap = argsDecoded.cast<String, dynamic>();
            }
          } catch (_) {
            argsMap = <String, dynamic>{'raw': argsRaw};
          }
        } else if (argsRaw is Map) {
          argsMap = argsRaw.cast<String, dynamic>();
        }
        toolCalls.add(AssistantToolCall(name: name, arguments: argsMap, id: callId));
      }
      if (toolCalls.isNotEmpty) {
        // 保存完整 assistant message（含 tool_calls），供下一轮构建 OpenAI 协议历史使用
        rawAssistantMsg = <String, dynamic>{
          'role': 'assistant',
          'content': content.isEmpty ? null : content,
          'tool_calls': toolCallsRaw,
        };
      }
    }
    return AssistantModelOutput(
      text: content.isEmpty ? '已完成模型推理。' : content,
      toolCalls: toolCalls,
      modelPath: 'remote',
      rawAssistantToolCallsMessage: rawAssistantMsg,
    );
  }

  Future<void> _ensureReactPolicyLoaded() async {
    _reactPolicyLoading ??= () async {
      _reactPolicy = await ReactPolicy.loadFromAsset(_reactPolicyPath);
    }();
    await _reactPolicyLoading;
  }

  /// 判断 withTools 失败后是否应降级为无工具调用重试。
  ///
  /// 主判据：HTTP 4xx/5xx（已在 [_requestCompletion] 通过 [failureCode] 携带）。
  /// 补充判据：对于外部 LLM 的 error body 文案（极少数无 HTTP 错误码但包含工具相关词）。
  bool _shouldRetryWithoutTools(String errorText) {
    // 主判据：failureCode 已是 modelHttp 时，直接判断是否是工具相关的 4xx
    // 此处 errorText 是 AssistantModelOutput.text，格式为 "模型调用失败: HTTP {code} - {msg}"
    // 从中提取状态码做精确判断
    final statusMatch = RegExp(r'HTTP (\d{3})').firstMatch(errorText);
    if (statusMatch != null) {
      final code = int.tryParse(statusMatch.group(1) ?? '') ?? 0;
      if (_reactPolicy.llmRetryWithoutToolsStatusCodes.contains(code)) {
        return true;
      }
      // 其他 4xx/5xx 不重试（避免将 429 也触发无工具重试）
      return false;
    }
    // 兜底：外部 API 有时返回 200 但 body 含工具相关错误。
    final lowered = errorText.toLowerCase();
    for (final keyword in _reactPolicy.llmRetryWithoutToolsKeywords) {
      final token = keyword.trim().toLowerCase();
      if (token.isNotEmpty && lowered.contains(token)) return true;
    }
    return false;
  }

  List<Map<String, dynamic>> _buildToolSchemas(List<String> availableTools) {
    final schemas = <Map<String, dynamic>>[];
    for (final name in availableTools) {
      final schema = toolMetadataRegistry?.openAiFunctionSchemaByName(name);
      if (schema != null) {
        schemas.add(schema);
      }
    }
    return schemas;
  }
}

class ModelOnlyFailureLlmProvider implements AssistantLlmProvider {
  const ModelOnlyFailureLlmProvider();

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    return const AssistantModelOutput(
      text: '模型调用失败: 当前未配置可用模型（请检查模型配置或远端桥接）。',
      degraded: true,
      modelPath: 'model_unavailable',
      failureCode: AssistantFailureCode.modelUnavailable,
    );
  }
}

class SwitchableAssistantLlmProvider implements AssistantLlmProvider {
  SwitchableAssistantLlmProvider({
    required AssistantLlmProvider fallbackProvider,
    this.templateRuntime,
    this.toolMetadataRegistry,
    this.plannerTemplateVersion = '',
  }) : _fallbackProvider = fallbackProvider;

  final AssistantLlmProvider _fallbackProvider;
  final PromptTemplateRuntime? templateRuntime;
  final ToolMetadataRegistry? toolMetadataRegistry;
  final String plannerTemplateVersion;
  final Map<String, OpenAiCompatibleLlmProvider> _providers =
      <String, OpenAiCompatibleLlmProvider>{};
  final List<String> _registrationOrder = <String>[];
  final List<String> _selectedModelOrder = <String>[];
  String? _activeModelRef;

  String? get activeModelRef => _activeModelRef;
  List<String> get availableModelRefs =>
      _providers.keys.toList(growable: false);
  List<String> get selectedModelRefs {
    if (_selectedModelOrder.isEmpty) {
      return _registrationOrder.toList(growable: false);
    }
    return _selectedModelOrder.toList(growable: false);
  }

  void registerRemoteModel(AssistantModelRuntimeConfig config) {
    _providers[config.modelRef] = OpenAiCompatibleLlmProvider(
      modelId: config.modelId,
      baseUrl: config.baseUrl,
      apiKey: config.apiKey,
      templateRuntime: templateRuntime,
      toolMetadataRegistry: toolMetadataRegistry,
      plannerTemplateVersion: plannerTemplateVersion,
    );
    if (!_registrationOrder.contains(config.modelRef)) {
      _registrationOrder.add(config.modelRef);
    }
    if (!_selectedModelOrder.contains(config.modelRef)) {
      _selectedModelOrder.add(config.modelRef);
    }
    _activeModelRef ??= config.modelRef;
  }

  void registerRemoteModels(List<AssistantModelRuntimeConfig> configs) {
    for (final c in configs) {
      registerRemoteModel(c);
    }
  }

  bool switchModel(String modelRef) {
    if (!_providers.containsKey(modelRef)) return false;
    if (!_selectedModelOrder.contains(modelRef)) {
      _selectedModelOrder.insert(0, modelRef);
    }
    _activeModelRef = modelRef;
    return true;
  }

  bool setSelectedModels(List<String> modelRefs) {
    final ordered = <String>[];
    for (final modelRef in modelRefs) {
      if (_providers.containsKey(modelRef) && !ordered.contains(modelRef)) {
        ordered.add(modelRef);
      }
    }
    if (ordered.isEmpty) return false;
    _selectedModelOrder
      ..clear()
      ..addAll(ordered);
    if (_activeModelRef == null ||
        !_selectedModelOrder.contains(_activeModelRef)) {
      _activeModelRef = _selectedModelOrder.first;
    }
    return true;
  }

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    if (_selectedModelOrder.isNotEmpty &&
        (_activeModelRef == null ||
            !_selectedModelOrder.contains(_activeModelRef))) {
      _activeModelRef = _selectedModelOrder.first;
    }
    final ref = _activeModelRef;
    if (ref == null) {
      const unavailable = ModelOnlyFailureLlmProvider();
      final degraded = await unavailable.reason(
        messages: messages,
        availableTools: availableTools,
      );
      return degraded.copyWith(
        modelPath: degraded.modelPath.isEmpty
            ? 'model_unavailable'
            : degraded.modelPath,
        failureCode: degraded.failureCode.isEmpty
            ? AssistantFailureCode.modelUnavailable
            : degraded.failureCode,
      );
    }
    final remote = _providers[ref];
    if (remote == null) {
      const unavailable = ModelOnlyFailureLlmProvider();
      final degraded = await unavailable.reason(
        messages: messages,
        availableTools: availableTools,
      );
      return degraded.copyWith(
        modelPath: degraded.modelPath.isEmpty
            ? 'model_unavailable'
            : degraded.modelPath,
        failureCode: degraded.failureCode.isEmpty
            ? AssistantFailureCode.modelUnavailable
            : degraded.failureCode,
      );
    }
    final remoteResult = await remote.reason(
      messages: messages,
      availableTools: availableTools,
      templateContext: templateContext,
      templateVariables: templateVariables,
      templateId: templateId,
      templateVersion: templateVersion,
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
      callOptions: callOptions,
      onDelta: onDelta,
    );
    if (remoteResult.degraded) {
      if (remoteResult.failureCode == AssistantFailureCode.templateMissing) {
        return remoteResult.copyWith(
          modelPath: remoteResult.modelPath.isEmpty
              ? 'template_error'
              : remoteResult.modelPath,
        );
      }
      if (remoteResult.failureCode == AssistantFailureCode.modelHttp ||
          remoteResult.failureCode == AssistantFailureCode.modelException ||
          remoteResult.failureCode ==
              AssistantFailureCode.modelResponseInvalid ||
          remoteResult.failureCode == AssistantFailureCode.modelUnavailable) {
        return remoteResult.copyWith(
          modelPath: remoteResult.modelPath.isEmpty
              ? ref
              : remoteResult.modelPath,
        );
      }
      // Try next remote model first, then fallback to local provider.
      final nextRef = _nextRemoteRef(ref);
      if (nextRef != null && nextRef != ref) {
        _activeModelRef = nextRef;
        final nextProvider = _providers[nextRef];
        if (nextProvider != null) {
          final retry = await nextProvider.reason(
            messages: messages,
            availableTools: availableTools,
            templateContext: templateContext,
            templateVariables: templateVariables,
            templateId: templateId,
            templateVersion: templateVersion,
            sessionId: sessionId,
            runId: runId,
            traceId: traceId,
          );
          if (!retry.degraded) return retry;
          if (retry.failureCode == AssistantFailureCode.templateMissing) {
            return retry.copyWith(
              modelPath: retry.modelPath.isEmpty
                  ? 'template_error'
                  : retry.modelPath,
            );
          }
          if (retry.failureCode == AssistantFailureCode.modelHttp ||
              retry.failureCode == AssistantFailureCode.modelException ||
              retry.failureCode == AssistantFailureCode.modelResponseInvalid ||
              retry.failureCode == AssistantFailureCode.modelUnavailable) {
            return retry.copyWith(
              modelPath: retry.modelPath.isEmpty ? nextRef : retry.modelPath,
            );
          }
        }
      }
      final fallback = await _fallbackProvider.reason(
        messages: messages,
        availableTools: availableTools,
        templateContext: templateContext,
        templateVariables: templateVariables,
        templateId: templateId,
        templateVersion: templateVersion,
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
      );
      return fallback.copyWith(
        modelPath: fallback.modelPath.isEmpty
            ? 'fallback_local'
            : fallback.modelPath,
        failureCode: fallback.failureCode.isEmpty
            ? AssistantFailureCode.heuristicFallback
            : fallback.failureCode,
      );
    }
    return remoteResult;
  }

  String? _nextRemoteRef(String current) {
    final candidates = _selectedModelOrder.isEmpty
        ? _registrationOrder
        : _selectedModelOrder;
    if (candidates.length <= 1) return null;
    final idx = candidates.indexOf(current);
    if (idx < 0) return candidates.first;
    final next = idx + 1;
    if (next < candidates.length) return candidates[next];
    return candidates.first;
  }
}

/// Fallback-only local provider:
/// - Do NOT perform domain inference or tool planning.
/// - Return a stable degraded response so upper runtime can continue safely.
class HeuristicLocalLlmProvider implements AssistantLlmProvider {
  const HeuristicLocalLlmProvider();

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    return const AssistantModelOutput(
      degraded: true,
      modelPath: 'fallback_local',
      failureCode: AssistantFailureCode.heuristicFallback,
      text: '当前模型服务不可用，已进入安全降级模式。请稍后重试，或明确告诉我要查询的内容（例如“深圳天气”）。',
    );
  }
}

class _StreamingToolCallAccum {
  String id = '';
  String name = '';
  final StringBuffer argsBuffer = StringBuffer();
}

/// Transforms raw SSE byte stream into individual event lines.
/// Uses proper UTF-8 decoding to handle multi-byte characters (CJK, emoji).
/// Handles \n, \r\n, and \r line endings.
class _SseLineTransformer
    extends StreamTransformerBase<List<int>, String> {
  const _SseLineTransformer();

  @override
  Stream<String> bind(Stream<List<int>> stream) async* {
    final byteBuffer = <int>[];
    final lineBuffer = StringBuffer();
    await for (final chunk in stream) {
      byteBuffer.addAll(chunk);
      // Decode as many complete UTF-8 characters as possible.
      // Trailing incomplete sequences are kept in byteBuffer for the next chunk.
      final decodable = _findDecodableBoundary(byteBuffer);
      if (decodable == 0) continue;
      final decoded = utf8.decode(
        byteBuffer.sublist(0, decodable),
        allowMalformed: true,
      );
      byteBuffer.removeRange(0, decodable);
      lineBuffer.write(decoded);
      final raw = lineBuffer.toString().replaceAll('\r\n', '\n').replaceAll('\r', '\n');
      final lastNewline = raw.lastIndexOf('\n');
      if (lastNewline < 0) continue;
      final complete = raw.substring(0, lastNewline + 1);
      lineBuffer.clear();
      lineBuffer.write(raw.substring(lastNewline + 1));
      for (final line in complete.split('\n')) {
        final trimmed = line.trim();
        if (trimmed.isNotEmpty) yield trimmed;
      }
    }
    // Flush remaining bytes
    if (byteBuffer.isNotEmpty) {
      lineBuffer.write(utf8.decode(byteBuffer, allowMalformed: true));
    }
    final remaining = lineBuffer.toString().trim();
    if (remaining.isNotEmpty) yield remaining;
  }

  /// Finds the largest prefix of [bytes] that forms complete UTF-8 sequences.
  static int _findDecodableBoundary(List<int> bytes) {
    if (bytes.isEmpty) return 0;
    var i = bytes.length;
    // Walk back from the end to find a potential incomplete multi-byte sequence.
    // UTF-8 continuation bytes start with 10xxxxxx (0x80..0xBF).
    while (i > 0 && i > bytes.length - 4) {
      final b = bytes[i - 1];
      if (b < 0x80) return i; // ASCII — safe boundary
      if (b >= 0xC0) {
        // Start of a multi-byte sequence; check if it's complete.
        final seqLen = b >= 0xF0 ? 4 : (b >= 0xE0 ? 3 : 2);
        final available = bytes.length - (i - 1);
        return available >= seqLen ? bytes.length : i - 1;
      }
      i--;
    }
    return bytes.length;
  }
}
