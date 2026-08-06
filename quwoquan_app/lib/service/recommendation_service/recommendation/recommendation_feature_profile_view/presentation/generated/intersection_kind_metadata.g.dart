// Code generated from the canonical intersection registry. DO NOT EDIT.
// Source: recommendation/recommendation/recommendation_model_release/intersection_kind_registry.yaml
// ignore_for_file: prefer_const_constructors

/// 行动建议 actionKey 闭集（registry.actionHintLegend，端只读分发，不按 kind 猜测）。
const List<String> intersectionActionKeys = <String>["ask_assistant", "create_followup", "follow_object", "follow_person", "greet_person", "join_circle", "message_person", "open_content", "open_discussion", "open_object", "open_route", "start_gathering", "view_shared_people"];

/// 单个 actionKey 的行动阶梯元数据（registry.actionKeyMeta，§24 M0.1/M0.3/M0.7）。
/// 端据 requiredGates 判断「可执行 / 优雅降级」；tier 区分轻查看/重社交；
/// dispatch 表示端交互 handler 路由类别（assistant|navigate|message|gathering），
/// 端 navigator/徽标/助手分发读本字段，禁止端手写「哪些 actionKey 属助手/约伴」第二份枚举（M0.7）。
class IntersectionActionKeyMeta {
  const IntersectionActionKeyMeta({
    required this.tier,
    required this.requiredGates,
    required this.dispatch,
  });

  final String tier;
  final List<String> requiredGates;
  final String dispatch;

  bool get isHeavy => tier == 'heavy';
  /// 助手类：点击打开小艺解释/追问/续写，而非导航到对象页。
  bool get isAssistant => dispatch == 'assistant';
  /// 同行/线下约伴类：唯一驱动「有人同行」徽标与约伴专属落点。
  bool get isGathering => dispatch == 'gathering';
  /// 重社交连接类（私信/约伴，需破冰阶梯/请求/建群），非简单对象下钻。
  bool get isSocialConnect =>
      dispatch == 'message' || dispatch == 'gathering';

  /// 由 actionKey 查行动阶梯元数据；未知 key 返回 null（端据此安全降级）。
  static IntersectionActionKeyMeta? of(String? actionKey) {
    if (actionKey == null) return null;
    return intersectionActionKeyMeta[actionKey.trim()];
  }
}

/// actionKey → 行动阶梯元数据表（单一真相源 registry.actionKeyMeta 下发）。
const Map<String, IntersectionActionKeyMeta> intersectionActionKeyMeta = <String, IntersectionActionKeyMeta>{
  "ask_assistant": IntersectionActionKeyMeta(
    tier: "light",
    requiredGates: <String>[],
    dispatch: "assistant",
  ),
  "create_followup": IntersectionActionKeyMeta(
    tier: "heavy",
    requiredGates: <String>["login", "realName"],
    dispatch: "assistant",
  ),
  "follow_object": IntersectionActionKeyMeta(
    tier: "light",
    requiredGates: <String>["login"],
    dispatch: "navigate",
  ),
  "follow_person": IntersectionActionKeyMeta(
    tier: "light",
    requiredGates: <String>["login"],
    dispatch: "navigate",
  ),
  "greet_person": IntersectionActionKeyMeta(
    tier: "light",
    requiredGates: <String>["login", "greetPreference", "blocked"],
    dispatch: "message",
  ),
  "join_circle": IntersectionActionKeyMeta(
    tier: "light",
    requiredGates: <String>["login"],
    dispatch: "navigate",
  ),
  "message_person": IntersectionActionKeyMeta(
    tier: "heavy",
    requiredGates: <String>["login", "mutualConsent", "blocked", "rateLimit"],
    dispatch: "message",
  ),
  "open_content": IntersectionActionKeyMeta(
    tier: "light",
    requiredGates: <String>[],
    dispatch: "navigate",
  ),
  "open_discussion": IntersectionActionKeyMeta(
    tier: "light",
    requiredGates: <String>["login"],
    dispatch: "navigate",
  ),
  "open_object": IntersectionActionKeyMeta(
    tier: "light",
    requiredGates: <String>[],
    dispatch: "navigate",
  ),
  "open_route": IntersectionActionKeyMeta(
    tier: "light",
    requiredGates: <String>[],
    dispatch: "navigate",
  ),
  "start_gathering": IntersectionActionKeyMeta(
    tier: "heavy",
    requiredGates: <String>["login", "realName", "minorMode", "blocked", "rateLimit"],
    dispatch: "gathering",
  ),
  "view_shared_people": IntersectionActionKeyMeta(
    tier: "light",
    requiredGates: <String>["login"],
    dispatch: "navigate",
  ),
};
