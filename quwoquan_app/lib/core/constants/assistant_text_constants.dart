/// Assistant 域专属用户文案。
///
/// 业务代码直接消费本域常量，避免继续扩大全局文案大桶。
abstract final class AssistantText {
  static const String assistantCommandRead = '帮我读';
  static const String assistantCommandRemember = '帮我记';
  static const String assistantCommandHandle = '帮我办';
  static const String assistantCommandShare = '帮我发';
  static const String assistantCommandFind = '帮我找';
  static const String assistantCommandPlan = '帮我排';
  static const String assistantActionNoRemind = '不再提醒';
  static const String assistantFeedbackSavedToMemory = '已加入记忆';
  static const String assistantSupportingCapabilities = '配套能力';
  static const String assistantSkillCenter = '技能中心';
  static const String assistantMemorySectionTitle = '偏好与记忆';
  static const String assistantMemoryEmpty = '暂无已保存的显式偏好';
  static const String assistantMemoryUntitled = '未命名偏好';
  static const String assistantMemoryFrequentLocations = '常用地点';
  static const String assistantMemoryFamilyTerms = '家庭称谓';
  static const String assistantMemoryDietaryRestrictions = '饮食禁忌';
  static const String assistantMemoryTravelPreferences = '出行偏好';
  static const String assistantMemorySourceConfirmedSession = '来自已确认会话';
  static const String assistantMemorySourceManagement = '来自记忆管理';
  static const String assistantMemorySourceExplicitRewrite = '来自回答偏好调整';
  static const String assistantPreferenceDefaultsTitle = '长期回答偏好';
  static const String assistantPreferenceConcise = '简洁';
  static const String assistantPreferenceDetailed = '详细';
  static const String assistantPreferenceCasual = '口语化';
  static const String assistantPreferenceDeepThink = '深入分析';
  static const String assistantPreferenceProfessional = '专业';
  static const String assistantPreferenceWarm = '温和';
  static const String assistantPreferenceSessionScope = '仅当前会话';
  static const String assistantPreferenceLongTermScope = '后续会话';
  static const String assistantPreferenceForget = '遗忘';
  static const String assistantPreferenceForgot = '已遗忘该偏好';
  static const String assistantPreferenceUndo = '撤销';
  static const String assistantSkillCenterOngoingTasksTitle = '进行中任务';
  static const String assistantSkillCenterNoOngoingTasks = '暂无进行中的任务';
  static const String assistantSkillCenterNoSubscribedSkills = '暂无已订阅技能';
  static const String assistantSkillCategoryOther = '其他';
  static const String assistantSkillSubscribed = '已订阅';
  static const String assistantSkillPaused = '已暂停';
  static const String assistantSkillEnabled = '已启用';
  static const String assistantSkillDisabled = '已停用';
  static const String assistantSkillConsentRequired = '需授权';
  static const String assistantSkillConsentGranted = '数据已授权';
  static const String assistantSkillConsentGrant = '允许所需数据';
  static const String assistantSkillConsentRevoke = '撤回数据授权';
  static const String assistantSkillProactiveReminder = '主动提醒';
  static const String assistantSkillProactiveAdd = '添加提醒';
  static const String assistantSkillProactiveNotConfigured = '未设置主动提醒';
  static const String assistantSkillRequiredConsentScopes = '必要授权';
  static const String assistantSkillOptionalConsentScopes = '可选授权';
  static const String assistantSkillSetupPersonalization = '个性化设置';
  static const String assistantSkillSetupTargetUsers = '适合谁';
  static const String assistantSkillSetupSurfaces = '可使用位置';
  static const String assistantSkillSetupDataUse = '数据使用';
  static const String assistantSkillSetupSave = '保存设置';
  static const String assistantSkillSetupRequiredFieldMarker = ' *';
  static const String assistantSkillSetupListPlaceholder = '多项请用逗号分隔';
  static const String assistantSkillSetupUnavailable = '设置暂不可用';
  static const String assistantSkillSetupUnavailableDescription =
      '当前 Skill package 没有提供此版本可安全渲染的设置定义。你仍可使用或停用该 Skill。';
  static const String assistantSkillSetupSaveFailed = '设置没有保存，请稍后重试。';
  static const String assistantSkillSubscriptionSetupTitle = '设置主动提醒';
  static const String assistantSkillSubscriptionSetupDescription =
      '小趣会按设定时间检查你关注的变化；静默时段、频控和最终投递仍由服务端策略控制。';
  static const String assistantSkillSubscriptionTopicTitle = '提醒关注什么';
  static const String assistantSkillSubscriptionTopicPlaceholder =
      '例如：行程天气、交通变化和集合时间';
  static const String assistantSkillSubscriptionTimeTitle = '每天检查时间';
  static const String assistantSkillSubscriptionTimezoneLabel =
      '北京时间（Asia/Shanghai）';
  static const String assistantSkillSubscriptionEnable = '开启主动提醒';
  static const String assistantSkillSubscriptionTopicRequired = '请填写要关注的变化';
  static String assistantSkillSubscriptionDefaultTopic(String skillName) =>
      '提醒我关注$skillName的重要变化和下一步';
  static const String assistantSkillPackageSkillCount = '个技能';
  static const String assistantSkillStatusPendingSync = '状态待同步';
  static const String assistantSkillDetailsAndSettings = '详情与设置';
  static const String assistantConnectorTitle = '连接的应用';
  static const String assistantConnectorDescription =
      '小趣只会使用你明确授权的能力，凭证不会进入技能、聊天或圈子。';
  static const String assistantConnectorEmpty = '暂无可连接的应用';
  static const String assistantConnectorConnected = '已连接';
  static const String assistantConnectorDisconnected = '未连接';
  static const String assistantConnectorRevoked = '已断开';
  static const String assistantConnectorPendingNative = '等待设备授权能力接入';
  static const String assistantConnectorDisconnect = '断开连接';
  static const String assistantConnectorDisconnectConfirmTitle = '确认断开应用？';
  static const String assistantConnectorDisconnectConfirmBody =
      '断开后，小趣会在下一个安全边界停止使用该应用能力。';
  static const String assistantConnectorRecentActivity = '最近活动';
  static const String assistantSkillDataControlTitle = '权限与记忆';
  static const String assistantSkillDataControlDescription =
      '查看已授权的内容访问和已确认记忆，可随时撤销或忘记。';
  static const String assistantSkillDataControlAction = '管理权限与记忆';
  static const String assistantSkillLifecycleAction = '活动与数据管理';
  static const String assistantSkillLifecycleTitle = 'Skill 活动与数据';
  static const String assistantSkillActivityTitle = '最近活动';
  static const String assistantSkillActivityEmpty = '暂无活动记录';
  static const String assistantSkillActivityRetry = '重试';
  static const String assistantSkillDataControlChoiceTitle = '选择要执行的数据操作';
  static const String assistantSkillDataControlHideActivity = '隐藏此 Skill 的活动历史';
  static const String assistantSkillDataControlRevokeConsent =
      '撤回此 Skill 的数据授权';
  static const String assistantSkillDataControlArchiveSubscriptions =
      '归档此 Skill 的主动提醒';
  static const String assistantSkillDataControlCreate = '创建确认请求';
  static const String assistantSkillDataControlConfirmTitle = '确认执行这些操作？';
  static const String assistantSkillDataControlConfirmBody =
      '操作只会作用于当前 Skill；执行前会以最新 revision 再次确认。';
  static const String assistantSkillDataControlConfirm = '确认执行';
  static const String assistantSkillDataControlCancel = '取消请求';
  static const String assistantSkillDataControlPending = '等待确认';
  static const String assistantSkillDataControlExecuting = '正在后台执行';
  static const String assistantSkillDataControlCompleted = '已完成';
  static const String assistantSkillDataControlCancelled = '已取消';
  static const String assistantSkillDataControlFailed = '执行未完成';
  static const String assistantSkillDataControlResume = '恢复处理';
  static const String assistantSkillDataControlUnknownResultRetry =
      '创建结果尚未确认，使用同一请求重试';
  static const String assistantSkillActivityRunAccepted = '任务已接收';
  static const String assistantSkillActivityRunOrienting = '正在理解目标';
  static const String assistantSkillActivityRunPlanning = '正在规划';
  static const String assistantSkillActivityRunExecuting = '正在执行';
  static const String assistantSkillActivityRunObserving = '正在核对结果';
  static const String assistantSkillActivityRunReflecting = '正在反思补充';
  static const String assistantSkillActivityRunCheckpointing = '正在保存进度';
  static const String assistantSkillActivityRunWaitingUser = '等待补充信息';
  static const String assistantSkillActivityRunWaitingApproval = '等待确认';
  static const String assistantSkillActivityRunWaitingExternal = '等待外部结果';
  static const String assistantSkillActivityRunPaused = '任务已暂停';
  static const String assistantSkillActivityRunSynthesizing = '正在整理结果';
  static const String assistantSkillActivityRunVerifying = '正在完成验收';
  static const String assistantSkillActivityRunCompleted = '任务已完成';
  static const String assistantSkillActivityRunFailed = '任务未完成';
  static const String assistantSkillActivityRunCancelled = '任务已取消';
  static const String assistantSkillActivityConsentGranted = '已授予数据权限';
  static const String assistantSkillActivityConsentRevoked = '已撤回数据权限';
  static const String assistantSkillActivitySubscriptionActive = '主动提醒已启用';
  static const String assistantSkillActivitySubscriptionPaused = '主动提醒已暂停';
  static const String assistantSkillActivitySubscriptionArchived = '主动提醒已归档';
  static const String assistantTaskStatusPending = '待处理';
  static const String assistantTaskStatusInProgress = '进行中';
  static const String assistantTaskStatusCompleted = '已完成';
  static const String assistantTaskStatusCancelled = '已取消';
  static const String assistantTaskUntitled = '未命名任务';
  static const String assistantFeedbackTaskDraftCreated = '已生成待办草案';
  static const String assistantFeedbackShareDraftCreated = '已生成分享草稿';
  static const String assistantFeedbackPlanCreated = '已生成安排建议';
  static const String assistantFeedbackRemindLater = '已设为稍后提醒';
  static const String assistantFeedbackReduceProactive = '已减少主动提醒';
  static const String assistantFeedbackOptimizeRecommendation = '收到，将优化推荐';
  static const String assistantFeedbackAddedToLater = '已加入稍后处理';
  static const String assistantTabSchedule = '日程';
  static const String assistantTabSkills = '技能';
  static const String assistantEntryFindPersonal = '找私助';
  static const String assistantEntryAsk = '问小趣';
  static const String assistantEntryXiaoqu = '小趣';

