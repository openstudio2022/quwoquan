/// Gathering 创建与详情页的生产中文文案唯一入口。
///
/// 页面仍通过 typed copy model 消费这些常量；local_contract 的探针文案只留在
/// test/support，不进入 production `lib/**`。
abstract final class GatheringText {
  static const String createPageTitle = '发起活动';
  static const String createPurposeSection = '活动内容';
  static const String createTitleLabel = '活动标题';
  static const String createTitlePlaceholder = '用一句话说明这次活动';
  static const String createSummaryLabel = '活动说明';
  static const String createSummaryPlaceholder = '说明活动安排、参与方式和注意事项';
  static const String createSourceReferencesLabel = '关联内容';
  static const String createScheduleSection = '时间安排';
  static const String createTimezoneLabel = '时区';
  static const String createStartAtLabel = '开始时间';
  static const String createEndAtLabel = '结束时间';
  static const String createAdmissionClosesAtLabel = '报名截止时间';
  static const String createDateTimePlaceholder = '例如 2026-08-08 10:00';
  static const String createPlaceSection = '活动地点';
  static const String createPlaceModeLabel = '活动形式';
  static const String createPlaceModePhysical = '线下';
  static const String createPlaceModeOnline = '线上';
  static const String createPlaceModeHybrid = '线上与线下';
  static const String createCoarsePlaceLabel = '公开地点';
  static const String createExactMeetingPointLabel = '准确集合点';
  static const String createOnlineLocationLabel = '线上入口';
  static const String createPolicySection = '参与规则';
  static const String createAudienceLabel = '可见范围';
  static const String audiencePublic = '公开';
  static const String audienceUnlisted = '不公开展示';
  static const String audienceCommunityMembers = '圈子成员';
  static const String audienceInviteOnly = '仅受邀者';
  static const String createAdmissionLabel = '加入方式';
  static const String admissionOpen = '直接加入';
  static const String admissionApproval = '申请后加入';
  static const String admissionInviteOnly = '仅限邀请';
  static const String createCapacityLabel = '人数上限';
  static const String createTimeDisclosureLabel = '时间展示';
  static const String createPlaceDisclosureLabel = '地点展示';
  static const String createRosterDisclosureLabel = '成员展示';
  static const String disclosureExact = '完整展示';
  static const String disclosureDateOnly = '仅展示日期';
  static const String disclosureCoarse = '仅展示大致地点';
  static const String disclosureAfterJoin = '加入后展示';
  static const String rosterCountOnly = '仅展示人数';
  static const String rosterJoinedMembers = '展示已加入成员';
  static const String rosterPublicOptIn = '仅展示同意公开的成员';
  static const String createRiskControlPolicyLabel = '安全策略';
  static const String createHostSection = '发起身份';
  static const String createHostKindLabel = '发起主体';
  static const String createHostPersona = '个人身份';
  static const String createHostEntity = '地点主页';
  static const String createHostCircle = '圈子';
  static const String createHostSubjectIdLabel = '主体标识';
  static const String createAuthorityEvidenceLabel = '授权凭证';
  static const String createAuthorityVersionLabel = '授权版本';
  static const String createCreatorParticipatesLabel = '我也参加本次活动';
  static const String createSubmitAction = '发布活动';
  static const String retryAction = '重试';
  static const String createInvalidFormMessage = '请补全活动信息后再发布';
  static const String createDraftStepLabel = '正在创建活动';
  static const String createRoomStepLabel = '正在准备活动群聊';
  static const String createPublishStepLabel = '正在发布活动';
  static const String createCompletedStepLabel = '活动已发布';

  static const String sourceRecentGatheringsTitle = '近期行动';
  static String sourceGatheringSeatsRemaining(int count) => '余 $count 席';
  static const String sourceGatheringFullLabel = '已满';

  /// 「我的行动」入口与分组页（REQ-008；只消费 ListGatheringsByHost 公开披露面）。
  static const String myGatheringsTitle = '我的行动';
  static const String myGatheringsEntryHint = '我发起的公开行动';
  static String myGatheringsUpcomingBadge(int count) => '$count 个即将开始';
  static const String myGatheringsSegmentUpcoming = '即将开始';
  static const String myGatheringsSegmentDraft = '草稿';
  static const String myGatheringsSegmentEnded = '已结束';
  static const String myGatheringsSegmentCancelled = '已取消';
  static const String myGatheringsEmptyTitle = '还没有公开行动';
  static const String myGatheringsEmptyDescription =
      '从一条交集出发发起第一次行动，成行后会沉淀在这里。';
  static const String myGatheringsSegmentEmpty = '该分组暂无行动';

