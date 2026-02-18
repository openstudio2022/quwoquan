import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/personal_assistant/engine/model_config.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_run_interaction_collector.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

class AssistantModelOutput {
  const AssistantModelOutput({
    required this.text,
    this.toolCalls = const <AssistantToolCall>[],
    this.degraded = false,
  });

  final String text;
  final List<AssistantToolCall> toolCalls;
  final bool degraded;

  bool get hasToolCalls => toolCalls.isNotEmpty;
}

abstract class AssistantLlmProvider {
  Future<AssistantModelOutput> reason({
    required List<Map<String, String>> messages,
    required List<String> availableTools,
    String sessionId = '',
    String runId = '',
    String traceId = '',
  });
}

class OpenAiCompatibleLlmProvider implements AssistantLlmProvider {
  OpenAiCompatibleLlmProvider({
    required this.modelId,
    required this.baseUrl,
    required this.apiKey,
  });

  final String modelId;
  final String baseUrl;
  final String apiKey;

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, String>> messages,
    required List<String> availableTools,
    String sessionId = '',
    String runId = '',
    String traceId = '',
  }) async {
    final requestMessages = <Map<String, String>>[
      const <String, String>{
        'role': 'system',
        'content':
            '你是可调用工具的助理，必须采用“思考-查询-观察-再决策”的方式回答。'
            '由你决定是否查询、查询什么、使用哪个 provider、是否继续扩展检索轮次。'
            '当问题涉及实时信息或你明确要“查询/检索”时，必须先发起 tool_calls，'
            '拿到工具结果后再回答；禁止只说“我来查询”却不调用工具。'
            '若检索结果不足，请改写查询词并追加一轮；若工具不可用，请明确说明并基于已有知识回答。',
      },
      ...messages,
    ];
    final toolSchemas = _buildToolSchemas(availableTools);
    final withTools = await _requestCompletion(
      requestMessages: requestMessages,
      toolSchemas: toolSchemas,
      enableTools: toolSchemas.isNotEmpty,
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
    );
    if (!withTools.degraded) return withTools;
    if (toolSchemas.isEmpty) return withTools;
    if (!_shouldRetryWithoutTools(withTools.text)) return withTools;
    // 对齐 Moltbot crm-l2-qa：当工具调用协议不兼容时，自动降级到纯 chat completions，优先保证模型可调用与结果生成。
    final plain = await _requestCompletion(
      requestMessages: requestMessages,
      toolSchemas: const <Map<String, dynamic>>[],
      enableTools: false,
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
    required List<Map<String, String>> requestMessages,
    required List<Map<String, dynamic>> toolSchemas,
    required bool enableTools,
    required String sessionId,
    required String runId,
    required String traceId,
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
      'temperature': 0.3,
    };
    try {
      final startAt = DateTime.now();
      final response = await http.post(
        Uri.parse(endpoint),
        headers: requestHeaders,
        body: jsonEncode(requestBody),
      );
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
      return AssistantModelOutput(text: '模型调用异常: $error', degraded: true);
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
      );
    }
    final choices = decoded['choices'];
    if (choices is! List || choices.isEmpty) {
      return const AssistantModelOutput(
        text: '模型调用失败: 响应中缺少 choices',
        degraded: true,
      );
    }
    final first = choices.first;
    if (first is! Map) {
      return const AssistantModelOutput(
        text: '模型调用失败: choices[0] 结构不可解析',
        degraded: true,
      );
    }
    final message = first['message'];
    if (message is! Map) {
      return const AssistantModelOutput(
        text: '模型调用失败: choices[0].message 缺失',
        degraded: true,
      );
    }
    final content = (message['content'] as String?)?.trim() ?? '';
    final toolCallsRaw = message['tool_calls'];
    final toolCalls = <AssistantToolCall>[];
    if (toolCallsRaw is List) {
      for (final t in toolCallsRaw) {
        if (t is! Map) continue;
        final function = t['function'];
        if (function is! Map) continue;
        final name = (function['name'] as String?)?.trim() ?? '';
        if (name.isEmpty) continue;
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
        toolCalls.add(AssistantToolCall(name: name, arguments: argsMap));
      }
    }
    return AssistantModelOutput(
      text: content.isEmpty ? '已完成模型推理。' : content,
      toolCalls: toolCalls,
    );
  }

  bool _shouldRetryWithoutTools(String errorText) {
    final lowered = errorText.toLowerCase();
    return lowered.contains('tool') ||
        lowered.contains('tools') ||
        lowered.contains('tool_choice') ||
        lowered.contains('function') ||
        lowered.contains('schema') ||
        lowered.contains('invalid') ||
        lowered.contains('unsupported') ||
        lowered.contains('400') ||
        lowered.contains('422') ||
        lowered.contains('500');
  }

  List<Map<String, dynamic>> _buildToolSchemas(List<String> availableTools) {
    final schemas = <Map<String, dynamic>>[];
    for (final name in availableTools) {
      final schema = _toolSchemaByName(name);
      if (schema != null) {
        schemas.add(schema);
      }
    }
    return schemas;
  }

  Map<String, dynamic>? _toolSchemaByName(String name) {
    switch (name) {
      case 'unified_retrieval':
        return <String, dynamic>{
          'type': 'function',
          'function': <String, dynamic>{
            'name': 'unified_retrieval',
            'description': '统一检索：按能力路由查询页面上下文、会话历史、长期记忆与 Web。',
            'parameters': <String, dynamic>{
              'type': 'object',
              'properties': <String, dynamic>{
                'query': <String, dynamic>{
                  'type': 'string',
                  'description': '要检索的问题或关键词。',
                },
                'requestedCapabilities': <String, dynamic>{
                  'type': 'array',
                  'items': <String, dynamic>{'type': 'string'},
                  'description': '候选能力ID，如 context.web_search。',
                },
                'contextScopeHint': <String, dynamic>{
                  'type': 'object',
                  'description': '页面与会话上下文锚点。',
                },
                'privacyProfile': <String, dynamic>{
                  'type': 'string',
                  'description': '隐私配置名。',
                },
                'providerHint': <String, dynamic>{
                  'type': 'string',
                  'description': '可选 provider 提示，如 brave/perplexity。',
                },
                'maxItems': <String, dynamic>{
                  'type': 'integer',
                  'description': '检索条数上限，默认 6。',
                },
              },
              'required': <String>['query'],
            },
          },
        };
      case 'web_search':
        return <String, dynamic>{
          'type': 'function',
          'function': <String, dynamic>{
            'name': 'web_search',
            'description': '网络检索最新信息。',
            'parameters': <String, dynamic>{
              'type': 'object',
              'properties': <String, dynamic>{
                'query': <String, dynamic>{'type': 'string'},
                'provider': <String, dynamic>{'type': 'string'},
                'count': <String, dynamic>{'type': 'integer'},
              },
              'required': <String>['query'],
            },
          },
        };
      case 'local_context':
        return <String, dynamic>{
          'type': 'function',
          'function': <String, dynamic>{
            'name': 'local_context',
            'description': '获取设备本地上下文。',
            'parameters': <String, dynamic>{
              'type': 'object',
              'properties': <String, dynamic>{},
            },
          },
        };
      case 'media_gallery':
        return <String, dynamic>{
          'type': 'function',
          'function': <String, dynamic>{
            'name': 'media_gallery',
            'description': '访问设备媒体库。',
            'parameters': <String, dynamic>{
              'type': 'object',
              'properties': <String, dynamic>{
                'mode': <String, dynamic>{'type': 'string'},
              },
            },
          },
        };
      case 'intent_bridge':
        return <String, dynamic>{
          'type': 'function',
          'function': <String, dynamic>{
            'name': 'intent_bridge',
            'description': '执行系统 Intent 或 URL 跳转。',
            'parameters': <String, dynamic>{
              'type': 'object',
              'properties': <String, dynamic>{
                'target': <String, dynamic>{'type': 'string'},
                'action': <String, dynamic>{'type': 'string'},
              },
            },
          },
        };
      default:
        return null;
    }
  }
}

