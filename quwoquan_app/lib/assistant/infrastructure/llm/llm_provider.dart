// ASSISTANT_WEAK_TYPE: LLM_RAW — 模型 HTTP/流式与多供应商容错；解析完成后用 LlmParseResult/AssistantTurnOutput。

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_policies.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/model_config.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_usage_ledger_entry.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/openai_compatible_chat_wire.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_response_parser.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/stream_json_field_extractor.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_run_interaction_collector.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

class AssistantModelOutput {
  const AssistantModelOutput({
    required this.text,
    this.toolCalls = const <AssistantToolCall>[],
    this.degraded = false,
    this.modelPath = '',
    this.failureCode = '',
    this.rawAssistantToolCallsMessage,
    this.reasoningText = '',
    this.usageEntries = const <LlmUsageLedgerEntry>[],
  });

  final String text;
  final List<AssistantToolCall> toolCalls;
  final bool degraded;
  final String modelPath;
  final String failureCode;

  /// 当模型走 native function calling 时，保存 assistant message 原文（含 tool_calls 字段），
  /// 用于下一轮 LLM 请求时正确构建 OpenAI 协议的消息历史。
  final Map<String, dynamic>? rawAssistantToolCallsMessage;

  /// Model-provided reasoning / thinking content (from dedicated fields like
  /// `reasoning`, `reasoning_content`, or `<think>` tags).
  final String reasoningText;

  /// Per-request usage ledger entries emitted by the model provider.
  final List<LlmUsageLedgerEntry> usageEntries;

  bool get hasToolCalls => toolCalls.isNotEmpty;

  /// 将 [text] 解析为助手 JSON 契约（与 [LlmResponseParser.parse] 一致）。
  ///
  /// 调用方若需 [assistantOutputViewIfParsed] 与 [assistantTurnOutputIfValid] 等投影，
  /// 应对返回值做局部缓存，避免重复解析。
  LlmParseResult parseAssistantText() => LlmResponseParser.parse(text);

  /// 解析成功后的只读投影；非 JSON / 解析失败则为 `null`。
  LlmAssistantOutputJsonView? get assistantOutputViewIfParsed =>
      parseAssistantText().assistantOutputView;

  /// 解析成功且满足 canonical `assistant_turn` 时的强类型；否则 `null`。
  AssistantTurnOutput? get assistantTurnOutputIfValid {
    return parseAssistantText().tryAssistantTurnOutput();
  }

  AssistantModelOutput copyWith({
    String? text,
    List<AssistantToolCall>? toolCalls,
    bool? degraded,
    String? modelPath,
    String? failureCode,
    Map<String, dynamic>? rawAssistantToolCallsMessage,
    String? reasoningText,
    List<LlmUsageLedgerEntry>? usageEntries,
  }) {
    return AssistantModelOutput(
      text: text ?? this.text,
      toolCalls: toolCalls ?? this.toolCalls,
      degraded: degraded ?? this.degraded,
      modelPath: modelPath ?? this.modelPath,
      failureCode: failureCode ?? this.failureCode,
      rawAssistantToolCallsMessage:
          rawAssistantToolCallsMessage ?? this.rawAssistantToolCallsMessage,
      reasoningText: reasoningText ?? this.reasoningText,
      usageEntries: usageEntries ?? this.usageEntries,
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
  static const String answerStreamNotStarted = 'answer_stream_not_started';
  static const String answerStreamFailed = 'answer_stream_failed';
  static const String processTimelineMissing = 'process_timeline_missing';
}

abstract class AssistantLlmProvider {
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, Object?>{},
    Map<String, dynamic> templateVariables = const <String, Object?>{},
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
    this.streamJsonFieldPaths = const <String>[],
  });

  /// Synthesis / structured-answer stage defaults.
  const LlmCallOptions.synthesis()
    : temperature = 0.2,
      maxTokens = 4096,
      forceJsonObject = true,
      timeoutSeconds = 45,
      streamJsonFieldPaths = const <String>[
        'retrievalProcessing.processingSummary',
        'answerProcessing.readinessSummary',
      ];

  /// Default planning / ReAct stage defaults (mirrors legacy hard-coded values).
  const LlmCallOptions.planning()
    : temperature = 0.3,
      maxTokens = null,
      forceJsonObject = false,
      timeoutSeconds = 30,
      streamJsonFieldPaths = const <String>[];

