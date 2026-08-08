import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/generated/intersection_client_policy.g.dart';

/// 交集动作 `actionKey` 端侧闭集常量与路由分类。
///
/// 唯一真相源是云侧 metadata：
/// `quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_model_release/intersection_kind_registry.yaml`
/// 与 `intersection_client_policy.g.dart`（codegen 下发的 typed policy）。
/// metadata 明确规定「端只读 actionKey / label / target / dispatch 渲染并分发动作，
/// 禁止端侧按 kind 猜测行动，也禁止端手写『哪些 actionKey 属助手/约伴』第二份枚举」。
///
/// - String 常量：把 metadata 闭集固化为端侧分发键，消除魔法字符串散落
///   （如旧实体页 `'ask_xiaoqu'` 死分支——该值全仓从无产出）。
/// - 分类判定（isAssistant / isGatheringAction）：一律委托 codegen
///   `IntersectionActionPolicy.dispatch`（M0.7 行动路由类别 dispatch 一等化），
///   端不再手写重社交/助手集合，杜绝与 registry 漂移的第二真相源。
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

  static const String startGathering = 'start_gathering';

  /// 助手类动作（dispatch==assistant，即 ask_assistant / create_followup）：
  /// 点击该交集行打开小艺解释 / 追问 / 续写，而非导航到对象页。
  /// 真相源为 codegen `IntersectionActionPolicy.dispatch`（M0.7），未知 key 安全返回 false。
  static bool isAssistant(String actionKey) {
    return policyFor(actionKey)?.isAssistant ?? false;
  }

  /// 聚集类动作（dispatch==gathering）：驱动聚集入口与专属落点。
  static bool isGatheringAction(String actionKey) {
    return policyFor(actionKey)?.isGathering ?? false;
  }

  /// 将 wire action key 安全解析为 canonical typed policy。
  ///
  /// 未知/退役 key 返回 null；不调用 throwing decoder，也不维护第二张映射表。
  static IntersectionActionPolicy? policyFor(String? actionKey) {
    final normalized = actionKey?.trim() ?? '';
    if (normalized.isEmpty) return null;
    for (final entry in intersectionActionPolicies.entries) {
      if (entry.key.wireName == normalized) return entry.value;
    }
    return null;
  }
}
