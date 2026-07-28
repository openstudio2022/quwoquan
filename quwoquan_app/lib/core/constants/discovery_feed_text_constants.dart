/// 首页推荐 feed 与交集（intersection）展示文案。
///
/// 从 [UITextConstants] 拆出的内聚常量类（R03 文件行数预算收口）：覆盖首页关注
/// feed 空态、推荐 feed 实时刷新 pill / 负反馈即时确认、我的交集收件箱、交集生命周期弱标、
/// 维度短标签、共同点 chip、交集 spotlight 与影响明细样本文案。
/// 真相源仍为服务端枚举 / 投影，端侧仅做展示，不自造结论。
class DiscoveryFeedText {
  // ==================== 首页推荐 feed ====================
  // 首页 feed 负反馈即时确认提示（不感兴趣 / 屏蔽作者 / 减少此类内容）。
  static const String feedNegativeFeedbackNotInterested = '将减少这类内容';
  static const String feedNegativeFeedbackAuthorReduced = '将减少该作者的内容';
  static const String feedNegativeFeedbackContentReduced = '将减少相似内容';

  // 首页关注流成功空态：只陈述尚无关注动态，不冒充推荐结果或错误。
  static const String followingFeedEmptyTitle = '还没有关注动态';
  static const String followingFeedEmptyDescription =
      '关注感兴趣的人后，他们发布的新内容会出现在这里。';

  // 首页推荐实时更新入口（顶部 pill）：点击触发用户主动刷新，不自动插入/跳位。
  static const String feedRealtimeUpdateHint = '有新内容，点击刷新';
  static String feedRealtimeNewContentBadge(int count) => '$count 条新内容，点击刷新';

  // ==================== 交集入口与解释 ====================
  static const String intersectionMoreLabel = '全部交集';
  // Work Browser 作者区交集入口与详情解释层（V1.0：N 个交集 › → 弹出推荐解释）
  static String intersectionEntrySummary(int count) => '$count 个交集';
  static const String intersectionDetailTitle = '与你相关的线索';
  static const String homeFeedIntersectionReasonLabel = '推荐理由';

  // ==================== 我的交集收件箱 ====================
  // V5 口径（user-profile-intersection-redesign S2b / 主任务 V5 成功标准）：
  // 我的主页交集模块统一命名「我的交集」，与他人主页「我与TA的交集」并列为列表入口。
  static const String myIntersectionsTitle = '我的交集';
  static const String intersectionViewAll = '查看全部';
  static const String intersectionFilterAll = '全部';
  static const String intersectionFilterPeople = '人';
  static const String intersectionFilterCircles = '圈子';
  static const String intersectionFilterPlaces = '地点';
  static const String intersectionFilterInterests = '兴趣';
  static const String impactFilterRecords = '记录';
  static const String impactFilterDiscussions = '讨论';
  static const String impactFilterHomepage = '主页';
  static const String intersectionTimeBucketToday = '今天';
  static const String intersectionTimeBucketYesterday = '昨天';
  static const String intersectionTimeBucketLast7Days = '近 7 天';
  static const String intersectionTimeBucketThisMonth = '本月';
  static const String intersectionTimeBucketLastMonth = '上月';
  static const String intersectionTimeBucketEmpty = '暂无交集';
  static const String intersectionTimelineRecentLimitNote = '仅展示最近 90 天的交集变化';
  static String intersectionTimelineBucketCount(int count) => '$count条';
  static const String myIntersectionsSubtitle = '最近谁和你有了新的共同点';
  static const String intersectionExpandMore = '展开';
  static const String intersectionCollapse = '收起';
  static const String intersectionNewBadgeSuffix = '条新增';
  static const String intersectionAffinityLabel = '推荐';

  // ==================== 交集行动建议按钮文案 ====================
  /// `actionKey` → 行动按钮微文案。
  ///
  /// actionKey 闭集真相源 = `intersection_kind_registry.yaml.actionHintLegend`
  /// （codegen 下发 `intersectionActionKeys` 校验）；按 kind 选哪个 action 由 codegen
  /// [IntersectionKindMetadata.primaryActionKey] / `actionHints` 决定。本表只承载
  /// UI 按钮文字（mock G2 模拟云侧下发的 `hint.label`），不再在 Repository / 句式合成器
  /// 各自硬编码第二份 actionKey→文案 switch。
  static const Map<String, String> intersectionActionLabels = <String, String>{
    'follow_person': '关注',
    'greet_person': '打招呼',
    'message_person': '发消息',
    'view_shared_people': '查看共同关注',
    'join_circle': '加入圈子',
    'open_discussion': '进入讨论',
    'open_content': '查看内容',
    'open_object': '进入主页',
    'follow_object': '关注对象',
    'open_route': '查看路线',
    'create_followup': '写续篇',
    'ask_assistant': '解释这条交集',
    // §交集行动深化：同趣 / 同行 / 线下 / 实时 / 意图 行动阶梯按钮文案。
    'join_topic_room': '进话题群',
    'start_companion': '发起结伴',
    'join_trip': '加入同行',
    'join_meetup': '报名',
    'meet_nearby': '附近碰头',
    'start_voice_room': '进语音房',
    'express_interest': '打个招呼',
    // §交集商用闭环：commerce 契约位，真实渠道未接入前由 feature flag / deferred 闸拦截。
    'view_official_deals': '看官方优惠',
    'book_ticket': '订门票',
    'book_hotel': '订住宿',
  };

