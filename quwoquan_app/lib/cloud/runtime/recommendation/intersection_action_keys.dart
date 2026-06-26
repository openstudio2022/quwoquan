/// 交集动作 `actionKey` 端侧闭集常量。
///
/// 唯一真相源是云侧 metadata：
/// `contracts/metadata/recommendation/rec_model/projections/intersection_action_hint.yaml`
/// 与 `intersection_kind_registry.yaml`。metadata 明确规定「端只读 actionKey / label /
/// target 渲染并分发动作，禁止端侧按 kind 猜测行动」。端在消费 `IntersectionActionHint`
/// 时按本闭集分发（助手类 → 打开小艺解释；其余结构化动作 → 经统一导航到 target），
/// 文案一律取 `hint.label`，不在端侧再造。
///
/// 注：actionKey 在 codegen DTO 中为开放 String；本类把 metadata 闭集固化为端侧分发键，
/// 消除魔法字符串散落（如旧实体页 `'ask_xiaoqu'` 死分支——该值全仓从无产出）。
abstract final class IntersectionActionKeys {
  static const String followPerson = 'follow_person';
  static const String greetPerson = 'greet_person';
  static const String messagePerson = 'message_person';
  static const String viewSharedPeople = 'view_shared_people';
  static const String joinCircle = 'join_circle';
  static const String openDiscussion = 'open_discussion';
  static const String openContent = 'open_content';
  static const String openObject = 'open_object';
  static const String followObject = 'follow_object';
  static const String openRoute = 'open_route';
  static const String createFollowup = 'create_followup';
  static const String askAssistant = 'ask_assistant';

  // §交集行动深化：同趣 / 同行 / 线下 / 实时 / 意图 行动阶梯（与 registry actionHintLegend 同源）。
  static const String joinTopicRoom = 'join_topic_room';
  static const String startCompanion = 'start_companion';
  static const String joinTrip = 'join_trip';
  static const String joinMeetup = 'join_meetup';
  static const String meetNearby = 'meet_nearby';
  static const String startVoiceRoom = 'start_voice_room';
  static const String expressInterest = 'express_interest';

  /// 助手类动作：点击该交集行打开小艺解释 / 追问，而非导航到对象页。
  static bool isAssistant(String actionKey) {
    final key = actionKey.trim();
    return key == askAssistant || key == createFollowup;
  }

  /// 重社交行动（同行 / 线下 / 实时 / 心动）：进入破冰阶梯或同频连接专属落点，
  /// 非简单对象下钻；端侧据此决定是否走打招呼请求 / 建群 / 报名等专属流程。
  static bool isHeavySocialAction(String actionKey) {
    final key = actionKey.trim();
    return key == joinTopicRoom ||
        key == startCompanion ||
        key == joinTrip ||
        key == joinMeetup ||
        key == meetNearby ||
        key == startVoiceRoom ||
        key == expressInterest;
  }
}