  /// 半弹窗：进入完整对话按钮
  static const String assistantHalfSheetEnterFullChat = '进入完整对话';

  /// 半弹窗：输入框占位
  static const String assistantHalfSheetInputPlaceholder = '说点什么或选上面试试';

  /// 半弹窗：「当前适合干啥」区块标题
  static const String assistantHalfSheetSuggestionTitle = '当前适合干啥';
  static const String assistantPromptWelcomeDefault = '有什么想让我帮忙的？';
  static const String assistantPromptDiscoveryFirstTime =
      '你在发现页，第一次来这儿～找内容、管讨论或调设置都可以跟我说。';
  static const String assistantPromptDiscoveryReturning =
      '又来看发现了，需要帮你找、帮你记还是做别的？';
  static const String assistantPromptDiscoveryFrequent = '老地方了，直接说你想干啥～';
  static const String assistantPromptCirclesFirstTime =
      '你在圈子页，第一次来～想找圈子、管订阅或发内容都可以找我。';
  static const String assistantPromptCirclesReturning =
      '又来看圈子了，需要帮你找、帮你记还是做别的？';
  static const String assistantPromptCirclesFrequent = '圈子常客了，直接说你想干啥～';
  static const String assistantPromptChatFirstTime =
      '你在聊天，第一次从这里找我～发消息、找人或管设置都可以。';
  static const String assistantPromptChatReturning = '又来找我了，需要帮你找、帮你记还是发点什么？';
  static const String assistantPromptChatFrequent = '直接说你想干啥～';
  static const String assistantPromptProfileFirstTime =
      '你在个人页，第一次从这里找我～改资料、管分身或设置都可以。';
  static const String assistantPromptProfileReturning =
      '又来看个人页了，需要帮你记、帮你办还是做别的？';
  static const String assistantPromptProfileFrequent = '直接说你想干啥～';
  static const String assistantPromptCreateFirstTime =
      '你在创作，第一次从这里找我～配文案、定时发或找灵感都可以。';
  static const String assistantPromptCreateReturning =
      '又在创作了，需要帮你配文案、帮你发还是做别的？';
  static const String assistantPromptCreateFrequent = '创作老手了，直接说你想干啥～';
  static const String assistantPromptArticleFirstTime =
      '你在看内容，第一次从这里找我～总结、推荐或记一笔都可以。';
  static const String assistantPromptArticleReturning =
      '又来看这篇了，需要帮你读、帮你记还是做别的？';
  static const String assistantPromptArticleFrequent = '直接说你想干啥～';
  static const String assistantPromptDiscussionManagement = '讨论管理';
  static const String assistantPromptDarkMode = '深色模式';
  static const String assistantPromptPinnedSubscription = '订阅置顶';
  static const String assistantPromptDirectPublish = '直接发';
  static const String assistantPromptFindSimilar = '可以让我帮你找类似风格的内容';
  static const String assistantPromptCreateCopyOrSchedule = '可以让我帮你配文案或定时发';
  static const String assistantPromptChooseOrDescribe = '说一句你想做的事，或选上面的推荐试试';
  static const String assistantCloudSessionSummary = '找私助云端会话';
  static const String assistantFeedbackUsefulLabel = '有用';
  static const String assistantFeedbackIrrelevantLabel = '不相关';
  static const String assistantFeedbackTooFrequentLabel = '太频繁';
  static const String assistantFeedbackRecordedLabel = '已记录';
  static String assistantFeedbackRecorded(String label) => '已记录反馈：$label';
  static String assistantProactiveReminderOpened(String text) =>
      '已打开主动提醒：$text';
  static const String assistantProactiveReminderOpenedDefault = '已打开主动提醒。';
  static const String assistantProactiveReminderSource = '来自云侧主动触发';
  static const String assistantCurrentUserSenderName = '我';
  static String assistantReferenceIndexed(int index) => '参考来源 $index';
  static const String assistantTaskReminderTitle = '今日待办提醒';
  static const String assistantActionNeedsMoreInfo = '我还需要你再补充一点信息，这样才能继续。';
  static const String assistantActionResultUnavailable =
      '这个操作我暂时还没拿到可展示结果，请再试一次。';
  static const String assistantDeviceActionPermissionDenied =
      '未获得系统日历权限，本次没有创建日程。请允许日历权限后重试。';
  static const String assistantDeviceActionUnavailable =
      '当前设备没有可写的系统日历，本次没有创建日程。';
  static const String assistantDeviceActionFailed = '系统日历创建失败，本次没有创建日程，请重试。';
  static const String assistantCardCompare = '对比卡片';
  static const String assistantCardTrend = '趋势卡片';
  static const String assistantCardDiagram = '结构图';
  static const String assistantActionCasual = '更口语化';
  static const String assistantActionDeepThink = '深度思考';
  static const String assistantGenerationStopped = '已停止生成。';
  static const String assistantStopGenerating = '停止生成';
  static const String assistantPauseRun = '暂停任务';
  static const String assistantResumeRun = '继续任务';
  static const String assistantHistoryTitle = '历史会话';
  static const String assistantHistoryEmpty = '还没有历史会话';
  static const String assistantNewSession = '新会话';
  static const String assistantHistoryDefaultTitle = '小趣对话';
  static const String assistantRegenerateStylePrefixConcise = '请更简洁地重新回答：';
  static const String assistantRegenerateStylePrefixDetailed = '请更详细地重新回答：';
  static const String assistantRegenerateStylePrefixCasual = '请用更口语化的方式重新回答：';
  static const String assistantRegenerateStylePrefixDeepThink = '请深入思考后重新回答：';

