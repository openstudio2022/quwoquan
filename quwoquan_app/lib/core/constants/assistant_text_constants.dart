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
  static const String assistantPrivacyPermissions = '隐私权限';
  static const String assistantContentAccessPermission = '允许私助使用我的创作内容';
  static const String assistantSupportingCapabilities = '配套能力';
  static const String assistantSkillCenter = '技能中心';
  static const String assistantContentAccessGranted = '已允许';
  static const String assistantContentAccessNotGranted = '未允许';
  static const String assistantConsentLoadFailedTitle = '隐私权限未同步';
  static const String assistantMemorySectionTitle = '偏好与记忆';
  static const String assistantMemoryEmpty = '暂无已保存的显式偏好';
  static const String assistantMemoryUntitled = '未命名偏好';
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
  static const String assistantSkillCategoryLife = '生活';
  static const String assistantSkillCategoryWork = '工作';
  static const String assistantSkillCategoryKnowledge = '知识与资讯';
  static const String assistantSkillCategoryCreation = '创作';
  static const String assistantSkillCategoryCompanion = '陪伴';
  static const String assistantSkillCategoryOther = '其他';
  static const String assistantSkillSubscribed = '已订阅';
  static const String assistantSkillPaused = '已暂停';
  static const String assistantSkillConsentRequired = '需授权';
  static const String assistantSkillSubscriptionUnavailable = '暂不可订阅';
  static const String assistantSkillStatusPendingSync = '状态待同步';
  static const String assistantSkillSubscriptionUnavailableTitle = '暂不可订阅';
  static const String assistantSkillSubscriptionUnavailableMessage =
      '该技能暂未提供可配置订阅入口';
  static const String assistantTaskStatusPending = '待处理';
  static const String assistantTaskStatusInProgress = '进行中';
  static const String assistantTaskStatusCompleted = '已完成';
  static const String assistantTaskStatusCancelled = '已取消';
  static const String assistantTaskUntitled = '未命名任务';
  static const String assistantSyncing = '同步中';
  static const String assistantLoading = '加载中';
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
  static const String assistantCloudConversationSummary = '找私助云端对话';
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
  static const String assistantCardCompare = '对比卡片';
  static const String assistantCardTrend = '趋势卡片';
  static const String assistantCardDiagram = '结构图';
  static const String assistantActionCasual = '更口语化';
  static const String assistantActionDeepThink = '深度思考';
  static const String assistantGenerationStopped = '已停止生成。';
  static const String assistantStopGenerating = '停止生成';
  static const String assistantHistoryTitle = '历史会话';
  static const String assistantHistoryEmpty = '还没有历史会话';
  static const String assistantNewConversation = '新对话';
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
