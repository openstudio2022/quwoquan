import 'package:quwoquan_app/assistant/infrastructure/llm/llm_response_parser.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';

final RegExp _xmlToolCallTagRe = RegExp(
  r'<tool_call>[\s\S]*?</tool_call>|'
  r'<function=[^>]+>[\s\S]*?</function>|'
  r'<tool_call>|</tool_call>|'
  r'<function=[^>]*>|</function>|'
  r'<parameter=[^>]*>[\s\S]*?</parameter>|'
  r'</?parameter[^>]*>',
);

final RegExp _xmlToolCallOpenRe = RegExp(r'<tool_call>|<function=');

bool isAssistantStreamInternalChunk(String value) {
  final text = value.trim();
  if (text.isEmpty) return false;
  if (text == '</think>' || text == '<think>') return true;
  if (AssistantContentFilters.isJsonEnvelope(text)) return true;
  if (AssistantDisplayTextResolver.containsInternalAssistantProtocolFragment(
    text,
  )) {
    return true;
  }
  if (_xmlToolCallOpenRe.hasMatch(text)) {
    final stripped = text.replaceAll(_xmlToolCallTagRe, '').trim();
    if (stripped.isEmpty) return true;
  }
  if (text.startsWith('{') || text.startsWith('```')) {
    final parsed = LlmResponseParser.parse(text);
    if (parsed.ok) return true;
  }
  return false;
}