  static const String assistantPanelTitleSuffix = '智能助手';
  static const String assistantPanelSubtitle = '可总结图片与评论，给出推荐与标注信息';
  static const String assistantAskPlaceholder = '可以问：这张图有什么亮点？';
  static const String assistantSuggestedQuestionsTitle = '推荐问题';
  static const String assistantAskAboutSummary = '帮我总结这张图片';
  static const String assistantAskAboutOutfit = '分析人物穿搭/风格';
  static const String assistantAskAboutLocation = '这可能是什么地方';
  static const String assistantAskAboutRecommendations = '给出相关推荐';
  static const String assistantAskAboutComments = '结合评论给出观点';
  static const String assistantInitialSummaryPrefix = '我已经浏览了当前内容：';
  static const String assistantInitialSummaryNoContent =
      '我已经浏览了当前图片，可以帮你总结亮点、推荐类似内容或解析拍摄信息。';
  static const String assistantInitialSummaryTitleLabel = '标题：';
  static const String assistantInitialSummaryCaptionLabel = '配文：';
  static const String assistantPromptFollowUp = '你还可以继续问我：';
  static const String assistantAutoResponsePrefix = '收到，我来看看：';
  static const String assistantCardHighlightsTitle = '图片亮点';
  static const String assistantCardHighlightsBody = '构图集中在主体与光影对比，画面层次清晰。';
  static const String assistantCardCommentsTitle = '评论总结';
  static const String assistantCardCommentsBody = '当前讨论聚焦于拍摄地点与色调风格。';
  static const String assistantCardRecommendationsTitle = '推荐内容';
  static const String assistantCardRecommendationsBody = '可以看看同风格拍摄与相似场景合集。';