class ModelOnlyFailureLlmProvider implements AssistantLlmProvider {
  const ModelOnlyFailureLlmProvider();

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, String>> messages,
    required List<String> availableTools,
    String sessionId = '',
    String runId = '',
    String traceId = '',
  }) async {
    return const AssistantModelOutput(
      text: '模型调用失败: 当前未配置可用模型（请检查模型配置或远端桥接）。',
      degraded: true,
    );
  }
}

class SwitchableAssistantLlmProvider implements AssistantLlmProvider {
  SwitchableAssistantLlmProvider({
    required AssistantLlmProvider fallbackProvider,
  }) : _fallbackProvider = fallbackProvider;

  final AssistantLlmProvider _fallbackProvider;
  final Map<String, OpenAiCompatibleLlmProvider> _providers =
      <String, OpenAiCompatibleLlmProvider>{};
  final List<String> _registrationOrder = <String>[];
  String? _activeModelRef;

  String? get activeModelRef => _activeModelRef;
  List<String> get availableModelRefs =>
      _providers.keys.toList(growable: false);

  void registerRemoteModel(AssistantModelRuntimeConfig config) {
    _providers[config.modelRef] = OpenAiCompatibleLlmProvider(
      modelId: config.modelId,
      baseUrl: config.baseUrl,
      apiKey: config.apiKey,
    );
    if (!_registrationOrder.contains(config.modelRef)) {
      _registrationOrder.add(config.modelRef);
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
    _activeModelRef = modelRef;
    return true;
  }

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, String>> messages,
    required List<String> availableTools,
    String sessionId = '',
    String runId = '',
    String traceId = '',
  }) async {
    final ref = _activeModelRef;
    if (ref == null) {
      return _fallbackProvider.reason(
        messages: messages,
        availableTools: availableTools,
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
      );
    }
    final remote = _providers[ref];
    if (remote == null) {
      return _fallbackProvider.reason(
        messages: messages,
        availableTools: availableTools,
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
      );
    }
    final remoteResult = await remote.reason(
      messages: messages,
      availableTools: availableTools,
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
    );
    if (remoteResult.degraded) {
      // Try next remote model first, then fallback to local provider.
      final nextRef = _nextRemoteRef(ref);
      if (nextRef != null && nextRef != ref) {
        _activeModelRef = nextRef;
        final nextProvider = _providers[nextRef];
        if (nextProvider != null) {
          final retry = await nextProvider.reason(
            messages: messages,
            availableTools: availableTools,
            sessionId: sessionId,
            runId: runId,
            traceId: traceId,
          );
          if (!retry.degraded) return retry;
        }
      }
      return _fallbackProvider.reason(
        messages: messages,
        availableTools: availableTools,
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
      );
    }
    return remoteResult;
  }

  String? _nextRemoteRef(String current) {
    if (_registrationOrder.length <= 1) return null;
    final idx = _registrationOrder.indexOf(current);
    if (idx < 0) return _registrationOrder.first;
    final next = idx + 1;
    if (next < _registrationOrder.length) return _registrationOrder[next];
    return _registrationOrder.first;
  }
}

