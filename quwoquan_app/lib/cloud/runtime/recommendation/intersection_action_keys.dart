import '../generated/recommendation/intersection_kind_metadata.g.dart';

/// 交集动作 `actionKey` 端侧闭集常量与路由分类。
///
/// 唯一真相源是云侧 metadata：
/// `quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_model_release/intersection_kind_registry.yaml`
/// 与 `intersection_kind_metadata.g.dart`（codegen 下发的 `intersectionActionKeyMeta`）。
/// metadata 明确规定「端只读 actionKey / label / target / dispatch 渲染并分发动作，
/// 禁止端侧按 kind 猜测行动，也禁止端手写『哪些 actionKey 属助手/约伴』第二份枚举」。
///
/// - String 常量：把 metadata 闭集固化为端侧分发键，消除魔法字符串散落
///   （如旧实体页 `'ask_xiaoqu'` 死分支——该值全仓从无产出）。
/// - 分类判定（isAssistant / isGatheringAction）：一律委托 codegen
///   `IntersectionActionKeyMeta.dispatch`（M0.7 行动路由类别 dispatch 一等化），
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

  // §交集行动深化：同趣 / 同行 / 线下 / 实时 / 意图 行动阶梯（与 registry actionHintLegend 同源）。
  static const String joinTopicRoom = 'join_topic_room';
  static const String startGathering = 'start_gathering';
  static const String joinGathering = 'join_gathering';
  static const String meetNearby = 'meet_nearby';
  static const String expressInterest = 'express_interest';
  static const String viewOfficialDeals = 'view_official_deals';
  static const String bookTicket = 'book_ticket';
  static const String bookHotel = 'book_hotel';

  /// 助手类动作（dispatch==assistant，即 ask_assistant / create_followup）：
  /// 点击该交集行打开小艺解释 / 追问 / 续写，而非导航到对象页。
  /// 真相源为 codegen `IntersectionActionKeyMeta.dispatch`（M0.7），未知 key 安全返回 false。
  static bool isAssistant(String actionKey) {
    return IntersectionActionKeyMeta.of(actionKey)?.isAssistant ?? false;
  }

  /// 同行 / 线下约伴类动作（dispatch==gathering，即 start_gathering /
  /// join_gathering / meet_nearby）：唯一驱动「有人同行」徽标与约伴专属落点。
  /// 真相源为 codegen `IntersectionActionKeyMeta.dispatch`（M0.7）；话题房 / 语音房 /
  /// 心动（dispatch==connect）与私信（dispatch==message）不属此类，不再误标为同行。
  static bool isGatheringAction(String actionKey) {
    return IntersectionActionKeyMeta.of(actionKey)?.isGathering ?? false;
  }

  /// 商用转化动作（dispatch==commerce）：真实渠道和法务条款未就绪时必须保持
  /// targetAvailability=deferred 或被端侧 feature flag 拦截，不得伪造交易。
  static bool isCommerce(String actionKey) {
    return IntersectionActionKeyMeta.of(actionKey)?.dispatch == 'commerce';
  }
}