  /// `actionKey` → 行动按钮文案；未知 key 回退助手解释（与 `ask_assistant` 同义）。
  static String intersectionActionLabel(String actionKey) =>
      intersectionActionLabels[actionKey.trim()] ??
      intersectionActionLabels['ask_assistant']!;

  // ==================== 影响明细 sheet ====================
  // 影响明细 sheet（统一交互子契约落地：展示云侧样本，不编造全量）
  static const String impactEvidenceSheetSourceLabel = '来源';
  static const String impactEvidenceSheetSampleLabel = '相关连接样本';
  static const String impactEvidenceSheetFullPendingNote =
      '完整名单将稍后开放，以下仅为云侧部分样本';
  static const String impactEvidenceSheetNoSampleNote = '完整名单将稍后开放，暂未提供可展示样本';
  // 完整明细分页（R-ID03 端侧下钻闭合）：以被影响内容为载体逐条展示，不暴露具体用户身份。
  static const String impactEvidenceSheetDetailLabel = '完整来源明细';
  static const String impactEvidenceSheetLoadMore = '加载更多';
  static const String impactEvidenceSheetLoadFailed = '影响明细加载失败';
  static const String impactEvidenceSheetEmptyNote = '暂无可展示的影响明细';

  // ==================== 交集生命周期 / 维度 ====================
  // 交集生命周期弱标（§21.3，仅弱标/红点，不进结论句；真相源为服务端 lifecycleState 枚举）
  static const String intersectionLifecycleNew = '新';
  static const String intersectionLifecycleStrengthened = '增强';
  static const String intersectionLifecycleReactivated = '重新活跃';
  static const String intersectionLifecycleArchived = '历史记录';
  static const Map<String, String> intersectionLifecycleLabels =
      <String, String>{
        'new': intersectionLifecycleNew,
        'strengthened': intersectionLifecycleStrengthened,
        'reactivated': intersectionLifecycleReactivated,
        // archived 默认不进 inbox（§22.3 端侧过滤），仅历史筛选/对象页弱标展示。
        'archived': intersectionLifecycleArchived,
      };

  /// 生命周期弱标短文案；stable/weakened/expired 无标（返回空串，端不渲染弱标）。
  static String intersectionLifecycleLabel(String state) =>
      intersectionLifecycleLabels[state.trim()] ?? '';

  /// 传播视图二跳扩散计数弱标前缀（§21.4，仅可证绝对计数，禁百分比/漏斗）。
  static const String intersectionPropagationSecondarySpreadPrefix = '再传播';
  // 交集维度短标签（端展示用，真相源仍为服务端 dimension 枚举）
  static const Map<String, String> intersectionDimensionShortLabels =
      <String, String>{
        'identity': '身份',
        'location': '足迹',
        'content': '内容',
        'relationship': '关系',
        'interest': '兴趣',
      };

  static String intersectionDimensionShortLabel(String dimension) =>
      intersectionDimensionShortLabels[dimension] ?? dimension;

  // ==================== 共同点 chip ====================
  /// 共同点安静 chip：「N 共同点」。
  static String intersectionSharedChip(int count) => '$count 共同点';

  /// 共同点计数安静 chip：「N 个共同点」（事实通道）。
  static String intersectionPointCountChip(int count) => '$count 个共同点';

  /// 推荐共同点计数安静 chip：「N 个推荐共同点」（affinity 通道，明示推荐）。
  static String intersectionRecommendedPointCountChip(int count) =>
      '$count 个推荐共同点';

  // ==================== 交集 spotlight ====================
  /// 首页/频道交集模块头：「N 位与你有交集」（N 为红色数字，文案不含数字）。
  static const String intersectionSpotlightHeaderPrefix = '个对象与你有关';

  /// 首页/频道交集模块安静轻提示（不含数量，等高封面卡上方一行）。
  static const String intersectionSpotlightSubtitle = '这些人和地方与你有关';

  /// 首页/频道交集推荐「换一批」入口（候选窗内轮转，强调保鲜）。
  static const String intersectionShuffle = '换一批';

  /// 交集对象类型统一品牌蓝角标文字（闭集 person|circle|school|place|enterprise）。
  static const Map<String, String> intersectionObjectKindBadgeLabels =
      <String, String>{
        'person': '人',
        'circle': '圈',
        'school': '校',
        'place': '地',
        'enterprise': '企',
      };

  static String intersectionObjectKindBadgeLabel(String objectKindName) =>
      intersectionObjectKindBadgeLabels[objectKindName] ?? '';
  static const String intersectionRecommendSpotlightTitle = '与你有关的新对象';
  static const String intersectionCampusSpotlightTitle = '校园里与你有关的人和圈子';
  static const String intersectionTravelSpotlightTitle = '和你有相同足迹的人与地点';
}
