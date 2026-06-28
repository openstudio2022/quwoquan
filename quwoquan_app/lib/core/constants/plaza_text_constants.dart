/// 同频/广场（社交连接）页面 UI 固定文案常量。
///
/// 守 `verify_dart_semantic`：UI 层禁止硬编码中文字面量，固定文案统一在此集中。
/// 业务数据文案（昵称、结论句、标签等）来自 Repository 的 canonical/seed，不在此处。
class PlazaTextConstants {
  PlazaTextConstants._();

  // ==================== 四 tab ====================
  static const String tabAffinity = '同趣';
  static const String tabCompanion = '同行';
  static const String tabNearby = '附近';
  static const String tabMeetup = '局';

  // ==================== 区块 / chip ====================
  static const String sharedInterestsLabel = '共同兴趣';
  static const String seeAllLabel = '查看全部';
  static const String fuzzyLocationHint = '模糊位置';
  static const String mutualConsentHint = '打招呼后，对方同意才能继续聊天';

  // ==================== 加载态 ====================
  static const String loadingLabel = '正在为你寻找同频的人…';

  // ==================== 空态 ====================
  static const String emptyAffinityTitle = '还没有发现同趣的人';
  static const String emptyAffinitySubtitle = '去内容里逛逛，留下你的兴趣足迹';
  static const String emptyCompanionTitle = '还没有结伴计划';
  static const String emptyCompanionSubtitle = '在喜欢的目的地发起一次结伴';
  static const String emptyNearbyTitle = '附近暂时没有同频的人';
  static const String emptyNearbySubtitle = '换个时间再来看看';
  static const String emptyMeetupTitle = '还没有可报名的局';
  static const String emptyMeetupSubtitle = '发起一个局，邀请同城同好';

  // ==================== 错误态 ====================
  static const String errorTitle = '加载失败';
  static const String errorRetry = '重新加载';

  // ==================== 权限态（附近定位） ====================
  static const String permissionTitle = '开启定位，发现附近同频的人';
  static const String permissionSubtitle = '只展示模糊距离，不会暴露你的精确位置';
  static const String permissionGrant = '开启定位';

  // ==================== 破冰 / 行动反馈 ====================
  static const String actionSentTitle = '已发起';
  static const String actionCancel = '取消';
  static const String actionConfirm = '确定';

  static String actionSentMessage(String label) =>
      '「$label」已发送，等待对方回应';

  // ==================== 独立页标题 ====================
  static const String nearbyPageTitle = '附近同趣';
  static const String companionPageTitle = '结伴出发';
  static const String meetupPageTitle = '线下局';

  // ==================== 实体页 / 对象页行动区 ====================
  static const String entityCompanionSectionTitle = '想去 · 正在去 · 结伴';
  static const String entityCompanionSectionSubtitle = '和也想来这里的人结伴出发';
  static const String entityWantToGoLabel = '想去';
  static const String entityOnTheWayLabel = '正在去';
  static const String entityCompanionLabel = '结伴';
  static const String objectActionZoneEmptyHint = '成为第一个在这里留下交集的人';

  // ==================== 发现流连接徽章（展示态） ====================
  static const String feedBadgeEntity = '实体';
  static const String feedBadgeCircle = '圈子';
  static const String feedBadgeCompanion = '有人同行';
}