  /// 四锚点诚实社会证明（只用成形/经历两级；organizer 锚点另有发起级）。
  static const String detailOrganizerStatsLabel = '发起人往绩';
  static String detailOrganizerStats(
    int published,
    int formed,
    int experienced,
  ) => '发起 $published 次 · 成形 $formed 次 · 经历 $experienced 次';
  static String sourceFormedCountLabel(int formed) => '$formed 次行动从这里成行';

  /// 经历内容溯源标（works 详情态两种语义，L0 氛围层）。
  static const String provenanceRecapBadge = '来自一次共同行动';
  static const String provenanceSeedBadge = '他们从这条内容出发，一起去了';

  /// 双人邀约（1对1 同好邀约）。
  static const String duoInviteFailedToast = '邀请发送失败，可在行动详情中重新邀请';
  static const String invitationCardAccept = '接受';
  static const String invitationCardDecline = '婉拒';
  static const String invitationCardTitlePrefix = '邀你同行：';
  static const String invitationDeclinedFeedback = '已婉拒邀请';
  static const String invitationActionFailedToast = '操作失败，请稍后重试';
  static const String inviteCandidatesLabel = '从有交集的同好中选';

  static const String detailPageTitle = '活动详情';
  static const String detailEmptyTitle = '暂时无法读取活动';
  static const String detailHostLabel = '发起方';
  static const String detailTimeLabel = '活动时间';
  static const String detailPlaceLabel = '活动地点';
  static const String detailPrivatePlaceLabel = '加入后可查看准确地点';
  static const String detailCapacityLabel = '参与人数';
  static const String detailPolicyLabel = '参与方式';
  static const String detailRequirementsLabel = '参与要求';
  static const String detailRevisionsLabel = '活动更新';
  static const String detailJoinAction = '加入活动';
  static const String detailApplyAction = '申请加入';
  static const String detailAcceptInvitationAction = '接受邀请';
  static const String detailWatchAvailabilityAction = '关注空位';
  static const String detailEnterChatAction = '进入活动群聊';
  static const String detailReadOnlyAction = '活动已结束';
  static const String detailHostConsoleTitle = '活动管理';
  static const String detailApplicationsTitle = '加入申请';
  static const String detailApplicationAnswersLabel = '申请回答';
  static const String detailApproveAction = '同意';
  static const String detailRejectAction = '拒绝';
  static const String detailInviteTitle = '邀请参与者';
  static const String detailPersonaIdLabel = '用户标识';
  static const String detailInviteAction = '发送邀请';
  static const String detailRosterTitle = '参与成员';
  static const String detailRemoveAction = '移出活动';
  static const String detailCapacityAction = '调整人数上限';
  static const String detailPauseAdmissionAction = '暂停加入';
  static const String detailResumeAdmissionAction = '恢复加入';
  static const String detailMaterialUpdateAction = '更新活动信息';
  static const String detailCancelAction = '取消活动';
  static const String detailStartAction = '开始活动';
  static const String detailOutcomeAction = '记录活动结果';
  static const String detailReasonLabel = '原因';
  static const String detailOccurredOutcome = '活动已按计划完成';
  static const String detailDidNotHappenOutcome = '活动未举行';
  static const String detailEndedEarlyOutcome = '活动提前结束';
  static const String detailSafetyTerminatedOutcome = '因安全原因终止';
  static const String detailDisputedOutcome = '活动结果有争议';
  static const String detailUnverifiedOutcome = '活动结果待确认';
  static const String detailNoRequirements = '暂无额外参与要求';
  static const String detailRecapAction = '发布回顾';
  static const String detailSharedExperienceTitle = '共同经历';
  static const String detailSharedExperienceSingleTitle = '个人回顾';
  static const String detailSharedExperienceEndedEmpty = '行动时间已结束';
}