  final double? temperature;
  final int? maxTokens;
  final bool forceJsonObject;
  final int? timeoutSeconds;
  final List<String> streamJsonFieldPaths;
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
    this.modelRef = '',
  });

  final String modelId;
  final String baseUrl;
  final String apiKey;
  final PromptTemplateRuntime? templateRuntime;
  final ToolMetadataRegistry? toolMetadataRegistry;
  final String modelRef;
  final String plannerTemplateVersion;
  static const String _reactPolicyPath =
      'assets/assistant/config/react_policy.json';
  ReactPolicy _reactPolicy = ReactPolicy.defaults;
  Future<void>? _reactPolicyLoading;
  final JsonFieldStreamExtractor _reasonShortJsonExtractor =
      JsonFieldStreamExtractor('reasonShort');
  final JsonFieldStreamExtractor _answerJsonExtractor =
      JsonFieldStreamExtractor('userMarkdown');

  ModelCapabilityProfile get _profile =>
      ModelCapabilityProfile.forModelRef(modelRef);

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, Object?>{},
    Map<String, dynamic> templateVariables = const <String, Object?>{},
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
    final requestMessages = _buildRequestMessages(
      messages: <Map<String, dynamic>>[
        <String, String>{'role': 'system', 'content': resolvedPrompt.content},
        ...messages,
      ],
      templateContext: templateContext,
    );
    final toolSchemas = _buildToolSchemas(availableTools);
    final enableTools = toolSchemas.isNotEmpty;

    if (onDelta != null) {
      return _requestCompletionStreamingWithCompatFallback(
        requestMessages: requestMessages,
        toolSchemas: toolSchemas,
        enableTools: enableTools,
        resolvedPrompt: resolvedPrompt,
        callOptions: opts,
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        onDelta: onDelta,
      );
    }

    return _requestCompletionWithCompatFallback(
      requestMessages: requestMessages,
      toolSchemas: toolSchemas,
      enableTools: enableTools,
      resolvedPrompt: resolvedPrompt,
      callOptions: opts,
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
    );
  }

  Future<AssistantModelOutput> _requestCompletionWithCompatFallback({
    required List<Map<String, dynamic>> requestMessages,
    required List<Map<String, dynamic>> toolSchemas,
    required bool enableTools,
    required _ResolvedPromptStack resolvedPrompt,
    required String sessionId,
    required String runId,
    required String traceId,
    required LlmCallOptions callOptions,
  }) async {
    final usageLedger = <LlmUsageLedgerEntry>[];
    final attemptedVariants = <String>{};
    AssistantModelOutput? lastResult;

    Future<AssistantModelOutput?> runVariant({
      required bool variantEnableTools,
      required bool variantForceJsonObject,
    }) async {
      final variantKey = _compatVariantKey(
        enableTools: variantEnableTools,
        forceJsonObject: variantForceJsonObject,
      );
      if (!attemptedVariants.add(variantKey)) return null;
      final retry = await _requestCompletion(
        requestMessages: requestMessages,
        toolSchemas: variantEnableTools
            ? toolSchemas
            : const <Map<String, dynamic>>[],
        enableTools: variantEnableTools,
        resolvedPrompt: resolvedPrompt,
        callOptions: _copyCallOptions(
          callOptions,
          forceJsonObject: variantForceJsonObject,
        ),
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
      );
      usageLedger.addAll(retry.usageEntries);
      final merged = retry.copyWith(
        usageEntries: List<LlmUsageLedgerEntry>.from(usageLedger),
      );
      lastResult = merged;
      if (!merged.degraded ||
          merged.failureCode == AssistantFailureCode.templateMissing) {
        return merged;
      }
      return null;
    }

    final initial = await runVariant(
      variantEnableTools: enableTools,
      variantForceJsonObject: callOptions.forceJsonObject,
    );
    if (initial != null) return initial;
    final baseResult = lastResult!;
    final shouldRetryWithoutJsonMode =
        callOptions.forceJsonObject &&
        _profile.supportsJsonMode &&
        _shouldRetryWithoutJsonMode(baseResult.text);
    final shouldRetryWithoutTools =
        enableTools && _shouldRetryWithoutTools(baseResult.text);

    if (shouldRetryWithoutJsonMode) {
      final retried = await runVariant(
        variantEnableTools: enableTools,
        variantForceJsonObject: false,
      );
      if (retried != null) return retried;
    }
    if (shouldRetryWithoutTools) {
      final retried = await runVariant(
        variantEnableTools: false,
        variantForceJsonObject: callOptions.forceJsonObject,
      );
      if (retried != null) return retried;
    }
    if (shouldRetryWithoutJsonMode && shouldRetryWithoutTools) {
      final retried = await runVariant(
        variantEnableTools: false,
        variantForceJsonObject: false,
      );
      if (retried != null) return retried;
    }
    return lastResult!;
  }

  Future<AssistantModelOutput> _requestCompletionStreamingWithCompatFallback({
    required List<Map<String, dynamic>> requestMessages,
    required List<Map<String, dynamic>> toolSchemas,
    required bool enableTools,
    required _ResolvedPromptStack resolvedPrompt,
    required String sessionId,
    required String runId,
    required String traceId,
    required LlmCallOptions callOptions,
    required void Function(String delta) onDelta,
  }) async {
    final usageLedger = <LlmUsageLedgerEntry>[];
    final attemptedVariants = <String>{};
    AssistantModelOutput? lastResult;

    Future<AssistantModelOutput?> runVariant({
      required bool variantEnableTools,
      required bool variantForceJsonObject,
    }) async {
      final variantKey = _compatVariantKey(
        enableTools: variantEnableTools,
        forceJsonObject: variantForceJsonObject,
      );
      if (!attemptedVariants.add(variantKey)) return null;
      final retry = await _requestCompletionStreaming(
        requestMessages: requestMessages,
        toolSchemas: variantEnableTools
            ? toolSchemas
            : const <Map<String, dynamic>>[],
        enableTools: variantEnableTools,
        resolvedPrompt: resolvedPrompt,
        callOptions: _copyCallOptions(
          callOptions,
          forceJsonObject: variantForceJsonObject,
        ),
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        onDelta: onDelta,
      );
      usageLedger.addAll(retry.usageEntries);
      final merged = retry.copyWith(
        usageEntries: List<LlmUsageLedgerEntry>.from(usageLedger),
      );
      lastResult = merged;
      if (!merged.degraded ||
          merged.failureCode == AssistantFailureCode.templateMissing) {
        return merged;
      }
      return null;
    }

    final initial = await runVariant(
      variantEnableTools: enableTools,
      variantForceJsonObject: callOptions.forceJsonObject,
    );
    if (initial != null) return initial;
    final baseResult = lastResult!;
    final shouldRetryWithoutJsonMode =
        callOptions.forceJsonObject &&
        _profile.supportsJsonMode &&
        _shouldRetryWithoutJsonMode(baseResult.text);
    final shouldRetryWithoutTools =
        enableTools && _shouldRetryWithoutTools(baseResult.text);

    if (shouldRetryWithoutJsonMode) {
      final retried = await runVariant(
        variantEnableTools: enableTools,
        variantForceJsonObject: false,
      );
      if (retried != null) return retried;
    }
    if (shouldRetryWithoutTools) {
      final retried = await runVariant(
        variantEnableTools: false,
        variantForceJsonObject: callOptions.forceJsonObject,
      );
      if (retried != null) return retried;
    }
    if (shouldRetryWithoutJsonMode && shouldRetryWithoutTools) {
      final retried = await runVariant(
        variantEnableTools: false,
        variantForceJsonObject: false,
      );
      if (retried != null) return retried;
    }
    return lastResult!;
  }

  LlmCallOptions _copyCallOptions(
    LlmCallOptions source, {
    required bool forceJsonObject,
  }) {
    return LlmCallOptions(
      temperature: source.temperature,
      maxTokens: source.maxTokens,
      forceJsonObject: forceJsonObject,
      timeoutSeconds: source.timeoutSeconds,
      streamJsonFieldPaths: source.streamJsonFieldPaths,
    );
  }

  String _compatVariantKey({
    required bool enableTools,
    required bool forceJsonObject,
  }) {
    return 'tools=${enableTools ? 1 : 0}|json=${forceJsonObject ? 1 : 0}';
  }

  List<JsonFieldStreamExtractor> _buildStreamingReasonExtractors(
    LlmCallOptions callOptions,
  ) {
    if (callOptions.streamJsonFieldPaths.isEmpty) {
      return <JsonFieldStreamExtractor>[_reasonShortJsonExtractor];
    }
    return callOptions.streamJsonFieldPaths
        .map(JsonFieldStreamExtractor.new)
        .toList(growable: false);
  }

  String _consumeStreamingReasonDelta(
    String textDelta, {
    required List<JsonFieldStreamExtractor> streamExtractors,
  }) {
    for (final extractor in streamExtractors) {
      final delta = extractor.consume(textDelta);
      if (delta.isNotEmpty) {
        return delta;
      }
      if (!extractor.hasMatchedField || !extractor.isComplete) {
        break;
      }
    }
    return '';
  }

  bool _hasMatchedStreamingReasonExtractor(
    List<JsonFieldStreamExtractor> streamExtractors,
  ) {
    for (final extractor in streamExtractors) {
      if (extractor.hasMatchedField) {
        return true;
      }
    }
    return false;
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
    final requestBody = buildOpenAiNonStreamingChatCompletionRequest(
      modelId: modelId,
      requestMessages: requestMessages,
      toolSchemas: toolSchemas,
      enableTools: enableTools,
      temperature: callOptions.temperature ?? 0.3,
      maxTokens: callOptions.maxTokens,
      reasoningRequestEntries: _reasoningRequestEntries(_profile),
      forceJsonObject: callOptions.forceJsonObject,
      supportsJsonMode: _profile.supportsJsonMode,
    );
    final timeoutDuration = Duration(seconds: callOptions.timeoutSeconds ?? 30);
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
      final decodedBody = jsonDecode(response.body);
      if (decodedBody is! Map) {
        return const AssistantModelOutput(
          text: '模型调用失败: 返回格式异常（非 JSON 对象）',
          degraded: true,
          failureCode: AssistantFailureCode.modelResponseInvalid,
        );
      }
      final decoded = Map<String, dynamic>.from(decodedBody);
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
            'body': decodedBody,
          },
          'latencyMs': elapsedMs,
        },
      );
      final rootWire = OpenAiChatCompletionResponseRoot(decoded);
      final parsed = _parseModelOutput(rootWire.root);
      return parsed.copyWith(
        usageEntries: _buildUsageEntries(
          usageWire: rootWire.usage,
          requestMessages: requestMessages,
          responseText: '${parsed.text}\n${parsed.reasoningText}'.trim(),
          streaming: false,
          latencyMs: elapsedMs,
        ),
      );
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
  /// while accumulating the full response. Supports both text and tool_calls
  /// in streamed chunks. Also extracts canonical process reasoning from
  /// `<think>` tags or JSON `reasonShort` and emits those via [onDelta].
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
    final requestBody = buildOpenAiStreamingChatCompletionRequest(
      modelId: modelId,
      requestMessages: requestMessages,
      toolSchemas: toolSchemas,
      enableTools: enableTools,
      temperature: callOptions.temperature ?? 0.3,
      maxTokens: callOptions.maxTokens,
      reasoningRequestEntries: _reasoningRequestEntries(_profile),
      forceJsonObject: callOptions.forceJsonObject,
      supportsJsonMode: _profile.supportsJsonMode,
    );
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
        final rawBody = await streamedResponse.stream.bytesToString();
        final serverMessage = _extractErrorMessage(rawBody);
        await _logLlmInteraction(
          sessionId: sessionId,
          runId: runId,
          traceId: traceId,
          payload: <String, dynamic>{
            'kind': 'llm_stream',
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
              'statusCode': streamedResponse.statusCode,
              'body': rawBody,
            },
            'latencyMs': elapsedMs,
            'error':
                'HTTP ${streamedResponse.statusCode}${serverMessage.isEmpty ? '' : ' - $serverMessage'}',
          },
          hasError: true,
        );
        return AssistantModelOutput(
          text:
              '模型调用失败: HTTP ${streamedResponse.statusCode}${serverMessage.isEmpty ? '' : ' - $serverMessage'}',
          degraded: true,
          failureCode: AssistantFailureCode.modelHttp,
        );
      }

      _inThinkBlock = false;
      _inXmlToolBlock = false;
      _thinkingPhaseEnded = false;
      _reasonShortJsonExtractor.reset();

      final contentBuffer = StringBuffer();
      final reasoningBuffer = StringBuffer();
      final toolCallAccum = <String, _StreamingToolCallAccum>{};
      final profile = _profile;
      final streamExtractors = _buildStreamingReasonExtractors(callOptions);
      for (final extractor in streamExtractors) {
        extractor.reset();
      }
      Map<String, dynamic>? usageWire;

      await for (final line in streamedResponse.stream.transform(
        const _SseLineTransformer(),
      )) {
        if (!line.startsWith('data:')) continue;
        final data = line.substring(5).trim();
        if (data == '[DONE]') break;
        try {
          final decoded = jsonDecode(data);
          if (decoded is! Map) continue;
          final decodedMap = Map<String, dynamic>.from(decoded);
          final u = OpenAiChatCompletionResponseRoot(decodedMap).usage;
          if (u != null) {
            usageWire = u;
          }
          final choices = decodedMap['choices'] as List?;
          if (choices == null || choices.isEmpty) continue;
          final choice = choices.first as Map?;
          if (choice == null) continue;
          final delta = choice['delta'] as Map?;
          if (delta == null) continue;

          // MIMO / DeepSeek put thinking into a dedicated `reasoning` or
          // `reasoning_content` field instead of (or in addition to) `content`.
          if (profile.supportsReasoningField) {
            final reasoningDelta = _extractReasoningField(
              delta.cast<String, Object?>(),
              profile,
            );
            if (reasoningDelta.isNotEmpty) {
              reasoningBuffer.write(reasoningDelta);
              onDelta(reasoningDelta);
            }
          }

          final textDelta = (delta['content'] as String?) ?? '';
          if (textDelta.isNotEmpty) {
            contentBuffer.write(textDelta);
            String thinkingDelta = '';
            if (!profile.supportsReasoningField) {
              switch (profile.reasoningMode) {
                case ModelReasoningMode.nativeField:
                case ModelReasoningMode.none:
                  thinkingDelta = '';
                  break;
                case ModelReasoningMode.thinkTag:
                  thinkingDelta = _extractStreamingThinking(textDelta);
                  break;
                case ModelReasoningMode.jsonThinkingText:
                  thinkingDelta = _consumeStreamingReasonDelta(
                    textDelta,
                    streamExtractors: streamExtractors,
                  );
                  if (thinkingDelta.isEmpty &&
                      !_hasMatchedStreamingReasonExtractor(streamExtractors)) {
                    thinkingDelta = _extractStreamingThinking(textDelta);
                  }
                  break;
              }
            } else if (profile.supportsThinkTags) {
              thinkingDelta = _extractStreamingThinking(textDelta);
            }
            if (thinkingDelta.isNotEmpty) {
              reasoningBuffer.write(thinkingDelta);
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
        final argsStr = accum.argsBuffer.toString();
        final argsMap = argsStr.isEmpty
            ? <String, dynamic>{}
            : _decodeOpenAiFunctionArguments(argsStr);
        toolCalls.add(
          AssistantToolCall(name: accum.name, arguments: argsMap, id: accum.id),
        );
      }

      if (toolCalls.isNotEmpty) {
        rawAssistantMsg = <String, dynamic>{
          'role': 'assistant',
          'content': fullText.isEmpty ? null : fullText,
          'tool_calls': _openAiToolCallsWireFromAssistantCalls(toolCalls),
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

      final reasoning = reasoningBuffer.toString().trim();

      String effectiveText = fullText;
      if (effectiveText.isEmpty && toolCalls.isNotEmpty) {
        final names = toolCalls.map((c) => c.name).join('、');
        effectiveText = '正在调用工具：$names';
      } else if (effectiveText.isEmpty) {
        effectiveText = _structuredReasoningPayload(reasoning);
      }
      return AssistantModelOutput(
        text: effectiveText,
        toolCalls: toolCalls,
        modelPath: 'remote',
        rawAssistantToolCallsMessage: rawAssistantMsg,
        reasoningText: reasoning,
        usageEntries: _buildUsageEntries(
          usageWire: usageWire,
          requestMessages: requestMessages,
          responseText: '$effectiveText\n$reasoning'.trim(),
          streaming: true,
          latencyMs: DateTime.now().difference(startAt).inMilliseconds,
        ),
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
  // XML-format tool call tags used by some models (e.g. older Qwen).
  static final RegExp _xmlToolCallPattern = RegExp(
    r'<tool_call>.*?</tool_call>|<function=[^>]+>.*?</function>|'
    r'</?tool_call>|<function=[^>]*>|</function>|'
    r'<parameter=[^>]*>.*?</parameter>|</?parameter[^>]*>',
    dotAll: true,
  );
  bool _inThinkBlock = false;
  bool _inXmlToolBlock = false;
  bool _thinkingPhaseEnded = false;

  /// Extracts user-visible thinking content from streaming deltas.
  ///
  /// Supports two sources:
  /// 1. `<think>...</think>` tag pairs (DeepSeek-R1 / Qwen3 style).
  /// 2. Plain text content that is NOT inside XML tool-call tags.
  ///    This handles models that stream their reasoning as regular text
  ///    before emitting the JSON action block.
  ///
  /// XML tool-call fragments (`<tool_call>`, `<function=...>`) are stripped
  /// and never forwarded to the UI.
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
          _thinkingPhaseEnded = true;
        } else {
          buf.write(remaining);
          remaining = '';
        }
      } else if (_inXmlToolBlock) {
        final closeIdx = remaining.indexOf('</tool_call>');
        final closeFnIdx = remaining.indexOf('</function>');
        final close = _minPositive(closeIdx, closeFnIdx);
        if (close >= 0) {
          final tag =
              closeIdx >= 0 && (closeFnIdx < 0 || closeIdx <= closeFnIdx)
              ? '</tool_call>'
              : '</function>';
          remaining = remaining.substring(close + tag.length);
          _inXmlToolBlock = false;
        } else {
          remaining = '';
        }
      } else if (_thinkingPhaseEnded) {
        // After </think>, remaining content is the JSON action envelope.
        // Check if a new <think> block starts (multi-iteration scenario).
        final thinkMatch = _thinkTagOpen.firstMatch(remaining);
        if (thinkMatch != null) {
          _thinkingPhaseEnded = false;
          remaining = remaining.substring(thinkMatch.end);
          _inThinkBlock = true;
        } else {
          remaining = '';
        }
      } else {
        final thinkMatch = _thinkTagOpen.firstMatch(remaining);
        final toolCallIdx = remaining.indexOf('<tool_call>');
        final funcIdx = _findXmlFunctionTag(remaining);
        final xmlStart = _minPositive(toolCallIdx, funcIdx);

        if (thinkMatch != null &&
            (xmlStart < 0 || thinkMatch.start < xmlStart)) {
          final before = remaining.substring(0, thinkMatch.start).trim();
          if (before.isNotEmpty && !_looksLikeJsonEnvelope(before)) {
            buf.write(before);
          }
          remaining = remaining.substring(thinkMatch.end);
          _inThinkBlock = true;
        } else if (xmlStart >= 0) {
          final before = remaining.substring(0, xmlStart).trim();
          if (before.isNotEmpty && !_looksLikeJsonEnvelope(before)) {
            buf.write(before);
          }
          _inXmlToolBlock = true;
          final tagEnd = remaining.indexOf('>', xmlStart);
          remaining = tagEnd >= 0 ? remaining.substring(tagEnd + 1) : '';
        } else {
          final text = remaining.trim();
          if (text.isNotEmpty && !_looksLikeJsonEnvelope(text)) {
            buf.write(text);
          }
          remaining = '';
        }
      }
    }
    return buf.toString();
  }

  /// Returns the smaller non-negative value, or -1 if both are negative.
  static int _minPositive(int a, int b) {
    if (a < 0) return b;
    if (b < 0) return a;
    return a < b ? a : b;
  }

  /// Finds the start index of an XML `<function=...>` tag in [text], or -1.
  static int _findXmlFunctionTag(String text) {
    final m = RegExp(r'<function=').firstMatch(text);
    return m?.start ?? -1;
  }

  /// Returns true if [text] looks like a JSON envelope that the UI should not show.
  static bool _looksLikeJsonEnvelope(String text) {
    final t = text.trimLeft();
    if (!t.startsWith('{') && !t.startsWith('```')) return false;
    return t.contains('"contractId"') ||
        t.contains('"decision"') ||
        t.contains('"toolPlan"') ||
        t.contains('"nextAction"');
  }

  /// Strips XML tool-call markup from a complete text string for display.
  static String stripXmlToolCalls(String text) =>
      text.replaceAll(_xmlToolCallPattern, '').trim();

  /// Streams synthesis tokens via SSE. Calls [onDelta] for each text chunk.
  /// Returns the accumulated full text when done.
  Future<String> reasonStream({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    required void Function(String delta) onDelta,
    List<String> streamJsonFieldPaths = const <String>[],
    void Function(String fieldPath, String delta)? onStructuredDelta,
    void Function(String failureCode, Map<String, dynamic> diagnostics)?
    onFailure,
    Map<String, dynamic> templateContext = const <String, Object?>{},
    Map<String, dynamic> templateVariables = const <String, Object?>{},
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
      onFailure?.call(AssistantFailureCode.templateMissing, <String, dynamic>{
        'templateId': templateId,
        'templateVersion': templateVersion,
      });
      return '';
    }
    final requestMessages = _buildRequestMessages(
      messages: <Map<String, dynamic>>[
        <String, String>{'role': 'system', 'content': resolvedPrompt.content},
        ...messages,
      ],
      templateContext: templateContext,
    );
    final profile = _profile;
    final endpoint = '${_normalizeBaseUrl(baseUrl)}/chat/completions';
    final requestHeaders = <String, String>{
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $apiKey',
      'Accept': 'text/event-stream',
    };
    final requestBody = buildOpenAiStreamingPlannerChatRequest(
      modelId: modelId,
      requestMessages: requestMessages,
      reasoningRequestEntries: _reasoningRequestEntries(profile),
      supportsJsonMode: profile.supportsJsonMode,
    );
    try {
      final request = http.Request('POST', Uri.parse(endpoint));
      request.headers.addAll(requestHeaders);
      request.body = jsonEncode(requestBody);
      final streamedResponse = await request.send().timeout(
        const Duration(seconds: 60),
      );
      if (streamedResponse.statusCode >= 400) {
        onFailure?.call(AssistantFailureCode.modelHttp, <String, dynamic>{
          'statusCode': streamedResponse.statusCode,
          'templateId': templateId,
          'templateVersion': templateVersion,
          'modelId': modelId,
        });
        return '';
      }
      final buffer = StringBuffer();
      _answerJsonExtractor.reset();
      final structuredExtractors = profile.supportsJsonMode
          ? streamJsonFieldPaths
                .map(JsonFieldStreamExtractor.new)
                .toList(growable: false)
          : const <JsonFieldStreamExtractor>[];
      var emittedVisibleText = '';
      await for (final chunk in streamedResponse.stream.transform(
        const _SseLineTransformer(),
      )) {
        final delta = _parseSseDelta(chunk);
        if (delta != null && delta.isNotEmpty) {
          buffer.write(delta);
          for (final extractor in structuredExtractors) {
            final fieldDelta = extractor.consume(delta);
            if (fieldDelta.isNotEmpty) {
              onStructuredDelta?.call(extractor.fieldName, fieldDelta);
            }
          }
          var visibleDelta = '';
          if (profile.supportsJsonMode) {
            visibleDelta = _answerJsonExtractor.consume(delta);
          } else {
            visibleDelta = stripXmlToolCalls(delta);
          }
          if (visibleDelta.isNotEmpty) {
            emittedVisibleText += visibleDelta;
            onDelta(visibleDelta);
          }
        }
      }
      final rawOutput = buffer.toString();
      final fallbackVisible = _answerJsonExtractor.decodedValue.isNotEmpty
          ? _answerJsonExtractor.decodedValue
          : LlmResponseParser.extractUserMarkdown(rawOutput) ?? '';
      if (fallbackVisible.isNotEmpty &&
          fallbackVisible.length > emittedVisibleText.length) {
        onDelta(fallbackVisible.substring(emittedVisibleText.length));
      }
      if (rawOutput.trim().isEmpty) {
        onFailure?.call(AssistantFailureCode.modelResponseInvalid, <String, dynamic>{
          'reason': 'empty_stream_payload',
          'templateId': templateId,
          'templateVersion': templateVersion,
          'modelId': modelId,
        });
      }
      return rawOutput;
    } catch (error) {
      onFailure?.call(AssistantFailureCode.modelException, <String, dynamic>{
        'errorType': error.runtimeType.toString(),
        'templateId': templateId,
        'templateVersion': templateVersion,
        'modelId': modelId,
      });
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
      final choiceMap = choice.cast<String, Object?>();
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

    // Prompt ordering: identity → safety → model_thinking_policy →
    // conversation_spine(optional) → task → output_contract → persona →
    // tool_policy.
    // Stable prefix maximizes cache hits; instructions precede data.
    await appendLayer('stack.identity');
    await appendLayer('stack.safety');
    await appendLayer('stack.model_thinking_policy');
    final hasConversationSpine =
        (templateVariables['conversationSpine'] as String?)?.trim().isNotEmpty ==
        true;
    if (hasConversationSpine) {
      await appendLayer('stack.conversation_spine');
    }
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
        return 'phase.output_contract.plan';
      case 'synthesizer.final_answer':
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

  AssistantModelOutput _parseModelOutput(Map<String, dynamic> decoded) {
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
    final profile = ModelCapabilityProfile.forModelRef(modelRef);
    final reasoning = profile.supportsReasoningField
        ? _extractReasoningField(message.cast<String, Object?>(), profile).trim()
        : '';
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
        final argsMap = (argsRaw is String && argsRaw.trim().isEmpty)
            ? <String, dynamic>{}
            : _decodeOpenAiFunctionArguments(argsRaw);
        toolCalls.add(
          AssistantToolCall(name: name, arguments: argsMap, id: callId),
        );
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
    String effectiveContent = content;
    if (effectiveContent.isEmpty && toolCalls.isNotEmpty) {
      final names = toolCalls.map((c) => c.name).join('、');
      effectiveContent = '正在调用工具：$names';
    } else if (effectiveContent.isEmpty) {
      effectiveContent = _structuredReasoningPayload(reasoning);
    }
    return AssistantModelOutput(
      text: effectiveContent,
      toolCalls: toolCalls,
      modelPath: 'remote',
      rawAssistantToolCallsMessage: rawAssistantMsg,
      reasoningText: reasoning,
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

  bool _shouldRetryWithoutJsonMode(String errorText) {
    final statusMatch = RegExp(r'HTTP (\d{3})').firstMatch(errorText);
    if (statusMatch != null) {
      final code = int.tryParse(statusMatch.group(1) ?? '') ?? 0;
      if (_reactPolicy.llmRetryWithoutJsonModeStatusCodes.contains(code)) {
        return true;
      }
      return false;
    }
    final lowered = errorText.toLowerCase();
    for (final keyword in _reactPolicy.llmRetryWithoutJsonModeKeywords) {
      final token = keyword.trim().toLowerCase();
      if (token.isNotEmpty && lowered.contains(token)) return true;
    }
    return false;
  }

  List<LlmUsageLedgerEntry> _buildUsageEntries({
    required Map<String, dynamic>? usageWire,
    required List<Map<String, dynamic>> requestMessages,
    required String responseText,
    required bool streaming,
    required int latencyMs,
  }) {
    final entry = _buildUsageEntry(
      usageWire: usageWire,
      requestMessages: requestMessages,
      responseText: responseText,
      streaming: streaming,
      latencyMs: latencyMs,
    );
    if (entry == null) return const <LlmUsageLedgerEntry>[];
    return <LlmUsageLedgerEntry>[entry];
  }

  LlmUsageLedgerEntry? _buildUsageEntry({
    required Map<String, dynamic>? usageWire,
    required List<Map<String, dynamic>> requestMessages,
    required String responseText,
    required bool streaming,
    required int latencyMs,
  }) {
    final usage = usageWire ?? const <String, Object?>{};
    var inputTokens = _nonNegativeIntFromUsageKeys(usage, const <String>[
      'prompt_tokens',
      'input_tokens',
      'promptTokens',
    ]);
    var outputTokens = _nonNegativeIntFromUsageKeys(usage, const <String>[
      'completion_tokens',
      'output_tokens',
      'completionTokens',
    ]);
    var totalTokens = _nonNegativeIntFromUsageKeys(usage, const <String>[
      'total_tokens',
      'totalTokens',
    ]);
    var source = 'provider';

    final estimatedInput = _estimateTokenCount(
      _flattenMessages(requestMessages),
    );
    final estimatedOutput = _estimateTokenCount(responseText);
    if (inputTokens <= 0 && outputTokens <= 0 && totalTokens <= 0) {
      inputTokens = estimatedInput;
      outputTokens = estimatedOutput;
      totalTokens = inputTokens + outputTokens;
      source = 'estimated';
    } else {
      if (totalTokens <= 0) {
        totalTokens = inputTokens + outputTokens;
      }
      if (inputTokens <= 0 && totalTokens > 0 && outputTokens > 0) {
        inputTokens = totalTokens - outputTokens;
      }
      if (outputTokens <= 0 && totalTokens > 0 && inputTokens > 0) {
        outputTokens = totalTokens - inputTokens;
      }
    }
    if (totalTokens <= 0) return null;
    return LlmUsageLedgerEntry(
      provider: 'openai_compatible',
      modelId: modelId,
      modelRef: modelRef,
      streaming: streaming,
      source: source,
      inputTokens: inputTokens < 0 ? 0 : inputTokens,
      outputTokens: outputTokens < 0 ? 0 : outputTokens,
      totalTokens: totalTokens < 0 ? 0 : totalTokens,
      latencyMs: latencyMs < 0 ? 0 : latencyMs,
    );
  }

  /// OpenAI `usage` Map 中按候选键读取非负整数（供应商 wire，无 `Object?` 形参）。
  int _nonNegativeIntFromUsageKeys(
    Map<String, dynamic> usage,
    List<String> keys,
  ) {
    for (final k in keys) {
      final v = usage[k];
      if (v == null) continue;
      if (v is int) {
        return v < 0 ? 0 : v;
      }
      if (v is num) {
        final n = v.toInt();
        return n < 0 ? 0 : n;
      }
      final parsed = int.tryParse(v.toString().trim());
      if (parsed != null && parsed >= 0) return parsed;
    }
    return 0;
  }

  String _flattenMessages(List<Map<String, dynamic>> messages) {
    final buffer = StringBuffer();
    for (final message in messages) {
      final role = (message['role'] as String?)?.trim() ?? '';
      final content = (message['content'] ?? '').toString().trim();
      if (content.isEmpty) continue;
      if (buffer.isNotEmpty) buffer.writeln();
      if (role.isNotEmpty) {
        buffer.write('$role: ');
      }
      buffer.write(content);
    }
    return buffer.toString();
  }

  int _estimateTokenCount(String text) {
    final normalized = text.trim();
    if (normalized.isEmpty) return 0;
    return (normalized.length / 4).ceil();
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

  List<Map<String, dynamic>> _buildRequestMessages({
    required List<Map<String, dynamic>> messages,
    required Map<String, dynamic> templateContext,
  }) {
    final normalized = messages
        .map((message) => _normalizeMessageForProfile(message))
        .toList(growable: true);
    final continuation =
        (templateContext['providerReasoningContinuation'] as String?)
            ?.trim() ??
        '';
    if (continuation.isEmpty || !_profile.supportsReasoningField) {
      return normalized;
    }
    final alreadyPresent = normalized.any(
      (message) => _extractReasoningField(message, _profile).trim().isNotEmpty,
    );
    if (alreadyPresent) {
      return normalized;
    }
    final reasoningFieldName = _profile.reasoningFieldName.isNotEmpty
        ? _profile.reasoningFieldName
        : 'reasoning_content';
    final injected = <String, dynamic>{
      'role': 'assistant',
      'content': '',
      reasoningFieldName: continuation,
    };
    final insertIndex = normalized.lastIndexWhere(
      (message) => (message['role'] as String?)?.trim() == 'user',
    );
    if (insertIndex >= 0) {
      normalized.insert(insertIndex, injected);
    } else {
      normalized.add(injected);
    }
    return normalized;
  }

  Map<String, dynamic> _normalizeMessageForProfile(Map<String, dynamic> message) {
    final normalized = <String, dynamic>{};
    final role = (message['role'] as String?)?.trim() ?? '';
    if (role.isNotEmpty) {
      normalized['role'] = role;
    }
    if (message.containsKey('content')) {
      normalized['content'] = message['content'];
    }
    if (message['tool_calls'] is List) {
      normalized['tool_calls'] = message['tool_calls'];
    }
    if (message['tool_call_id'] != null) {
      normalized['tool_call_id'] = message['tool_call_id'];
    }
    if (message['name'] != null) {
      normalized['name'] = message['name'];
    }
    final continuation = _firstNonEmptyText(<String?>[
      (message['provider_reasoning_continuation'] as String?)?.trim(),
      (message['providerReasoningContinuation'] as String?)?.trim(),
      (message['reasoning_content'] as String?)?.trim(),
      (message['reasoning'] as String?)?.trim(),
    ]);
    if (_profile.supportsReasoningField &&
        role == 'assistant' &&
        continuation.isNotEmpty) {
      normalized[_profile.reasoningFieldName.isNotEmpty
          ? _profile.reasoningFieldName
          : 'reasoning_content'] = continuation;
    }
    return normalized;
  }

  Map<String, dynamic> _reasoningRequestEntries(ModelCapabilityProfile profile) {
    if (profile.reasoningRequestObject.isEmpty) {
      return const <String, Object?>{};
    }
    return <String, dynamic>{'reasoning': profile.reasoningRequestObject};
  }

  String _extractReasoningField(
    Map<String, dynamic> payload,
    ModelCapabilityProfile profile,
  ) {
    return _firstNonEmptyText(<String?>[
      (payload[profile.reasoningFieldName] as String?)?.trim(),
      (payload['reasoning_content'] as String?)?.trim(),
      (payload['reasoning'] as String?)?.trim(),
    ]);
  }

  String _structuredReasoningPayload(String reasoning) {
    final trimmed = reasoning.trim();
    if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
      return trimmed;
    }
    if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
      return trimmed;
    }
    return '';
  }

  String _firstNonEmptyText(Iterable<String?> values) {
    for (final value in values) {
      final normalized = value?.trim() ?? '';
      if (normalized.isNotEmpty) {
        return normalized;
      }
    }
    return '';
  }
}

class ModelOnlyFailureLlmProvider implements AssistantLlmProvider {
  const ModelOnlyFailureLlmProvider();

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, Object?>{},
    Map<String, dynamic> templateVariables = const <String, Object?>{},
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
      modelRef: config.modelRef,
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

  Future<String> reasonStream({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    required void Function(String delta) onDelta,
    List<String> streamJsonFieldPaths = const <String>[],
    void Function(String fieldPath, String delta)? onStructuredDelta,
    void Function(String failureCode, Map<String, dynamic> diagnostics)?
    onFailure,
    Map<String, dynamic> templateContext = const <String, Object?>{},
    Map<String, dynamic> templateVariables = const <String, Object?>{},
    String templateId = 'synthesizer.final_answer',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
  }) async {
    if (_selectedModelOrder.isNotEmpty &&
        (_activeModelRef == null ||
            !_selectedModelOrder.contains(_activeModelRef))) {
      _activeModelRef = _selectedModelOrder.first;
    }
    final ref = _activeModelRef;
    var emittedDelta = false;
    var emittedStructuredDelta = false;
    void forward(String delta) {
      if (delta.trim().isEmpty) return;
      emittedDelta = true;
      onDelta(delta);
    }
    void forwardStructured(String fieldPath, String delta) {
      if (delta.trim().isEmpty) return;
      emittedStructuredDelta = true;
      onStructuredDelta?.call(fieldPath, delta);
    }

    if (ref != null) {
      final remote = _providers[ref];
      if (remote is OpenAiCompatibleLlmProvider) {
        final streamed = await remote.reasonStream(
          messages: messages,
          availableTools: availableTools,
          onDelta: forward,
          streamJsonFieldPaths: streamJsonFieldPaths,
          onStructuredDelta: forwardStructured,
          onFailure: onFailure,
          templateContext: templateContext,
          templateVariables: templateVariables,
          templateId: templateId,
          templateVersion: templateVersion,
          sessionId: sessionId,
          runId: runId,
          traceId: traceId,
        );
        if ((emittedDelta || emittedStructuredDelta) &&
            streamed.trim().isNotEmpty) {
          return streamed;
        }
      }
    }

    emittedDelta = false;
    emittedStructuredDelta = false;
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
      onDelta: forward,
    );
    if (emittedDelta) {
      return fallback.text;
    }
    onFailure?.call(
      fallback.failureCode.isNotEmpty
          ? fallback.failureCode
          : AssistantFailureCode.modelUnavailable,
      <String, dynamic>{
        'source': 'switchable_fallback_without_stream',
        'templateId': templateId,
        'templateVersion': templateVersion,
        'modelRef': ref ?? '',
      },
    );
    return '';
  }

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, Object?>{},
    Map<String, dynamic> templateVariables = const <String, Object?>{},
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
        callOptions: callOptions,
        onDelta: onDelta,
      );
      return fallback.copyWith(
        modelPath: fallback.modelPath.isEmpty
            ? 'fallback_local'
            : fallback.modelPath,
        failureCode: fallback.degraded && fallback.failureCode.isEmpty
            ? AssistantFailureCode.modelUnavailable
            : fallback.failureCode,
      );
    }
    final remote = _providers[ref];
    if (remote == null) {
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
        callOptions: callOptions,
        onDelta: onDelta,
      );
      return fallback.copyWith(
        modelPath: fallback.modelPath.isEmpty
            ? 'fallback_local'
            : fallback.modelPath,
        failureCode: fallback.degraded && fallback.failureCode.isEmpty
            ? AssistantFailureCode.modelUnavailable
            : fallback.failureCode,
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
      final usageLedger = <LlmUsageLedgerEntry>[...remoteResult.usageEntries];
      if (remoteResult.failureCode == AssistantFailureCode.templateMissing) {
        return remoteResult.copyWith(
          modelPath: remoteResult.modelPath.isEmpty
              ? 'template_error'
              : remoteResult.modelPath,
        );
      }

      AssistantModelOutput lastRemoteFailure = remoteResult.copyWith(
        modelPath: remoteResult.modelPath.isEmpty
            ? ref
            : remoteResult.modelPath,
      );

      final retryableRemoteFailure =
          remoteResult.failureCode == AssistantFailureCode.modelHttp ||
          remoteResult.failureCode == AssistantFailureCode.modelException ||
          remoteResult.failureCode ==
              AssistantFailureCode.modelResponseInvalid ||
          remoteResult.failureCode == AssistantFailureCode.modelUnavailable;

      // 网络/DNS/HTTP/响应格式这类模型侧故障不应直接透传给 UI，
      // 先尝试剩余远端模型，再回退到本地安全降级。
      if (retryableRemoteFailure) {
        final candidates = _selectedModelOrder.isEmpty
            ? _registrationOrder
            : _selectedModelOrder;
        final currentIndex = candidates.indexOf(ref);
        final retryRefs = <String>[];
        for (var i = 1; i < candidates.length; i++) {
          final idx = currentIndex >= 0
              ? (currentIndex + i) % candidates.length
              : i - 1;
          final candidateRef = candidates[idx];
          if (candidateRef != ref && !retryRefs.contains(candidateRef)) {
            retryRefs.add(candidateRef);
          }
        }

        for (final nextRef in retryRefs) {
          _activeModelRef = nextRef;
          final nextProvider = _providers[nextRef];
          if (nextProvider == null) continue;
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
            callOptions: callOptions,
          );
          if (!retry.degraded) {
            return retry.copyWith(
              usageEntries: <LlmUsageLedgerEntry>[
                ...usageLedger,
                ...retry.usageEntries,
              ],
            );
          }
          if (retry.failureCode == AssistantFailureCode.templateMissing) {
            return retry.copyWith(
              modelPath: retry.modelPath.isEmpty
                  ? 'template_error'
                  : retry.modelPath,
              usageEntries: <LlmUsageLedgerEntry>[
                ...usageLedger,
                ...retry.usageEntries,
              ],
            );
          }
          usageLedger.addAll(retry.usageEntries);
          lastRemoteFailure = retry.copyWith(
            modelPath: retry.modelPath.isEmpty ? nextRef : retry.modelPath,
          );
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
        usageEntries: <LlmUsageLedgerEntry>[
          ...usageLedger,
          ...fallback.usageEntries,
        ],
        failureCode: fallback.degraded
            ? (fallback.failureCode.isEmpty
                  ? (lastRemoteFailure.failureCode.isNotEmpty
                        ? lastRemoteFailure.failureCode
                        : AssistantFailureCode.heuristicFallback)
                  : fallback.failureCode)
            : fallback.failureCode,
      );
    }
    return remoteResult;
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
    Map<String, dynamic> templateContext = const <String, Object?>{},
    Map<String, dynamic> templateVariables = const <String, Object?>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    final query = _latestUserQuery(messages);
    final userFacingText = query.isNotEmpty
        ? '当前未能稳定连接模型服务，无法可靠完成这一轮推理与工具规划。请稍后重试，或补充更明确的目标后再试。'
        : '当前未能稳定连接模型服务，无法可靠完成这一轮推理与工具规划。请稍后重试。';
    onDelta?.call(userFacingText);
    return AssistantModelOutput(
      degraded: true,
      modelPath: 'fallback_local',
      failureCode: AssistantFailureCode.heuristicFallback,
      text: jsonEncode(
        AssistantTurnOutput(
          contractId: kAssistantTurnCurrentContractId,
          decision: const AssistantTurnDecisionPayload(
            nextAction: AssistantNextAction.abort,
          ),
          messageKind: AssistantMessageKind.fallback,
          userMarkdown: userFacingText,
          result: AssistantTurnResult(text: userFacingText),
          diagnostics: const AssistantTurnDiagnostics(
            notes: <String>[
              'heuristic_fallback_disabled',
              'fallback_mode:fail_closed',
            ],
          ),
          modelSelfScore: const AssistantTurnModelSelfScore(
            score: 0,
            reason: 'heuristic_fallback_disabled',
          ),
          toolCalls: const <AssistantTurnToolCall>[],
          slotState: const SlotStateSnapshot(),
          askUser: const AssistantTurnAskUser(),
          subagentPlan: const [],
        ).toEnvelopeMap(),
      ),
    );
  }

  String _latestUserQuery(List<Map<String, dynamic>> messages) {
    for (var i = messages.length - 1; i >= 0; i--) {
      final item = messages[i];
      if ((item['role'] as String?)?.trim() != 'user') continue;
      final content = (item['content'] as String?)?.trim() ?? '';
      if (content.isNotEmpty) return content;
    }
    return '';
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
class _SseLineTransformer extends StreamTransformerBase<List<int>, String> {
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
      final raw = lineBuffer
          .toString()
          .replaceAll('\r\n', '\n')
          .replaceAll('\r', '\n');
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

/// OpenAI-compatible `function.arguments`：字符串 JSON、对象或空；与流式拼接后的 `jsonDecode` 语义一致。
Map<String, dynamic> _decodeOpenAiFunctionArguments(Object? argsRaw) {
  if (argsRaw is String) {
    final trimmed = argsRaw.trim();
    if (trimmed.isEmpty) return <String, dynamic>{};
    try {
      final decoded = jsonDecode(trimmed);
      if (decoded is Map) return decoded.cast<String, Object?>();
    } catch (_) {
      return <String, dynamic>{'raw': trimmed};
    }
    return <String, dynamic>{};
  }
  if (argsRaw is Map) {
    return argsRaw.cast<String, Object?>();
  }
  return <String, dynamic>{};
}

List<Map<String, dynamic>> _openAiToolCallsWireFromAssistantCalls(
  List<AssistantToolCall> toolCalls,
) {
  return toolCalls
      .map(
        (tc) => <String, dynamic>{
          'id': tc.id,
          'type': 'function',
          'function': <String, dynamic>{
            'name': tc.name,
            'arguments': jsonEncode(tc.arguments),
          },
        },
      )
      .toList(growable: false);
}

