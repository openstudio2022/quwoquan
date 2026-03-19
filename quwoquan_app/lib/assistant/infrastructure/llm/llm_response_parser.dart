import 'dart:convert';

/// LLM 响应统一解析器。
///
/// 职责：从 raw text 中提取并解析 JSON，支持多种模型输出格式。
/// 所有 JSON 解析逻辑集中于此，其他文件禁止直接 `jsonDecode` LLM 输出。
class LlmResponseParser {
  LlmResponseParser._();

  static final _fencePattern = RegExp(
    r'```(?:json)?\s*\n?([\s\S]*?)\n?```',
    multiLine: true,
  );
  static final _thinkPattern = RegExp(
    r'<think>[\s\S]*?</think>',
    multiLine: true,
  );
  static final _thinkTagPattern = RegExp(r'</?think>', multiLine: true);

  /// 从 LLM raw text 中提取 JSON 并解析为 [LlmParseResult]。
  ///
  /// 策略链（优先级递减）：
  /// 1. ```json``` fence 提取
  /// 2. 去除 think 标签 + 全文 strip → 直接 jsonDecode
  /// 3. 括号深度块扫描 → 优先选含 `decision` 的块
  /// 4. 全部失败 → 返回 unparsed 结果
  static LlmParseResult parse(String rawText) {
    final text = rawText.trim();
    if (text.isEmpty) {
      return LlmParseResult.unparsed(raw: rawText, reason: 'empty_input');
    }

    // Strategy 1: fence
    final fenceMatch = _fencePattern.firstMatch(text);
    if (fenceMatch != null) {
      final content = fenceMatch.group(1)?.trim() ?? '';
      if (content.isNotEmpty) {
        final result = _tryDecodeAsModelOutput(content);
        if (result != null) {
          return LlmParseResult.parsed(json: result, raw: rawText);
        }
        final sliced = _sliceFirstJsonObject(content);
        if (sliced != null) {
          final result2 = _tryDecodeAsModelOutput(sliced);
          if (result2 != null) {
            return LlmParseResult.parsed(json: result2, raw: rawText);
          }
        }
      }
    }

    // Strategy 2: strip fence + think tags → direct parse
    final cleaned = text
        .replaceAll(RegExp(r'```json\s*', multiLine: true), '')
        .replaceAll(RegExp(r'```\s*', multiLine: true), '')
        .replaceAll(_thinkPattern, '')
        .replaceAll(_thinkTagPattern, '')
        .trim();
    final direct = _tryDecodeAsModelOutput(cleaned);
    if (direct != null) {
      return LlmParseResult.parsed(json: direct, raw: rawText);
    }

    // Strategy 3: bracket-depth block scan
    final blocks = _extractTopLevelJsonBlocks(cleaned);
    Map<String, dynamic>? best;
    for (final block in blocks) {
      final decoded = _tryDecodeMap(block);
      if (decoded == null) continue;
      best ??= decoded;
      if (decoded.containsKey('decision')) {
        return LlmParseResult.parsed(json: decoded, raw: rawText);
      }
      if (decoded.containsKey('userMarkdown')) {
        return LlmParseResult.parsed(json: decoded, raw: rawText);
      }
    }
    if (best != null) {
      return LlmParseResult.parsed(json: best, raw: rawText);
    }

    return LlmParseResult.unparsed(raw: rawText, reason: 'no_valid_json');
  }

  /// 从模型输出 JSON 中提取 `userMarkdown`（快速路径，不做完整解析）。
  static String? extractUserMarkdown(String rawText) {
    final result = parse(rawText);
    if (!result.ok) return null;
    final um = result.explicitUserMarkdown;
    if (um.isNotEmpty) return um;
    return null;
  }

  /// 识别 canonical assistant_turn JSON：返回原始解码 Map，不做兼容拆包。
  static Map<String, dynamic>? _tryDecodeAsModelOutput(String text) {
    final decoded = _tryDecodeMap(text);
    if (decoded == null) return null;

    if (decoded.containsKey('decision')) return decoded;

    final contractId = (decoded['contractId'] as String?)?.trim() ?? '';
    if (contractId == 'assistant_turn') return decoded;

    if (decoded.containsKey('userMarkdown')) return decoded;

    return decoded;
  }

