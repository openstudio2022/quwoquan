import 'dart:convert';

import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';

Map<String, dynamic> _structuredPayload(AssistantRunResponse response) {
  final direct = response.structuredResponse;
  if (direct.isNotEmpty) return direct;
  final raw = response.finalText.trim();
  if (raw.isEmpty) return const <String, dynamic>{};
  try {
    final decoded = jsonDecode(raw);
    if (decoded is Map<String, dynamic>) return decoded;
    if (decoded is Map) return decoded.cast<String, dynamic>();
  } catch (_) {}
  return const <String, dynamic>{};
}

String resolveActionLikeCompletedFallback(AssistantRunResponse response) {
  final decision = AssistantTurnDecision.fromMaps(
    structured: _structuredPayload(response),
  );
  final nextAction = decision.nextAction.wireName;
  final messageKind = decision.messageKind.wireName;
  final rawSignals = <String>[
    response.finalText,
    response.displayMarkdown,
    response.displayPlainText,
  ].join('\n');
  final looksActionLike =
      nextAction == 'tool_call' ||
      nextAction == 'retry' ||
      nextAction == 'clarify' ||
      nextAction == 'ask_user' ||
      messageKind == 'progress' ||
      messageKind == 'tool_call' ||
      AssistantDisplayTextResolver.containsUnsafeDisplayProtocolLeak(
        rawSignals,
      );
  if (!looksActionLike) {
    return '';
  }
  if (nextAction == 'ask_user' || nextAction == 'clarify') {
    return '我还需要你再补充一点信息，这样才能继续。';
  }
  if (nextAction == 'retry') {
    return '这次没有拿到可靠结果，请稍后再试一次。';
  }
  return '这个操作我暂时还没拿到可展示结果，请再试一次。';
}
