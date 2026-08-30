import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show AssistantEntryChip;

/// 入口 chip 被点击后要达成的目标，与任何导航实现无关。
enum AssistantEntryChipIntentKind {
  /// 跳到一个已命名的产品位置（圈子、创作等）。
  namedDestination,

  /// 打开设置。
  settings,

  /// 进入助理会话，并把 chip 文案作为首条查询带过去。
  assistantSession,
}

/// chip 已解析出的目标：presentation 只负责执行，不再自己判读 wire 值。
final class AssistantEntryChipIntent {
  const AssistantEntryChipIntent._(this.kind, {this.destination, this.query});

  const AssistantEntryChipIntent.namedDestination(String destination)
    : this._(
        AssistantEntryChipIntentKind.namedDestination,
        destination: destination,
      );

  const AssistantEntryChipIntent.settings()
    : this._(AssistantEntryChipIntentKind.settings);

  const AssistantEntryChipIntent.assistantSession({String? query})
    : this._(AssistantEntryChipIntentKind.assistantSession, query: query);

  final AssistantEntryChipIntentKind kind;

  /// 仅 [AssistantEntryChipIntentKind.namedDestination] 有值。
  final String? destination;

  /// 仅 [AssistantEntryChipIntentKind.assistantSession] 可能有值：带入会话的首条查询。
  final String? query;

  @override
  bool operator ==(Object other) =>
      other is AssistantEntryChipIntent &&
      other.kind == kind &&
      other.destination == destination &&
      other.query == query;

  @override
  int get hashCode => Object.hash(kind, destination, query);
}

/// chip 可以指向的产品位置闭集。
///
/// 服务端只下发标识，端侧把它解析成本枚举；不在册的值一律退回助理会话，
/// 而不是猜一个路由——未知目的地不得表达成某个具体页面。
enum AssistantEntryChipDestination { circles, create }

const Map<String, AssistantEntryChipDestination> _knownDestinations = {
  'circles': AssistantEntryChipDestination.circles,
  'create': AssistantEntryChipDestination.create,
};

/// 把一枚 chip 解析成目标意图。
///
/// 这是 AssistantEntryView 的领域规则：`actionType` 与 `value` 的判读只此一处，
/// Widget 不得再自行 switch wire 值。
AssistantEntryChipIntent resolveAssistantEntryChipIntent(
  AssistantEntryChip chip,
) {
  switch (chip.actionType) {
    case 'route':
      final destination = _knownDestinations[chip.value];
      if (destination == null) {
        return const AssistantEntryChipIntent.assistantSession();
      }
      return AssistantEntryChipIntent.namedDestination(destination.name);
    case 'setting':
      return const AssistantEntryChipIntent.settings();
    case 'command':
    default:
      return AssistantEntryChipIntent.assistantSession(query: chip.label);
  }
}