  static const String assistantHome = '助理主页';

  /// 助手 run 失败时展示的通用提示（会话/存储/模型等任一步骤异常均会触发）
  static const String assistantUnavailable = '助手暂时不可用，请稍后重试。';
  static const String assistantTurnFailedFallback = '找私助执行遇到问题，请稍后重试。';
  static const String assistantModelUnavailable =
      '当前未配置可用模型，请先在模型配置中接入远程模型或桥接服务。';
  static const String assistantRunningHint = '小趣正在规划与执行中...';

  /// 用户视角阶段：先帮用户理清问题
  static const String assistantPhaseUnderstanding = '理解问题';

  /// 用户视角阶段：替用户核对资料（工具执行，由元数据覆盖）
  static const String assistantPhaseSearching = '检索设计';

  /// 用户视角阶段：替用户整理判断
  static const String assistantPhaseAnalyzing = '检索处理';

  /// 用户视角阶段：替用户组织最终回答
  static const String assistantPhaseAnswering = '生成答案';

  /// 用户视角阶段：确认当前信息是否已经够答
  static const String assistantPhaseAssessing = '我在确认现在的信息够不够回答';

  /// 用户视角阶段：完成
  static const String assistantPhaseCompleted = '已为你整理好';
  static const String assistantFeedbackHelpful = '有帮助';
  static const String assistantFeedbackUnhelpful = '没帮助';
  static const String assistantFeedbackCorrect = '纠正';
  static const String assistantFeedbackSubmitted = '已记录你的反馈';
  static const String assistantFeedbackReasonTitle = '请选择问题原因';
  static const String assistantFeedbackReasonOffTopic = '答非所问';
  static const String assistantFeedbackReasonInsufficient = '信息不足';
  static const String assistantFeedbackReasonIncorrect = '事实不准';
  static const String assistantFeedbackReasonStyle = '表达不清晰';
  static const String assistantFeedbackReasonPrivacy = '隐私顾虑';
  static const String assistantCorrectionTitle = '补充纠正';
  static const String assistantCorrectionHint = '告诉我你期望的正确表达';
  static const String assistantActionRegenerate = '重新生成';
  static const String assistantActionBrief = '更加简洁';
  static const String assistantActionDetailed = '更加详细';
  static const String assistantActionSwitchModel = '模型切换';
  static const String assistantModelSelectorEntry = '模型';
  static const String assistantModelSelectorSingle = '单模型';
  static const String assistantModelSelectorCount = '%s 个模型';
  static const String assistantModelSelectorEmpty = '未选择';
  static const String assistantModelSelectorTitle = '选择模型';
  static const String assistantModelSelectorHint = '选择当前对话使用的模型';
  static const String assistantModelSelectorConfirm = '应用';
  static const String assistantModelSelectorApplied = '已切换为 %m';
  static const String assistantSearchingReferenceCount = '参考 %s 篇资料';
  static const String assistantReferenceCopied = '链接已复制';
  static const String assistantReferenceActionTitle = '引用链接';
  static const String assistantReferenceOpenInBrowser = '在浏览器中打开';
  static const String assistantReferenceCopyLink = '复制链接';
  static const String assistantReferenceOpenFailed = '链接打开失败，已复制到剪贴板';
  static const String assistantReferenceHostBlocked = '该链接域名未通过安全白名单，已复制到剪贴板';
  static const String assistantReferenceSectionTitle = '参考来源';
  static const String assistantReferenceSectionHint = '点击编号查看原文';
  static const String assistantProcessSearching = '正在搜索';
  static const String assistantProcessOrganizing = '正在整理';
  static const String assistantProcessAnswering = '正在回答';
  static const String assistantProcessCompleted = '已完成';
  static const String assistantProcessModelCallCountTemplate = '模型调用 %s 次';
  static const String assistantProcessTokensTemplate = '%s tokens';
  static const String assistantProcessElapsedTemplate = '耗时 %s 秒';
  static const String assistantProcessStatusActive = '进行中';
  static const String assistantProcessStatusCompleted = '已完成';
  static const String assistantProcessStatusSkipped = '已跳过';
  static const String assistantProcessStatusFailed = '待补稳';
  static const String assistantProcessProcessedCountTemplate = '搜索 %s 篇';
  static const String assistantProcessAcceptedCountChipTemplate = '接纳 %s 篇';
  static const String assistantProcessReferenceCountTemplate = '接纳 %s 篇资料';
  static const String assistantProcessReferenceDigestTemplate =
      '搜索了 %s 篇，接纳了 %s 篇';
  static const String assistantProcessStepProgressTemplate = '已完成 %s/%s 步';
  static const String assistantProcessRunningSummary = '处理过程';
  static const String assistantProcessCompletedSummary = '已完成处理';
  static const String assistantProcessCompletedSummaryReferencesTemplate =
      '已完成处理，处理 %s 篇文档';
  static const String assistantProcessCompletedSummaryElapsedTemplate =
      '已完成处理，耗时 %s 秒';
  static const String assistantProcessCompletedSummaryFullTemplate =
      '已完成处理，处理 %s 篇文档，耗时 %s 秒';
  static const String assistantProcessFinalAnswerNarrative =
      '已结合检索与核对结果生成最终回答。';
  static const String assistantProcessStageUnderstand = '理解问题';
  static const String assistantProcessStageSearch = '检索设计';
  static const String assistantProcessStageRetrievalDesign = '检索设计';
  static const String assistantProcessStageRetrievalProcessing = '检索处理';
  static const String assistantProcessStageAnalyze = '检索处理';
  static const String assistantProcessStageVerify = '检索处理';
  static const String assistantProcessStageAnswer = '生成答案';

