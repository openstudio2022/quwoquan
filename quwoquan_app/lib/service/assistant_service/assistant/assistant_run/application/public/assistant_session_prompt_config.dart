import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/assistant_prompt_config.dart'
    as internal;
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';

typedef AssistantChipEntry = internal.AssistantChipEntry;

/// AssistantSession 空态消费的窄提示配置 API。
abstract final class AssistantSessionPromptConfig {
  static String getWelcomeMessage(AssistantOpenContext context) {
    return internal.AssistantPromptConfig.getWelcomeMessage(context);
  }

  static List<AssistantChipEntry> getChips(AssistantOpenContext context) {
    return internal.AssistantPromptConfig.getChips(context);
  }

  static List<String> getSuggestionLines(AssistantOpenContext context) {
    return internal.AssistantPromptConfig.getSuggestionLines(context);
  }
}
