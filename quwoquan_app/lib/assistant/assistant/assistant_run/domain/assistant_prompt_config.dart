import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';

/// 推荐操作 chip：文案与行为类型（发指令/跳转/设置等）。
class AssistantChipEntry {
  const AssistantChipEntry({
    required this.label,
    this.actionType = 'command',
    this.value,
  });

  final String label;
  final String actionType;
  final String? value;
}

/// 按 (source, tab/entityKind, experienceLevel) 提供欢迎句、推荐 chips 与「当前适合干啥」。
class AssistantPromptConfig {
  AssistantPromptConfig._();

  /// 根据 [context] 返回一句上下文欢迎文案。
  static String getWelcomeMessage(AssistantOpenContext context) {
    final level = _levelKey(context.experienceLevel);
    final tab = context.tab ?? context.dimension ?? '';
    final key = '${context.source.name}_${tab}_$level';
    return _welcomeMap[key] ??
        _welcomeMap['${context.source.name}_$level'] ??
        _welcomeMap['default']!;
  }

  static String _levelKey(ExperienceLevel l) {
    switch (l) {
      case ExperienceLevel.firstTime:
        return 'firstTime';
      case ExperienceLevel.returning:
        return 'returning';
      case ExperienceLevel.frequent:
        return 'frequent';
    }
  }

  static const Map<String, String> _welcomeMap = {
    'default': AssistantText.assistantPromptWelcomeDefault,
    'discovery_firstTime': AssistantText.assistantPromptDiscoveryFirstTime,
    'discovery_returning': AssistantText.assistantPromptDiscoveryReturning,
    'discovery_frequent': AssistantText.assistantPromptDiscoveryFrequent,
    'circles_firstTime': AssistantText.assistantPromptCirclesFirstTime,
    'circles_returning': AssistantText.assistantPromptCirclesReturning,
    'circles_frequent': AssistantText.assistantPromptCirclesFrequent,
    'chat_firstTime': AssistantText.assistantPromptChatFirstTime,
    'chat_returning': AssistantText.assistantPromptChatReturning,
    'chat_frequent': AssistantText.assistantPromptChatFrequent,
    'profile_firstTime': AssistantText.assistantPromptProfileFirstTime,
    'profile_returning': AssistantText.assistantPromptProfileReturning,
    'profile_frequent': AssistantText.assistantPromptProfileFrequent,
    'create_firstTime': AssistantText.assistantPromptCreateFirstTime,
    'create_returning': AssistantText.assistantPromptCreateReturning,
    'create_frequent': AssistantText.assistantPromptCreateFrequent,
    'article_firstTime': AssistantText.assistantPromptArticleFirstTime,
    'article_returning': AssistantText.assistantPromptArticleReturning,
    'article_frequent': AssistantText.assistantPromptArticleFrequent,
  };

  /// 根据 [context] 返回 3～5 个推荐 chips（首次偏教学向，常用偏效率向）。
  static List<AssistantChipEntry> getChips(AssistantOpenContext context) {
    switch (context.experienceLevel) {
      case ExperienceLevel.firstTime:
        return [
          AssistantChipEntry(
            label: AssistantText.assistantCommandFind,
            actionType: 'command',
            value: 'find',
          ),
          const AssistantChipEntry(
            label: AssistantText.assistantPromptDiscussionManagement,
            actionType: 'route',
            value: 'circles',
          ),
          const AssistantChipEntry(
            label: AssistantText.assistantPromptDarkMode,
            actionType: 'setting',
            value: 'theme',
          ),
        ];
      case ExperienceLevel.returning:
        return [
          AssistantChipEntry(
            label: AssistantText.assistantCommandFind,
            actionType: 'command',
            value: 'find',
          ),
          AssistantChipEntry(
            label: AssistantText.assistantCommandRemember,
            actionType: 'command',
            value: 'remember',
          ),
          const AssistantChipEntry(
            label: AssistantText.assistantPromptPinnedSubscription,
            actionType: 'route',
            value: 'circles',
          ),
        ];
      case ExperienceLevel.frequent:
        return [
          AssistantChipEntry(
            label: AssistantText.assistantCommandFind,
            actionType: 'command',
            value: 'find',
          ),
          AssistantChipEntry(
            label: AssistantText.assistantCommandShare,
            actionType: 'command',
            value: 'share',
          ),
          const AssistantChipEntry(
            label: AssistantText.assistantPromptDirectPublish,
            actionType: 'route',
            value: 'create',
          ),
        ];
    }
  }

  /// 根据 [context] 返回 1～2 条「当前适合干啥」文案。
  static List<String> getSuggestionLines(AssistantOpenContext context) {
    final tab = context.tab ?? '';
    final level = context.experienceLevel;
    final lines = <String>[];
    if (context.source == AssistantSource.discovery && tab.isNotEmpty) {
      if (level == ExperienceLevel.returning ||
          level == ExperienceLevel.frequent) {
        lines.add(AssistantText.assistantPromptFindSimilar);
      }
    }
    if (context.source == AssistantSource.create) {
      if (context.hints['hasAddedMedia'] == true) {
        lines.add(AssistantText.assistantPromptCreateCopyOrSchedule);
      }
    }
    if (lines.isEmpty) {
      lines.add(AssistantText.assistantPromptChooseOrDescribe);
    }
    return lines;
  }
}