  /// 长等待（>6 秒）时的 reassurance 文案，符合 world-class 等待体验
  static const String assistantProcessLongWaitReassurance = '正在深入处理，请稍候…';
  static const String assistantProcessHandoffReassurance =
      '我在切换更合适的处理路径，优先保证结论稳定。';
  static const String assistantProcessRecoveryReassurance =
      '中途有一部分信息需要重试，我已自动恢复并继续收敛。';
  static const String assistantDevReplayTitle = '助理开发态回放';
  static const String assistantDevReplayOpen = '回放';
  static const String assistantDevReplayRun = '运行记录';
  static const String assistantDevReplayQuery = '问题';
  static const String assistantDevReplayAnswer = '回答';
  static const String assistantDevReplayPolicy = '策略决策';
  static const String assistantDevReplayPlan = '查询计划';
  static const String assistantDevReplayRounds = '轮次轨迹';
  static const String assistantDevReplayScore = '评分聚合快照';
  static const String assistantNoReplayData = '暂无回放数据';
  static const String assistantSettingsModel = '选择模型';
  static const String assistantSettingsBackend = '会话引擎';
  static const String assistantSettingsBackendHint =
      '创建新会话时只绑定一个 backend，不做 fallback 或混跑。';
  static const String assistantSettingsRemoteHistoryDisabled = '远端链路不读取本地记录';
  static const String assistantSettingsTraceSession = '跟踪会话';
  static const String assistantSettingsConversationHistory = '对话记录';
  static const String assistantBackendLocal = '本地 phase 引擎';
  static const String assistantBackendRemote = '远端 API 引擎';
  static const String assistantViewHistory = '查看记录';
  static const String assistantWelcomeHeadline = 'Hi，今天从哪儿开始？';
  static const String assistantHistoryAll = '全部记录';
  static const String assistantHistoryAllSubtitle = '共 %s 个独立会话';
  static const String assistantHistoryMessageCount = '%s 条消息';
  static const String assistantHistoryUntitled = '未命名会话';
}
