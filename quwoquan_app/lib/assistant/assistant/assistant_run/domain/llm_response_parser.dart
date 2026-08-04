import 'dart:convert';

import 'package:quwoquan_app/assistant/assistant/assistant_turn_view/domain/assistant_turn_contract.dart';

/// LLM 响应统一解析器。
///
/// 只接收完整 canonical `assistant_turn` JSON；任何 fence、前后缀、旧字段或
/// 非 canonical shape 均 fail-closed。
class LlmResponseParser {
  LlmResponseParser._();

  /// 将完整响应解析为 typed [AssistantTurnOutput]。
  static LlmParseResult parse(String rawText) {
    final text = rawText.trim();
    if (text.isEmpty) {
      return LlmParseResult.unparsed(raw: rawText, reason: 'empty_input');
    }
    final turn = _tryDecodeCanonicalTurn(text);
    if (turn != null) {
      return LlmParseResult.parsed(turn: turn, raw: rawText);
    }
    return LlmParseResult.unparsed(
      raw: rawText,
      reason: 'invalid_assistant_turn',
    );
  }

  static AssistantTurnOutput? _tryDecodeCanonicalTurn(String text) {
    final decoded = _tryDecodeMap(text);
    if (decoded == null) return null;
    return tryParseAssistantTurnOutput(decoded);
  }

  static Map<String, dynamic>? _tryDecodeMap(String text) {
    try {
      final decoded = jsonDecode(text);
      if (decoded is Map) return decoded.cast<String, dynamic>();
    } catch (_) {
      /* best-effort: 文本非合法 JSON 时返回 null，由上层走非结构化文本解析路径 */
    }
    return null;
  }
}

/// LLM 响应解析结果。
class LlmParseResult {
  const LlmParseResult._({
    required this.ok,
    this.turn,
    required this.raw,
    this.failReason,
  });

  factory LlmParseResult.parsed({
    required AssistantTurnOutput turn,
    required String raw,
  }) => LlmParseResult._(ok: true, turn: turn, raw: raw);

  factory LlmParseResult.unparsed({
    required String raw,
    required String reason,
  }) => LlmParseResult._(ok: false, raw: raw, failReason: reason);

  final bool ok;
  final AssistantTurnOutput? turn;
  final String raw;
  final String? failReason;
}