/// Lightweight local-first provider:
/// - It heuristically maps user intents to tool calls for on-device ReAct loop.
/// - It can be replaced later by on-device or remote LLM providers.
class HeuristicLocalLlmProvider implements AssistantLlmProvider {
  const HeuristicLocalLlmProvider();

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, String>> messages,
    required List<String> availableTools,
    String sessionId = '',
    String runId = '',
    String traceId = '',
  }) async {
    final lastUser = messages.lastWhere(
      (m) => m['role'] == 'user',
      orElse: () => const <String, String>{'content': ''},
    );
    final query = lastUser['content'] ?? '';
    final content = query.toLowerCase();
    final lastTool = messages.lastWhere(
      (m) => m['role'] == 'tool',
      orElse: () => const <String, String>{'content': ''},
    );
    final lastToolContent = (lastTool['content'] ?? '').trim();
    final searchAttempts = messages
        .where(
          (m) =>
              m['role'] == 'tool' &&
              ((m['content'] ?? '').contains('检索结果：') ||
                  (m['content'] ?? '').contains('检索成功，但未获得可用摘要。') ||
                  (m['content'] ?? '').contains('Web search error') ||
                  (m['content'] ?? '').contains('检索未找到足够信息')),
        )
        .length;
    final retrievalToolName = _retrievalToolName(availableTools);

    if (lastToolContent.startsWith('检索结果：')) {
      var body = lastToolContent.replaceFirst('检索结果：', '').trim();
      body = _dropGenericCapabilityLine(body);
      if (_isWeatherQuery(query) || _looksLikeWeatherContent(body)) {
        return AssistantModelOutput(
          text: _buildWeatherBriefReply(
            query: query,
            weatherRawText: body,
            messages: messages,
          ),
        );
      }
      if (body.trim().isNotEmpty) {
        return AssistantModelOutput(text: body.trim());
      }
      return AssistantModelOutput(
        text: lastToolContent.replaceFirst('检索结果：', '').trim(),
      );
    }
    if (retrievalToolName != null &&
        lastToolContent.contains('检索成功，但未获得可用摘要。')) {
      if (searchAttempts < 2 && query.trim().isNotEmpty) {
        return AssistantModelOutput(
          text: '上一轮结果信息不足，我再补查一轮最新信息。',
          toolCalls: <AssistantToolCall>[
            AssistantToolCall(
              name: retrievalToolName,
              arguments: <String, dynamic>{
                'query': '$query 最新',
                'requestedCapabilities': const <String>['context.web_search'],
              },
            ),
          ],
        );
      }
      return const AssistantModelOutput(
        text: '我尝试了多轮检索，但结果信息仍不足。你可以补充更具体的关键词（如城市、时间、指标）后我继续查。',
      );
    }
    if (lastToolContent.contains('Web search error') ||
        lastToolContent.contains('检索未找到足够信息')) {
      if (retrievalToolName != null &&
          searchAttempts < 2 &&
          query.trim().isNotEmpty) {
        return AssistantModelOutput(
          text: '上一轮检索失败，我换个查询方式再试一次。',
          toolCalls: <AssistantToolCall>[
            AssistantToolCall(
              name: retrievalToolName,
              arguments: <String, dynamic>{
                'query': query,
                'provider': 'openclaw_proxy',
                'requestedCapabilities': const <String>['context.web_search'],
              },
            ),
          ],
        );
      }
      return const AssistantModelOutput(
        text: '当前网络检索暂不可用。请稍后重试，或先让我基于已知信息给出建议。',
      );
    }
    if (content.contains('搜索') || content.contains('search')) {
      if (retrievalToolName != null) {
        return AssistantModelOutput(
          text: '我先帮你搜索一下。',
          toolCalls: <AssistantToolCall>[
            AssistantToolCall(
              name: retrievalToolName,
              arguments: <String, dynamic>{
                'query': lastUser['content'] ?? '',
                'requestedCapabilities': const <String>[
                  'context.current_page',
                  'context.chat_recent',
                  'context.chat_longterm',
                  'context.web_search',
                ],
              },
            ),
          ],
        );
      }
    }
    if (content.contains('相册') ||
        content.contains('照片') ||
        content.contains('photo')) {
      if (availableTools.contains('media_gallery')) {
        return const AssistantModelOutput(
          text: '我来查看相册信息。',
          toolCalls: <AssistantToolCall>[
            AssistantToolCall(
              name: 'media_gallery',
              arguments: <String, dynamic>{'mode': 'recent'},
            ),
          ],
        );
      }
    }
    if (content.contains('定位') ||
        content.contains('电量') ||
        content.contains('权限')) {
      if (availableTools.contains('local_context')) {
        return const AssistantModelOutput(
          text: '我先读取设备上下文。',
          toolCalls: <AssistantToolCall>[
            AssistantToolCall(
              name: 'local_context',
              arguments: <String, dynamic>{},
            ),
          ],
        );
      }
    }
    if (content.contains('intent') || content.contains('打开')) {
      if (availableTools.contains('intent_bridge')) {
        return AssistantModelOutput(
          text: '我将尝试调用系统 Intent。',
          toolCalls: <AssistantToolCall>[
            AssistantToolCall(
              name: 'intent_bridge',
              arguments: <String, dynamic>{
                'target': '',
                'action': 'android.intent.action.VIEW',
              },
            ),
          ],
        );
      }
    }
    if (retrievalToolName != null) {
      final isQuestionLike =
          content.contains('天气') ||
          content.contains('怎么样') ||
          content.contains('如何') ||
          content.contains('怎样') ||
          content.contains('多少') ||
          content.contains('几号') ||
          content.contains('什么时候') ||
          content.contains('为什么') ||
          content.contains('哪里') ||
          content.contains('哪个') ||
          (content.contains('什么') && query.trim().length > 2);
      if (query.trim().isNotEmpty && isQuestionLike) {
        return AssistantModelOutput(
          text: '我先帮你查一下。',
          toolCalls: <AssistantToolCall>[
            AssistantToolCall(
              name: retrievalToolName,
              arguments: <String, dynamic>{
                'query': query,
                'requestedCapabilities': const <String>[
                  'context.current_page',
                  'context.chat_recent',
                  'context.chat_longterm',
                  'context.web_search',
                ],
              },
            ),
          ],
        );
      }
    }
    return const AssistantModelOutput(
      text: '我已理解你的需求。你可以让我执行搜索、读取相册、查询设备上下文或调用系统 Intent。',
    );
  }

  String? _retrievalToolName(List<String> availableTools) {
    if (availableTools.contains('unified_retrieval')) {
      return 'unified_retrieval';
    }
    if (availableTools.contains('web_search')) return 'web_search';
    return null;
  }

  /// 去掉检索结果中的通用能力说明句，优先保留 [web]/[page.xxx] 等实际内容
  String _dropGenericCapabilityLine(String body) {
    const generic = '我已理解你的需求。你可以让我执行';
    final lines = body.split('\n');
    final kept = lines.where((line) {
      final t = line.trim();
      if (t.isEmpty) return true;
      if (t.contains('[memory]') && t.contains(generic)) return false;
      if (t.contains(generic) && t.length < 80) return false;
      return true;
    });
    return kept.join('\n').replaceAll(RegExp(r'\n{3,}'), '\n\n').trim();
  }

  bool _isWeatherQuery(String query) {
    final lowered = query.toLowerCase();
    return lowered.contains('天气') ||
        lowered.contains('气温') ||
        lowered.contains('降雨') ||
        lowered.contains('体感') ||
        lowered.contains('weather');
  }

  bool _looksLikeWeatherContent(String text) {
    final lowered = text.toLowerCase();
    return lowered.contains('天气') ||
        lowered.contains('气温') ||
        lowered.contains('体感') ||
        lowered.contains('湿度') ||
        lowered.contains('风') ||
        lowered.contains('预报');
  }

  String _buildWeatherBriefReply({
    required String query,
    required String weatherRawText,
    required List<Map<String, String>> messages,
  }) {
    final city = _extractCity(query, weatherRawText);
    final condition = _extractFirstMatch(weatherRawText, <RegExp>[
      RegExp(r'(晴|多云|阴|小雨|中雨|大雨|雷阵雨|暴雨|阵雨|雾|霾)'),
    ]);
    final tempRange = _extractFirstMatch(weatherRawText, <RegExp>[
      RegExp(r'(\d{1,2}\s*[-~]\s*\d{1,2}\s*°?C)'),
      RegExp(r'(\d{1,2}\s*/\s*\d{1,2}\s*°?C)'),
    ]);
    final wind = _extractFirstMatch(weatherRawText, <RegExp>[
      RegExp(r'([东南西北]{0,2}风\d{1,2}级)'),
    ]);
    final humidity = _extractFirstMatch(weatherRawText, <RegExp>[
      RegExp(r'(湿度\s*\d{1,3}%\s*[-~]?\s*\d{0,3}%?)'),
      RegExp(r'(相对湿度\s*\d{1,3}%\s*[-~]?\s*\d{0,3}%?)'),
    ]);

    final pieces = <String>[
      if (condition.isNotEmpty) condition,
      if (tempRange.isNotEmpty) '气温 $tempRange',
      if (wind.isNotEmpty) wind,
      if (humidity.isNotEmpty) humidity,
    ];
    final summaryLine = pieces.isEmpty ? '已获取到最新天气信息。' : pieces.join('，');
    final contextPageType = _extractPageType(messages);
    final advice = _buildWeatherAdvice(summaryLine, contextPageType);
    final followUps = _buildWeatherFollowups(contextPageType, city);

    return [
      '${city.isEmpty ? '当前' : '$city 当前'}天气：$summaryLine',
      advice,
      '你还可以继续问：$followUps',
    ].join('\n');
  }

  String _extractCity(String query, String raw) {
    final qMatch = RegExp(
      r'([\u4e00-\u9fa5]{2,8}(?:市|区|县)?)天气',
    ).firstMatch(query);
    if (qMatch != null) {
      final city = (qMatch.group(1) ?? '').trim();
      if (city.isNotEmpty) return city;
    }
    final rawMatch = RegExp(r'([\u4e00-\u9fa5]{2,8}(?:市|区|县))').firstMatch(raw);
    return (rawMatch?.group(1) ?? '').trim();
  }

  String _extractFirstMatch(String text, List<RegExp> patterns) {
    for (final pattern in patterns) {
      final match = pattern.firstMatch(text);
      if (match == null) continue;
      final value = (match.group(1) ?? match.group(0) ?? '').trim();
      if (value.isNotEmpty) return value;
    }
    return '';
  }

  String _extractPageType(List<Map<String, String>> messages) {
    for (final msg in messages) {
      if (msg['role'] != 'system') continue;
      final content = (msg['content'] ?? '');
      final match = RegExp(r'pageType:\s*([a-zA-Z_]+)').firstMatch(content);
      if (match != null) {
        final value = (match.group(1) ?? '').trim();
        if (value.isNotEmpty) return value;
      }
    }
    return '';
  }

  String _buildWeatherAdvice(String summary, String pageType) {
    if (summary.contains('雨') || summary.contains('雷')) {
      if (pageType == 'create') return '建议优先室内拍摄/创作，外出记得带伞并注意设备防潮。';
      return '建议带伞，优先安排室内行程，通勤预留更多时间。';
    }
    if (summary.contains('高温') ||
        RegExp(r'气温\s*(3\d|[4-9]\d)').hasMatch(summary)) {
      return '建议补水和防晒，中午尽量减少长时间户外活动。';
    }
    if (summary.contains('风') && summary.contains('6级')) {
      return '风力偏大，户外活动注意安全，骑行请降低速度。';
    }
    if (pageType == 'discovery' || pageType == 'circles') {
      return '天气总体适合出行，可优先安排短途户外活动。';
    }
    return '天气总体平稳，可按原计划出行。';
  }

  String _buildWeatherFollowups(String pageType, String city) {
    final area = city.isEmpty ? '本地' : city;
    if (pageType == 'create') {
      return '$area 未来3小时会不会下雨、现在适合拍照的地点、今晚体感温度和穿衣建议';
    }
    if (pageType == 'circles' || pageType == 'discovery') {
      return '$area 今晚是否下雨、明天上下班时段天气、适合户外还是室内活动';
    }
    return '$area 未来3小时降雨概率、今晚体感温度、明天出行穿衣建议';
  }
}
