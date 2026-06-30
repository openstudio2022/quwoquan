/// 「找同趣 / 兴趣配对」页固定文案集中地。
///
/// 守 `verify_dart_semantic`：UI 层禁止硬编码中文字面量，固定 UI 文案统一在此。
/// 本页是**发现启动器（launcher）**，不渲染业务候选列表，因此不含昵称 / 结论句 /
/// 外链图等业务数据文案（业务数据来自既有真实面的 Repository / seed）。
class InterestMatchTextConstants {
  InterestMatchTextConstants._();

  /// 顶部利益表达。
  static const String lead = '今天想找哪种同趣？';

  /// 顶部利益表达副说明。
  static const String leadSubtitle = '按兴趣锚点出发，遇见同趣的人、圈子与想去的地方。';

  // ==================== 今日同趣机会 ====================
  static const String todayTitle = '今日同趣机会';
  static const String todaySubtitle = '基于你的交集与最近浏览生成，进入「我的交集」逐条行动。';
  static const String todayCta = '查看我的交集';

  // ==================== 兴趣配对 · 发现入口 ====================
  static const String matchTitle = '兴趣配对';
  static const String matchSubtitle = '选择一种发现方式，找到可以行动的同趣对象。';

  static const String findPeopleTitle = '找同趣的人';
  static const String findPeopleSubtitle = '按共同关注、共同圈子与亲和力发现可破冰的人。';

  static const String findCirclesTitle = '找相关圈子';
  static const String findCirclesSubtitle = '加入与你兴趣交集的圈子，进讨论、看作品。';

  static const String findPlacesTitle = '找想去的地方';
  static const String findPlacesSubtitle = '发现有人想去 / 去过的地点，标记想去或发起同行。';

  /// 按兴趣搜索入口。
  static const String searchCta = '按兴趣搜索同趣';

  // ==================== 安全与风控提示 ====================
  static const String safetyNote = '附近默认模糊位置；打招呼、同行、线下局等重行动前会校验登录 / 实名 / 青少年模式 / 双向同意。';
}
