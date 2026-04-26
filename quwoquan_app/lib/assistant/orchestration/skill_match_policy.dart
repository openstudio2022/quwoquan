import 'package:quwoquan_app/assistant/contracts/app_action_contract.dart';
import 'package:quwoquan_app/assistant/contracts/app_search_contract.dart';
import 'package:quwoquan_app/assistant/contracts/orchestrator_state_contract.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';

class SkillToolRouteDecision {
  const SkillToolRouteDecision({
    required this.toolName,
    this.toolArgs = const TaskToolArgs(),
    this.interactionDirective = const InteractionDirective(),
  });

  final String toolName;
  final TaskToolArgs toolArgs;
  final InteractionDirective interactionDirective;

  bool get hasExecutableTool => toolName.trim().isNotEmpty;
}

class SkillMatchPolicy {
  const SkillMatchPolicy();

  static const String appSearchToolName = 'app_search';
  static const String appActionToolName = 'app_action';
  static const String webSearchToolName = 'web_search';

  SkillToolRouteDecision route(IntentNode intent) {
    final intentType = intent.intentType.trim().toLowerCase();
    final goal = intent.goal.trim();

    if (_isAppSearchIntent(intentType)) {
      return SkillToolRouteDecision(
        toolName: appSearchToolName,
        toolArgs: TaskToolArgs(
          AppSearchRequest(
            query: goal,
            contentTypes: _contentTypesForIntent(intentType),
            filters: _filtersFromIntent(intent),
          ).toJson(),
        ),
      );
    }

    final actionType = _actionTypeForIntent(intentType);
    if (actionType != null) {
      return SkillToolRouteDecision(
        toolName: appActionToolName,
        toolArgs: TaskToolArgs(
          AppActionRequest(
            actionType: actionType,
            args: AppActionArgs(_constraintMap(intent)),
            requiresConfirmation: actionType == AppActionType.sendMessage,
          ).toJson(),
        ),
      );
    }

    if (_requiresUnavailableAction(intentType)) {
      return SkillToolRouteDecision(
        toolName: '',
        interactionDirective: InteractionDirective(
          kind: InteractionDirectiveKind.requiresUserAction,
          intentId: intent.intentId,
          message: '当前缺少可执行的应用能力，需要用户手动完成或授权后继续。',
        ),
      );
    }

    if (intent.requiresEvidence) {
      return SkillToolRouteDecision(
        toolName: webSearchToolName,
        toolArgs: TaskToolArgs(<String, Object?>{'query': goal}),
      );
    }

    return SkillToolRouteDecision(
      toolName: '',
      interactionDirective: InteractionDirective(
        kind: InteractionDirectiveKind.blocked,
        intentId: intent.intentId,
        message: '当前意图没有可用工具可执行。',
      ),
    );
  }

  bool _isAppSearchIntent(String intentType) {
    return intentType.startsWith('app.search') ||
        intentType.startsWith('chat.search') ||
        intentType.startsWith('post.search') ||
        intentType.startsWith('history.search') ||
        intentType.startsWith('user.search') ||
        intentType.startsWith('circle.search');
  }

  List<AppSearchContentType> _contentTypesForIntent(String intentType) {
    if (intentType.startsWith('chat.')) {
      return const <AppSearchContentType>[AppSearchContentType.chatMessage];
    }
    if (intentType.startsWith('post.')) {
      return const <AppSearchContentType>[AppSearchContentType.post];
    }
    if (intentType.startsWith('history.')) {
      return const <AppSearchContentType>[AppSearchContentType.historyPost];
    }
    if (intentType.startsWith('user.')) {
      return const <AppSearchContentType>[AppSearchContentType.user];
    }
    if (intentType.startsWith('circle.')) {
      return const <AppSearchContentType>[AppSearchContentType.circle];
    }
    return const <AppSearchContentType>[
      AppSearchContentType.chatMessage,
      AppSearchContentType.post,
      AppSearchContentType.historyPost,
      AppSearchContentType.user,
      AppSearchContentType.circle,
    ];
  }

  AppSearchFilters _filtersFromIntent(IntentNode intent) {
    final constraints = _constraintMap(intent);
    return AppSearchFilters(
      timeStart: (constraints['timeStart'] as String?)?.trim() ?? '',
      timeEnd: (constraints['timeEnd'] as String?)?.trim() ?? '',
      userId: (constraints['userId'] as String?)?.trim() ?? '',
      username: (constraints['username'] as String?)?.trim() ?? '',
      keywords: constraints['keywords'] is List
          ? (constraints['keywords'] as List)
                .map((item) => item.toString().trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false)
          : const <String>[],
      isMine: constraints['isMine'] is bool
          ? constraints['isMine'] as bool
          : null,
    );
  }

  AppActionType? _actionTypeForIntent(String intentType) {
    switch (intentType) {
      case 'chat.open':
        return AppActionType.openConversation;
      case 'message.send':
        return AppActionType.sendMessage;
      case 'post.open':
        return AppActionType.openPost;
      case 'page.navigate':
        return AppActionType.navigateToPage;
      case 'camera.capture':
        return AppActionType.capturePhoto;
      case 'photo.pick':
        return AppActionType.pickPhoto;
      case 'share':
      case 'content.share':
        return AppActionType.share;
      case 'phone.dial':
        return AppActionType.dial;
    }
    return null;
  }

  bool _requiresUnavailableAction(String intentType) {
    return intentType.endsWith('.book') ||
        intentType.endsWith('.order') ||
        intentType.endsWith('.operate');
  }

  Map<String, Object?> _constraintMap(IntentNode intent) {
    final values = <String, Object?>{};
    for (final constraint in intent.constraints) {
      if (constraint.key.trim().isEmpty) continue;
      values[constraint.key.trim()] = _parseConstraintValue(constraint.value);
    }
    return values;
  }

  Object? _parseConstraintValue(String raw) {
    final value = raw.trim();
    if (value == 'true') return true;
    if (value == 'false') return false;
    final intValue = int.tryParse(value);
    if (intValue != null) return intValue;
    if (value.contains(',')) {
      return value
          .split(',')
          .map((item) => item.trim())
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
    }
    return value;
  }
}
