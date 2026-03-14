export 'package:quwoquan_app/assistant/skills/skill_manifest.dart';
export 'package:quwoquan_app/assistant/tools/tool_schema.dart';

class AssistantCapabilityCatalog {
  const AssistantCapabilityCatalog._();

  static const String currentPage = 'context.current_page';
  static const String pageComments = 'context.page_comments';
  static const String chatRecent = 'context.chat_recent';
  static const String chatLongterm = 'context.chat_longterm';
  static const String behaviorTimeline = 'context.behavior_timeline';
  static const String webSearch = 'context.web_search';

  static const List<String> defaultCatalog = <String>[
    currentPage,
    pageComments,
    chatRecent,
    chatLongterm,
    behaviorTimeline,
    webSearch,
  ];

  static String toPromptText(List<String> capabilityIds) {
    if (capabilityIds.isEmpty) return '暂无可查询能力。';
    return capabilityIds.map((id) => '- $id').join('\n');
  }
}
