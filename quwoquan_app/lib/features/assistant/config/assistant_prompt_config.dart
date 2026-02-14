import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/features/assistant/context/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';

/// 推荐操作 chip：文案与行为类型（发指令/跳转/设置等）。
class AssistantChipEntry {
  const AssistantChipEntry({required this.label, this.actionType = 'command', this.value});

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
    return _welcomeMap[key] ?? _welcomeMap['${context.source.name}_$level'] ?? _welcomeMap['default']!;
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
    'default': '有什么想让我帮忙的？',
    'discovery_firstTime': '你在发现页，第一次来这儿～找内容、管频道或调设置都可以跟我说。',
    'discovery_returning': '又来看发现了，需要帮你找、帮你记还是做别的？',
    'discovery_frequent': '老地方了，直接说你想干啥～',
    'circles_firstTime': '你在圈子页，第一次来～想找圈子、管订阅或发内容都可以找我。',
    'circles_returning': '又来看圈子了，需要帮你找、帮你记还是做别的？',
    'circles_frequent': '圈子常客了，直接说你想干啥～',
    'chat_firstTime': '你在聊天，第一次从这里找我～发消息、找人或管设置都可以。',
    'chat_returning': '又来找我了，需要帮你找、帮你记还是发点什么？',
    'chat_frequent': '直接说你想干啥～',
    'profile_firstTime': '你在个人页，第一次从这里找我～改资料、管分身或设置都可以。',
    'profile_returning': '又来看个人页了，需要帮你记、帮你办还是做别的？',
    'profile_frequent': '直接说你想干啥～',
    'create_firstTime': '你在创作，第一次从这里找我～配文案、定时发或找灵感都可以。',
    'create_returning': '又在创作了，需要帮你配文案、帮你发还是做别的？',
    'create_frequent': '创作老手了，直接说你想干啥～',
    'article_firstTime': '你在看内容，第一次从这里找我～总结、推荐或记一笔都可以。',
    'article_returning': '又来看这篇了，需要帮你读、帮你记还是做别的？',
    'article_frequent': '直接说你想干啥～',
  };

  /// 根据 [context] 返回 3～5 个推荐 chips（首次偏教学向，常用偏效率向）。
  static List<AssistantChipEntry> getChips(AssistantOpenContext context) {
    switch (context.experienceLevel) {
      case ExperienceLevel.firstTime:
        return [
          AssistantChipEntry(label: UITextConstants.assistantCommandFind, actionType: 'command', value: 'find'),
          const AssistantChipEntry(label: '频道管理', actionType: 'route', value: 'circles'),
          const AssistantChipEntry(label: '深色模式', actionType: 'setting', value: 'theme'),
        ];
      case ExperienceLevel.returning:
        return [
          AssistantChipEntry(label: UITextConstants.assistantCommandFind, actionType: 'command', value: 'find'),
          AssistantChipEntry(label: UITextConstants.assistantCommandRemember, actionType: 'command', value: 'remember'),
          const AssistantChipEntry(label: '订阅置顶', actionType: 'route', value: 'circles'),
        ];
      case ExperienceLevel.frequent:
        return [
          AssistantChipEntry(label: UITextConstants.assistantCommandFind, actionType: 'command', value: 'find'),
          AssistantChipEntry(label: UITextConstants.assistantCommandShare, actionType: 'command', value: 'share'),
          const AssistantChipEntry(label: '直接发', actionType: 'route', value: 'create'),
        ];
    }
  }

  /// 根据 [context] 返回 1～2 条「当前适合干啥」文案。
  static List<String> getSuggestionLines(AssistantOpenContext context) {
    final tab = context.tab ?? '';
    final level = context.experienceLevel;
    final lines = <String>[];
    if (context.source == AssistantSource.discovery && tab.isNotEmpty) {
      if (level == ExperienceLevel.returning || level == ExperienceLevel.frequent) {
        lines.add('可以让我帮你找类似风格的内容');
      }
    }
    if (context.source == AssistantSource.create) {
      if (context.hints['hasAddedMedia'] == true) {
        lines.add('可以让我帮你配文案或定时发');
      }
    }
    if (lines.isEmpty) {
      lines.add('说一句你想做的事，或选上面的推荐试试');
    }
    return lines;
  }
}