  static Map<String, dynamic>? _tryDecodeMap(String text) {
    try {
      final decoded = jsonDecode(text);
      if (decoded is Map) return decoded.cast<String, dynamic>();
    } catch (_) {}
    return null;
  }

  static String? _sliceFirstJsonObject(String text) {
    final start = text.indexOf('{');
    final end = text.lastIndexOf('}');
    if (start >= 0 && end > start) {
      return text.substring(start, end + 1);
    }
    return null;
  }

  static List<String> _extractTopLevelJsonBlocks(String text) {
    final blocks = <String>[];
    int depth = 0;
    int start = -1;
    for (int i = 0; i < text.length; i++) {
      final ch = text[i];
      if (ch == '{') {
        if (depth == 0) start = i;
        depth++;
      } else if (ch == '}') {
        if (depth > 0) {
          depth--;
          if (depth == 0 && start >= 0) {
            blocks.add(text.substring(start, i + 1));
            start = -1;
          }
        }
      }
    }
    return blocks;
  }
}

/// LLM 响应解析结果。
class LlmParseResult {
  const LlmParseResult._({
    required this.ok,
    this.json,
    required this.raw,
    this.failReason,
  });

  factory LlmParseResult.parsed({
    required Map<String, dynamic> json,
    required String raw,
  }) => LlmParseResult._(ok: true, json: json, raw: raw);

  factory LlmParseResult.unparsed({
    required String raw,
    required String reason,
  }) => LlmParseResult._(ok: false, raw: raw, failReason: reason);

  final bool ok;
  final Map<String, dynamic>? json;
  final String raw;
  final String? failReason;

  /// 从解析结果中提取显式 userMarkdown。
  /// 不再回退到 `result.text`，避免把内部结果文本误当成用户可见回答。
  String get userMarkdown => explicitUserMarkdown;

  /// 仅提取显式用户轨 Markdown，不回退到 result.text。
  String get explicitUserMarkdown {
    if (!ok || json == null) return '';
    final payload = json!;
    final um = (payload['userMarkdown'] as String?)?.trim() ?? '';
    if (um.isNotEmpty) return um;
    return '';
  }

  /// 兼容 canonical result.text / result 字符串。
  String get resultText {
    if (!ok || json == null) return '';
    final payload = json!;
    final result = payload['result'];
    if (result is Map) {
      return (result['text'] as String?)?.trim() ?? '';
    }
    if (result is String) return result.trim();
    return '';
  }

  /// 从解析结果中提取 decision.nextAction
  String get nextAction {
    if (!ok || json == null) return '';
    final payload = json!;
    final decision = payload['decision'];
    if (decision is Map) {
      return (decision['nextAction'] as String?)?.trim() ?? '';
    }
    return '';
  }

  /// 是否为非最终答案（tool_call / ask_user 等中间态）
  bool get isIntermediateAction {
    final action = nextAction;
    return action.isNotEmpty && action != 'answer';
  }
}

/// 引擎元数据（模型不输出，由引擎注入）。
class EngineResponseMeta {
  const EngineResponseMeta({
    this.contractId = 'assistant_turn',
    this.domainId = '',
    this.stateId = '',
    this.detectedEvent = '',
    this.phaseAwareLoaded = const <String>[],
    this.promptTokens = 0,
    this.completionTokens = 0,
    this.latencyMs = 0,
    this.modelId = '',
    this.timestamp,
  });

  final String contractId;
  final String domainId;
  final String stateId;
  final String detectedEvent;
  final List<String> phaseAwareLoaded;
  final int promptTokens;
  final int completionTokens;
  final int latencyMs;
  final String modelId;
  final DateTime? timestamp;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'contractId': contractId,
    'domainId': domainId,
    'stateId': stateId,
    'detectedEvent': detectedEvent,
    'phaseAwareLoaded': phaseAwareLoaded,
    'promptTokens': promptTokens,
    'completionTokens': completionTokens,
    'latencyMs': latencyMs,
    'modelId': modelId,
    'timestamp': (timestamp ?? DateTime.now()).toIso8601String(),
  };
}
