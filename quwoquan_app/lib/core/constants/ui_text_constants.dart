class UITextConstants {
  // ==================== 导航 ====================
  static const String home = '首页';
  static const String discovery = '发现';
  static const String homeTabFollowing = '关注';
  static const String homeTabFeatured = '精选';
  static const String homeTabCircles = '圈子';
  static const String homeCirclesMy = '我的';
  static const String homeCirclesRecommendTab = '圈子推荐';
  static const String homeCirclesManage = '管理';
  static const String homeCirclesHotTopics = '热议话题';
  static const String homeCirclesMyCircles = '我的圈子';
  static const String homeCirclesSuggested = '推荐加入';
  static const String homeCirclesRecent = '最近活跃';
  static const String homeCirclesUnread = '未读';
  static const String homeCirclesManaged = '我管理的';
  static const String homeCirclesRecentlyJoined = '最近加入';
  static const String homeCirclesViewAll = '查看全部';
  static const String homeCirclesFeedSection = '来自圈子';
  static const String homeCirclesStoryTypeActivity = '活动';
  static const String homeCirclesStoryTypeCreation = '创作';

  /// 发现页 Tab（1:1 对应 DiscoveryFeed.tsx CATEGORIES）
  static const String discoveryTabMoment = '点滴';
  static const String discoveryTabPhoto = '图片';
  static const String discoveryTabVideo = '视频';
  static const String discoveryTabArticle = '笔记';

  /// 双轨道架构主 Rail 标签
  static const String discoveryRailMoment = '点滴';
  static const String discoveryRailWorks = '作品';

  /// 作品频道二级过滤器
  static const String discoveryWorksFilterAll = '全部';
  static const String discoveryWorksFilterVideo = '视频';
  static const String discoveryWorksFilterImage = '图片';
  static const String discoveryWorksFilterArticle = '笔记';

  /// 统一创作容器过滤器（profile / circle）
  static const String creationFilterAll = '全部';
  static const String creationFilterMoment = '点滴';
  static const String creationFilterWork = '作品';
  static const String workFormatFilterAll = '全部';
  static const String workFormatFilterImage = '图片';
  static const String workFormatFilterVideo = '视频';
  static const String workFormatFilterNote = '笔记';

  /// 发现页 V1：帮读/美图/视频
  static const String discoveryTabHelperRead = '帮读';
  static const String discoveryHelperSummaryTitle = '小趣已为你读完';
  static const String discoveryHelperSummarySubtitle = '今日值得看 3 条，已筛选 27 条重复信息';

  /// 帮读一句话综述占位（自上次阅读后…）
  static const String discoveryHelperOneLinerTemplate = '自上次阅读以来，%s';

  /// 帮读分维度展开的维度标题
  static const String discoveryHelperDimensionFriendPublish = '趣友新动态';
  static const String discoveryHelperDimensionNewFollowPublish = '刚加入的趣友';
  static const String discoveryHelperDimensionDormantFriendPublish =
      '久未发·最近有互动';
  static const String discoveryHelperDimensionCircleMoment = '圈子发生了什么';
  static const String discoveryHelperDimensionInteractionWithYou = '谁与你互动';
  static const String discoveryHelperDimensionExplore = '探索推荐';

  /// 时间线分组
  static const String discoveryHelperTimelineToday = '今天';
  static const String discoveryHelperTimelineYesterday = '昨天';
  static const String discoveryHelperTimelineThisWeek = '本周';
  static const String discoveryHelperExpandMoments = '展开点滴';
  static const String discoveryHelperExpandArticles = '查看笔记列表';
  static const String discoveryHelperSectionMoments = '点滴';
  static const String discoveryHelperSectionArticles = '笔记';
  static const String discoveryHelperActionReadOriginal = '看原文';
  static const String discoveryHelperActionLater = '稍后处理';
  static const String discoveryHelperActionPreference = '更像这个';
  static const String assistantCommandRead = '帮我读';
  static const String assistantCommandRemember = '帮我记';
  static const String assistantCommandHandle = '帮我办';
  static const String assistantCommandShare = '帮我发';
  static const String assistantCommandFind = '帮我找';
  static const String assistantCommandPlan = '帮我排';
  static const String assistantActionNoRemind = '不再提醒';
  static const String assistantFeedbackSavedToMemory = '已加入记忆';
  static const String assistantFeedbackTaskDraftCreated = '已生成待办草案';
  static const String assistantFeedbackShareDraftCreated = '已生成分享草稿';
  static const String assistantFeedbackPlanCreated = '已生成安排建议';
  static const String assistantFeedbackRemindLater = '已设为稍后提醒';
  static const String assistantFeedbackReduceProactive = '已减少主动提醒';
  static const String assistantFeedbackOptimizeRecommendation = '收到，将优化推荐';
  static const String assistantFeedbackAddedToLater = '已加入稍后处理';
  static const String assistantTabSchedule = '日程';
  static const String assistantTabSkills = '技能';
  static const String assistantEntryFind = '找小趣';
  static const String assistantEntryAskLegacy = '问小趣';

  /// 半弹窗：进入完整对话按钮
  static const String assistantHalfSheetEnterFullChat = '进入完整对话';

  /// 半弹窗：输入框占位
  static const String assistantHalfSheetInputPlaceholder = '说点什么或选上面试试';

  /// 半弹窗：「当前适合干啥」区块标题
  static const String assistantHalfSheetSuggestionTitle = '当前适合干啥';
  static const String search = '搜索';
  static const String create = '创建';
  static const String chat = '聊天';
  static const String profile = '个人资料';
  static const String like = '点赞';
  static const String share = '分享';
  static const String follow = '关注';
  static const String comment = '评论';
  static const String sourceFromPrefix = '来自 ';

  // ==================== 欢迎页 ====================
  static const String welcomeTitle = '趣我圈';
  static const String welcomeSubtitle = '以兴趣为半径，画出我们的交集';
  static const String welcomeMainSlogan = '专注你的热爱，其余交给小趣';
  static const String welcomeButtonLabel = '开启发现之旅';

  /// 欢迎页底部署名（中文表达，居中）
  static const String welcomeFooterCredit = '小趣私人助手 · 与你相伴';

  // ==================== 通用 ====================
  static const String commentPlaceholder = '添加评论...';
  static const String commentTooLong = '评论过长';
  static const String commentEmpty = '评论不能为空';
  static const String commentClosed = '评论已关闭';
  static const String needLogin = '需要登录';
  static const String loading = '加载中...';
  static const String retry = '重试';
  static const String cancel = '取消';
  static const String confirm = '确认';
  static const String user = '用户';
  static const String following = '已关注';
  static const String followBack = '回关';
  static const String unknownUser = '未知用户';
  static const String copyLink = '复制链接';

  /// 分享目标：微信
  static const String shareTargetWechat = '微信';

  /// 分享目标：朋友圈
  static const String shareTargetMoments = '朋友圈';
  static const String loadFailed = '加载失败';
  static const String report = '举报';
  static const String notInterested = '不感兴趣';
  static const String shareTo = '分享到';
  static const String shareActionSavePoster = '保存海报';
  static const String shareActionSystemShare = '系统分享';
  static const String sharePrivateBlocked = '仅自己可见内容不可对外分享';
  static const String shareCircleVisibilityNotice = '圈内可见内容将生成受控链接';
  static const String shareLegacyFallbackNotice = '当前已回退到通用分享面板';
  static const String shareLinkCopied = '分享链接已复制';
  static const String sharePosterSaved = '海报已保存到本地文件';
  static const String shareCancelled = '已取消分享';
  static const String shareFailed = '分享失败，请稍后重试';
  static const String savePhoto = '保存图片';
  static const String saveVideo = '保存视频';
  static const String savePost = '收藏';
  static const String savedLabel = '已收藏';
  static const String unknown = '未知';
  static const String commentSent = '评论已发送';
  static const String replySent = '回复已发送';
  static const String pullToRefreshHint = '下拉刷新试试';
  static const String goToUserProfile = '前往用户主页';
  static const String loadMoreComments = '加载更多评论';
  static const String noComment = '暂无评论';
  static const String replyAction = '回复';
  static const String commentAuthorBadge = '作者';
  static const String profileCommentsTabSent = '我发出的';
  static const String profileCommentsTabReceived = '我收到的';

  // ==================== 我的主页 ====================
  static const String editProfile = '编辑资料';
  static const String settings = '设置';
  static const String bookmarks = '收藏';

  // ==================== 圈子 ====================
  static const String createCircle = '创建圈子';
  static const String editCircle = '编辑圈子';
  static const String manageCenter = '管理中心';
  static const String followCircle = '关注圈子';
  static const String followedCircle = '已关注圈子';
  static const String joinCircle = '加入圈子';
  static const String joinedCircle = '已加入圈子';
  static const String joinPending = '加入审批中';
  static const String circleMembers = '成员';
  static const String circleGroups = '群聊';
  static const String circleFans = '粉丝';
  static const String circleLikes = '获赞';
  static const String searchMembersHint = '搜索成员...';
  static const String searchGroupsHint = '搜索群聊...';
  static const String searchFansHint = '搜索粉丝...';
  static const String searchLikesHint = '搜索获赞记录...';
  static const String noData = '暂无数据';
  static const String noLikesRecord = '暂无获赞记录';
  static const String circleWorksTab = '创作';
  static const String circleInteractionTab = '互动';
  static const String circleLifestyleTab = '生活';
  static const String circleSubAll = '全部';
  static const String circleSubPhoto = '图片';
  static const String circleSubVideo = '视频';
  static const String circleSubArticle = '笔记';
  static const String circleSubLikes = '赞';
  static const String circleSubComments = '评论';
  static const String circleSubMicro = '点滴';
  static const String circleSortLatest = '最新';
  static const String circleSortHot = '最热';
  static const String circleSortFeatured = '精选';
  static const String circleNoCreations = '暂无创作内容';
  static const String circleNoChatEnabled = '群聊尚未开启';
  static const String circleUploadFile = '上传文件';
  static const String circleComments = '评论';
  static const String circleOfficialBadge = '官方认证 | 优质社区';
  static const String circlesRecommendedTitle = '推荐圈子';
  static const String circlesFollowingEmpty = '关注暂无内容';
  static const String discoveryEndHint = '已经到底啦';
  static const String circleManageChannels = '频道管理';
  static const String circleMyChannels = '我的频道';
  static const String circleAllChannels = '全部频道';
  static const String circleDragToSort = '拖动排序';
  static const String circleTapToAdd = '点击添加频道';
  static const String done = '完成';
  static const String seeMore = '查看更多';
  static const String fullText = '全文';
  static const String collapse = '收起';
  static const String ellipsis = '...';
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

  // ==================== 趣聊 ====================
  static const String atMe = '@我';
  static const String unread = '未读';
  static const String secretMessage = '密信';
  static const String friends = '好友';
  static const String groupChat = '群聊';
  static const String secretLockedTitle = '密信已锁定';
  static const String secretUnlockButton = '解锁密信';
  static const String secretPasswordHint = '请输入密信密码';
  static const String secretUnlockedBanner = '密信已解锁';
  static const String secretLockButton = '锁定';
  static const String noSecretConversations = '暂无密信对话';
  static const String noConversations = '暂无对话';
  static const String startChatHint = '开始与圈友聊天吧！';
  static const String noMentionsMessages = '暂无@我的消息';
  static const String noMentionsHint = '有人提到你时，会在这里提醒你';
  static const String noUnreadMessages = '暂无未读消息';
  static const String noUnreadHint = '新消息来了，会第一时间出现在这里';
  static const String untitledConversation = '未命名对话';
  static const String chatPreviewImage = '[图片]';
  static const String chatPreviewVideo = '[视频]';
  static const String chatPreviewVoice = '[语音]';
  static const String chatPreviewCall = '[通话]';
  static const String chatPreviewCard = '[卡片]';
  static const String chatPreviewRecalled = '[消息已撤回]';
  static const String contactsTabAll = '全部';
  static const String contactsTabCircles = '圈子';

  /// 同好一级 Tab 下的二级：同好（原好友）
  static const String contactsTabSameInterest = '同好';

  /// 同好一级 Tab 下的二级：趣群（原群聊）
  static const String contactsTabFunGroup = '趣群';
  static const String contactsTabFriends = '好友';
  static const String contactsTabGroups = '群聊';
  static const String starredFriends = '星标朋友';
  static const String encryptedMessagePreview = '[加密消息] 查看需要验证身份';
  static const String copiedToClipboard = '已复制';

  /// 消息长按菜单（1:1 对应 MessageActionMenu.tsx）
  static const String messageActionForward = '转发';
  static const String messageActionSelect = '多选';
  static const String messageActionCopy = '复制';
  static const String messageActionRecall = '撤回';
  static const String messageActionDelete = '删除';
  static const String inputHint = '输入消息...';
  static const String send = '发送';
  static const String emoji = '表情';

  /// 实时通话
  static const String call = '语音通话';
  static const String videoCall = '视频通话';
  static const String callVoice = '语音通话';
  static const String callVideo = '视频通话';
  static const String callGroupVoice = '语音通话';
  static const String callGroupVideo = '视频通话';
  static const String callEnded = '通话结束';
  static const String callConnecting = '连接中...';
  static const String callRinging = '等待接听...';
  static const String callReconnecting = '正在重连...';
  static const String callNetworkWeak = '网络不佳';
  static const String callNetworkDisconnected = '连接中断，正在重连...';
  static const String callRecording = '录制中';
  static const String callScreenSharing = '屏幕共享中';
  static const String callReject = '拒绝';
  static const String callDecline = '拒接';
  static const String callAccept = '接听';
  static const String callHangup = '挂断';
  static const String callMute = '静音';
  static const String callUnmute = '取消静音';
  static const String callFlipCamera = '翻转摄像头';
  static const String callSpeaker = '扬声器';
  static const String callInvite = '邀请';
  static const String callIncoming = '来电';
  static const String callIncomingVoice = '语音来电';
  static const String callIncomingVideo = '视频来电';
  static const String callSourceCurrentConversation = '当前会话';
  static const String callSourceSameInterest = '同好';
  static const String callSourceOtherGroups = '其他群';
  static const String callParticipantList = '成员列表';
  static const String callRestoreDefaultSelection = '恢复默认';
  static const String callClearSelection = '全不选';
  static const String callShareJoinLink = '分享入会链接';
  static const String callDebugSimulateIncomingVoice = '模拟语音来电';
  static const String callDebugSimulateIncomingVideo = '模拟视频来电';
  static const String callDebugAutoConnectInFiveSeconds = '5 秒自动接通';
  static const String callDebugManualAnswer = '手动接通';
  static const String callDebugTimeout = '超时';
  static const String callDebugOnlyHint = '仅开发态显示';
  static const String callOutgoingCalling = '正在呼叫...';

  /// 统一 emoji 选择器「最近」Tab
  static const String emojiRecent = '最近';

  /// Mac 风格 emoji 面板分类（与键盘同高、Tab 切换）
  static const String emojiCategorySmileys = '表情';
  static const String emojiCategoryAnimals = '动物';
  static const String emojiCategoryFood = '食物';
  static const String emojiCategoryDrink = '饮料';
  static const String emojiCategoryActivity = '活动';
  static const String emojiCategoryTravel = '出行';
  static const String emojiCategoryObjects = '物体';
  // 聊天设置页（1:1 图二）
  static const String chatInfoTitle = '聊天信息';
  static const String viewAllMembers = '查看全部成员';
  static const String groupName = '群聊名称';
  static const String qrCode = '二维码';
  static const String groupAnnouncement = '群公告';
  static const String muteNotifications = '消息免打扰';
  static const String pinChat = '置顶聊天';
  static const String privacyShield = '隐私屏障(禁截屏、禁转发)';
  static const String setChatBackground = '设置当前聊天背景';
  static const String clearChatHistory = '清空聊天记录';
  static const String exitGroupChat = '退出群聊';
  static const String dissolveGroupChat = '解散该群聊';
  static const String addMember = '添加成员';
  static const String groupManagement = '群管理';
  static const String groupNameAdminOnly = '群组已设定为只有群主或管理员才能修改群名';
  static const String qrCodeJoin = '二维码进群';
  static const String joinRequiresApproval = '进群需要群主/群管理员确认';
  static const String nameEditableByAdminOnly = '仅群主/群管理员可修改群聊名称';
  static const String transferOwnership = '群主管理权转让';
  static const String groupAdmins = '群管理员';
  static const String selectNewOwner = '选择新群主';
  static const String selectGroupMembers = '选择群成员';
  static const String transferOwnershipConfirmPrefix = '确定选择 ';
  static const String transferOwnershipConfirmSuffix = ' 为新群主，你将自动放弃群主身份。';
  static const String maxAdminsReached = '最多选择 3 位管理员';
  static const String editGroupName = '修改群聊名称';
  static const String groupNameHint = '请输入群聊名称';
  static const String groupNameUpdated = '群聊名称已更新';
  static const String groupAdminDescription = '管理员可协助群主管理群聊，拥有发布群公告、移除群成员等能力。';
  static const String groupAdminOnlyOwner = '只有群主具备设置管理员、解散群聊的能力。';
  static const String groupAdminMaxCount = '最多可设置3个管理员。';
  static const String admin = '管理员';
  static const String owner = '群主';

  /// 发起群聊页（图一）
  static const String startGroupChat = '发起群聊';
  static const String addContact = '加联系';
  static const String globalActionSheetTitle = '发起';
  static const String globalSearchTitle = '搜索';
  static const String createActionCamera = '从摄像';
  static const String createActionTextShort = '写点字';
  static const String createActionGroupChatHint = '拉人进群，立即开聊';
  static const String createActionContactHint = '找到新联系，发起对话';
  static const String createNewGroupChat = '创建新群聊';
  static const String selectFriendsFromGroupChat = '选择群聊中的同好';
  static const String selectFriendsFromCircle = '选择圈子中的同好';
  static const String relatedSameInterest = '相关同好';
  static const String selectGroupChat = '选择群聊';
  static const String searchGroupChatHint = '搜索群聊';
  static const String selectCircle = '选择圈子';
  static const String searchCircleHint = '搜索圈子';
  static const String selectAll = '全选';
  static const String selectAction = '选择';
  static const String friendsCount = '个朋友';

  /// 聊天信息页：超过首屏成员时展开入口
  static const String moreMembers = '更多群成员';

  /// 聊天信息页：收起成员列表
  static const String collapseMembers = '收起来';

  /// 聊天底部「更多」面板（图二：两行六项）
  static const String chatMorePhoto = '照片';
  static const String chatMoreShoot = '拍摄';
  static const String chatMoreFile = '文件';
  static const String chatMoreBurnAfterRead = '阅后即焚';
  static const String chatMoreLocation = '位置';
  static const String chatMoreAudioVideo = '音视频';
  static const String chatMoreRedPacket = '红包';
  static const String chatAttachmentTypeConflict = '图片与文件不能同时添加';
  static const String chatAttachmentMaxCount = '最多添加 %s 个';
  static const String chatVoiceHoldToTalk = '按住说话';
  static const String chatVoiceHoldTip = '按住开始录音';
  static const String chatVoiceReleaseToSend = '松开发送';
  static const String chatVoicePermissionDenied = '未获得录音权限';
  static const String timeFormatAM = '上午';
  static const String timeFormatPM = '下午';
  static const String assistantHome = '助理主页';

  /// 助手 run 失败时展示的通用提示（会话/存储/模型等任一步骤异常均会触发）
  static const String assistantUnavailable = '助手暂时不可用，请稍后重试。';
  static const String assistantModelUnavailable =
      '当前未配置可用模型，请先在模型配置中接入远程模型或桥接服务。';
  static const String assistantRunningHint = '小趣正在规划与执行中...';

  /// v3 用户视角阶段：先帮用户理清问题
  static const String assistantPhaseUnderstanding = '理解问题中';

  /// v3 用户视角阶段：替用户核对资料（工具执行，由元数据覆盖）
  static const String assistantPhaseSearching = '检索处理中';

  /// v3 用户视角阶段：替用户整理判断
  static const String assistantPhaseAnalyzing = '检索处理中';

  /// v3 用户视角阶段：替用户组织最终回答
  static const String assistantPhaseAnswering = '整理答案中';

  /// v3 用户视角阶段：确认当前信息是否已经够答
  static const String assistantPhaseAssessing = '我在确认现在的信息够不够回答';

  /// v3 用户视角阶段：完成
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
  static const String assistantReferenceOpenFailed = '链接打开失败，已复制到剪贴板';
  static const String assistantReferenceHostBlocked = '该链接域名未通过安全白名单，已复制到剪贴板';
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
  static const String assistantProcessReferenceCountTemplate = '接纳 %s 篇资料';
  static const String assistantProcessStepProgressTemplate = '已完成 %s/%s 步';
  static const String assistantProcessCompletedSummary = '已完成深度思考';
  static const String assistantProcessCompletedSummaryReferencesTemplate =
      '已完成深度思考，处理 %s 篇文档';
  static const String assistantProcessCompletedSummaryElapsedTemplate =
      '已完成深度思考，耗时 %s 秒';
  static const String assistantProcessCompletedSummaryFullTemplate =
      '已完成深度思考，处理 %s 篇文档，耗时 %s 秒';
  static const String assistantProcessStageUnderstand = '理解问题中';
  static const String assistantProcessStageSearch = '检索处理中';
  static const String assistantProcessStageAnalyze = '检索处理中';
  static const String assistantProcessStageAnswer = '整理答案中';

  /// 长等待（>6 秒）时的 reassurance 文案，符合 world-class 等待体验
  static const String assistantProcessLongWaitReassurance = '正在深入处理，请稍候…';
  static const String assistantProcessHandoffReassurance =
      '我在切换更合适的处理路径，优先保证结论稳定。';
  static const String assistantProcessRecoveryReassurance =
      '中途有一部分信息需要重试，我已自动恢复并继续收敛。';
  static const String assistantBookmarked = '已收藏';
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
  static const String assistantSettingsRemoteHistoryDisabled = '远端链路不读取本地历史';
  static const String assistantSettingsTraceSession = '跟踪会话';
  static const String assistantSettingsConversationHistory = '对话历史';
  static const String assistantBackendLocal = '本地 phase 引擎';
  static const String assistantBackendRemote = '远端 API 引擎';
  static const String assistantViewHistory = '查看历史';
  static const String assistantWelcomeHeadline = 'Hi，今天从哪儿开始？';
  static const String assistantHistoryAll = '全部历史';
  static const String assistantHistoryAllSubtitle = '共 %s 个独立会话';
  static const String assistantHistoryMessageCount = '%s 条消息';
  static const String assistantHistoryUntitled = '未命名会话';
  static const String assistantHistoryEmpty = '暂无对话历史';

  /// 身份/分身（1:1 对应 PersonaSwitcher.tsx）
  static const String personaManage = '管理分身';
  static const String personaPrimary = '主账号';

  /// 我的主页统计与子页（关注数用 follow，此处为统计栏标题）
  static const String myResonance = '我的交集';
  static const String profileEditLabel = '资料编辑';
  static const String profilePersonasLabel = '分身管理';
  static const String profileDirectMessage = '消息';
  static const String profileTabCreations = '创作';
  static const String profileTabCircles = '圈子';
  static const String profileTabInteraction = '互动';
  static const String creationSubAll = '全部';
  static const String creationSubMicro = '点滴';
  static const String creationSubImage = '图片';
  static const String creationSubVideo = '视频';
  static const String creationSubArticle = '文章';
  static const String interactionSubLikes = '赞';
  static const String interactionSubComments = '评论';
  static const String interactionSubShares = '转发';
  static const String profileGreet = '打招呼';
  static const String profileSameInterest = '同好';
  static const String profileCloseFriend = '密友';
  static const String profileAddSameInterest = '加同好';
  static const String profileSubAccountManagement = '子账号管理';
  static const String profileSubAccountDeleteTitle = '删除子账号';
  static const String profileSubAccountDeleteConfirmTemplate =
      '确定要删除「%s」吗？此操作不可撤销。';
  static const String profileSubAccountCreateTitle = '创建子账号';
  static const String profileSubAccountNamePlaceholder = '账号名称（如：职业号、匿名号）';
  static const String profileSubAccountOpen = '公开';
  static const String profileSubAccountSemi = '半隐';
  static const String profileSubAccountStrict = '严格隔离';
  static const String profileSubAccountSwitchFailed = '切换失败';
  static const String profileSubAccountDeleteFailed = '删除失败';
  static const String profileSubAccountCreateFailed = '创建失败';
  static const String profileSubAccountMaxReachedTemplate = '最多创建 %s 个子账号';
  static const String profileSubAccountEmpty = '暂无子账号';
  static const String profileSubAccountStrictDescription = '严格隔离 · 不出现在通讯录发现';
  static const String profileSubAccountSemiDescription = '半隐私 · 仅好友可发现';
  static const String profileSubAccountOpenDescription = '公开 · 可被通讯录发现';
  static const String operationFailed = '操作失败';

  // ==================== 创作页（1:1 对应 CreatePage.tsx + MomentEditorCard.tsx） ====================
  static const String momentPlaceholder = '这一刻的想法...';
  static const String drafts = '草稿箱';
  static const String createExitConfirmTitle = '保存草稿？';
  static const String createExitConfirmDesc = '如果不保存，当前编辑的内容将会丢失。';
  static const String discard = '放弃';
  static const String saveDraft = '保存草稿';
  static const String createActionGallery = '从相册选';
  static const String createActionGalleryHint = '先挑素材，再决定发成点滴还是作品';
  static const String createActionWrite = '写点什么';
  static const String createActionWriteHint = '快速记录当下，也能随时升级成作品';
  static const String createActionCapture = '拍一下';
  static const String createActionCaptureHint = '直接拍照或录视频，立刻开始创作';
  static const String createIdentityMoment = '点滴';
  static const String createIdentityWork = '作品';
  static const String createSwitchToMoment = '切到点滴';
  static const String createSwitchToWork = '切到作品';
  static const String createWorkFormatImage = '图片';
  static const String createWorkFormatVideo = '视频';
  static const String createWorkFormatNote = '笔记';
  static const String createSuggestionKeepCurrent = '仍按当前发布';
  static const String createSuggestionSwitch = '去调整';
  static const String createSuggestionToWork = '当前内容更适合作为作品发布';
  static const String createSuggestionToMoment = '这条内容也可以更轻量地作为点滴发布';
  static const String postMoment = '发点滴';
  static const String postPhoto = '发图片';
  static const String postVideo = '发视频';
  static const String postArticle = '写笔记';
  static const String publish = '发表';
  static const String publishAction = '发布';
  static const String locationLabel = '所在位置';
  static const String locationHidden = '不显示位置';
  static const String remindWhoLabel = '提醒谁看';
  static const String whoCanSeeLabel = '谁可以看';
  static const String visibilityPublic = '公开';
  static const String visibilityPrivate = '私密';
  static const String isPublicLabel = '是否公开';

  /// 创作页圈子入口/空态；国际化请用 l10n.selectPublishCirclesLabel / l10n.noCirclesAvailable
  static const String selectPublishCirclesLabel = '发布的圈子';
  static const String noCirclesAvailable = '加入圈子，发现同好';
  static const String locationSearchHint = '搜索地点';
  static const String locationNearbyTitle = '附近位置';
  static const String locationSearchingNearby = '正在搜索附近位置';

  /// 与 integration/location/errors.location_unavailable 保持一致
  static const String locationLoadFailed = '暂时无法获取当前位置，请稍后重试';
  static const String locationSearchTitle = '搜索位置';
  static const String locationSearchEmpty = '未找到相关位置';
  static const String circleSelectTitle = '选择圈子';

  /// 图片选择/编辑（微趣、美图、文章共用）
  static const String addCover = '添加封面';
  static const String articleCoverOptionNone = '无图封面';
  static const String articleCoverOptionNoneDesc = '不使用封面图';
  static const String articleCoverOptionOne = '一图封面';
  static const String articleCoverOptionTwo = '二图封面';
  static const String articleCoverOptionThree = '三图封面';
  static const String addImage = '添加图片';
  static const String selectFromGallery = '从相册选择';
  static const String editImage = '编辑图片';
  static const String imageEditDone = '完成';

  /// 图片编辑器（图四 Snapseed 式）
  static const String imageEditTools = '工具';
  static const String imageEditStyles = '样式';
  static const String imageEditOriginal = '原图';
  static const String imageEditVivid = '鲜艳';
  static const String imageEditWarm = '暖色';
  static const String imageEditCool = '冷色';
  static const String imageEditMono = '黑白';
  static const String imageEditPortrait = '人像';
  static const String imageEditLandscape = '风景';
  static const String imageEditStillLife = '静物';
  static const String imageEditVintage = '复古';
  static const String imageEditDrama = '戏剧';
  static const String imageEditFaded = '褪色';
  static const String imageEditNostalgic = '怀旧';
  static const String imageEditCompare = '对比';

  /// 图片编辑器底栏工具（重建后三段式布局）
  static const String imageEditorRotate = '旋转';
  static const String imageEditorCrop = '裁剪';
  static const String imageEditorFilter = '滤镜';
  static const String imageEditorBeauty = '美颜';
  static const String imageEditorProTools = '专业工具';
  static const String imageEditorFrame = '相框';
  static const String imageEditorText = '文字';
  static const String imageEditorMosaic = '马赛克';

  /// 图片编辑器历史与操作面板
  static const String imageEditorHistory = '历史';
  static const String imageEditorRemoveStep = '删除步骤';
  static const String imageEditorRedoStep = '重做';

  /// 裁剪比例
  static const String imageEditorCropFree = '自由';
  static const String imageEditorCropOriginal = '原始';
  static const String imageEditorCropRatio1x1 = '1:1';
  static const String imageEditorCropRatio2x3 = '2:3';
  static const String imageEditorCropRatio3x2 = '3:2';
  static const String imageEditorCropRatio3x4 = '3:4';
  static const String imageEditorCropRatio4x3 = '4:3';
  static const String imageEditorCropRatio9x16 = '9:16';
  static const String imageEditorCropRatio16x9 = '16:9';
  static const String imageEditorCropReset = '重置';
  static const String imageEditorRotateRestore = '还原';

  /// 滤镜分类（面板顶部分类）
  static const String imageEditorFilterRecommended = '推荐';
  static const String imageEditorFilterFrequent = '常用';
  static const String imageEditorFilterRemove = '去滤镜';
  static const String imageEditorFilterQuality = '画质';
  static const String imageEditorFilterSpring = '春天';
  static const String imageEditorFilterVivid = '鲜明';
  static const String imageEditorFilterHighSat = '高饱和';
  static const String imageEditorFilterDehaze = '去灰';

  /// 专业修图子工具（曲线/白平衡等参数标签）
  static const String imageEditorProBrightness = '亮度';
  static const String imageEditorProLightSense = '光感';
  static const String imageEditorProContrast = '对比度';
  static const String imageEditorProColorTemp = '色温';
  static const String imageEditorProExposure = '曝光';
  static const String imageEditorProSaturation = '饱和度';
  static const String imageEditorProNaturalSaturation = '自然饱和度';
  static const String imageEditorProTexture = '纹理';
  static const String imageEditorProHighlight = '高光';
  static const String imageEditorProShadow = '阴影';
  static const String imageEditorProAmbiance = '氛围';
  static const String imageEditorProWarmth = '暖色调';
  static const String imageEditorProTone = '色调';
  static const String imageEditorProGrain = '颗粒';
  static const String imageEditorProFade = '褪色';
  static const String imageEditorProDenoise = '降噪';
  static const String imageEditorProSharpen = '锐化';
  static const String imageEditorProUnsharpen = '去锐化';
  static const String imageEditorPanelPlaceholder = '操作模版或内容';
  static const String imageEditorBeautyNatural = '自然';
  static const String imageEditorBeautySoft = '柔和';
  static const String imageEditorBeautyClear = '清透';
  static const String imageEditorTextPlaceholder = '点击输入文字';
  static const String imageEditorTextStyle = '样式';
  static const String imageEditorTextColor = '颜色';
  static const String imageEditorMosaicPixel = '像素';
  static const String imageEditorMosaicBlur = '模糊';
  static const String imageEditorMosaicBrush = '画笔';
  static const String imageEditorMosaicSize = '大小';
  static const String imageEditorFrameSimple = '简洁';
  static const String imageEditorFrameFilm = '胶片';
  static const String imageEditorFrameWhite = '留白';

  /// 专业修图子工具
  static const String imageEditorProCurve = '曲线';
  static const String imageEditorProWhiteBalance = '白平衡';
  static const String imageEditorProLocal = '局部';
  static const String imageEditorProHeal = '修复';
  static const String imageEditorProGlamourGlow = '美丽光晕';
  static const String imageEditorProToneContrast = '色调对比度';
  static const String imageEditorProHsl = 'HSL';
  static const String imageEditorProAdjustImage = '调整图片';
  static const String imageEditorProPerspective = '视角';
  static const String imageEditorProTabOverall = '调整图片';
  static const String imageEditorProTabLocal = '局部';
  // 兼容旧引用
  static const String imageEditorProTabBase = imageEditorProTabOverall;
  static const String imageEditorProTabHsl = 'HSL';
  static const String imageEditorProTabCurve = '曲线';
  static const String imageEditorProTabBwLevels = '黑白色阶';
  static const String imageEditorProPlaceholderHsl = 'HSL 即将支持';
  static const String imageEditorProPlaceholderLocal = '点击添加锚点开始局部调节';
  static const String imageEditorProPlaceholderCurve = '曲线 即将支持';
  static const String imageEditorProPlaceholderBwLevels = '黑白色阶 即将支持';
  static const String imageEditorProHue = '色相';
  static const String imageEditorProLuminance = '明度';
  static const String imageEditorProStructure = '结构';
  static const String imageEditorProWhiteLevel = '白色色阶';
  static const String imageEditorProBlackLevel = '黑色色阶';
  static const String imageEditorProAnchorAdd = '添加局部';
  static const String imageEditorProAnchorShowAll = '显隐局部';
  static const String imageEditorProAnchorRange = '显隐范围';
  static const String imageEditorProAnchorShow = '显示局部';
  static const String imageEditorProAnchorHide = '隐藏局部';
  static const String imageEditorProAnchorRangeShow = '显示范围';
  static const String imageEditorProAnchorRangeHide = '隐藏范围';
  static const String imageEditorProAnchorCopy = '复制';
  static const String imageEditorProAnchorDelete = '删除';
  static const String imageEditorProAnchorLimitReached = '局部锚点最多可添加10个';
  static const String imageEditorProAnchorScaleHint = '可缩放局部位置以调节范围大小';
  static const String imageEditorProAnchorSelectHint = '请先添加或选择局部锚点';
  static const String imageEditorProAnchorLetterBrightness = '亮';
  static const String imageEditorProAnchorLetterContrast = '对';
  static const String imageEditorProAnchorLetterSaturation = '饱';
  static const String imageEditorProAnchorLetterStructure = '结';
  static const String imageEditorProChannelRed = '红';
  static const String imageEditorProChannelOrange = '橙';
  static const String imageEditorProChannelYellow = '黄';
  static const String imageEditorProChannelGreen = '绿';
  static const String imageEditorProChannelCyan = '青';
  static const String imageEditorProChannelBlue = '蓝';
  static const String imageEditorProChannelPurple = '紫';
  static const String imageEditorProChannelMagenta = '洋红';
  static const String imageEditorProColorPicker = '取色器';
  static const String imageEditorProBwLevels = '黑白色阶';

  /// 旋转快捷：向左90°、向右90°、水平翻转、垂直翻转
  static const String imageEditorRotateLeft90 = '向左90°';
  static const String imageEditorRotateRight90 = '向右90°';
  static const String imageEditorFlipHorizontal = '水平翻转';
  static const String imageEditorFlipVertical = '垂直翻转';
  static const String imageSavedSuccess = '保存图片成功';

  /// 发微趣图片区小字提示（原型 1:1）
  static const String momentImageReorderHint = '拖动图片可以调整顺序，点击可以编辑图片';
  static const String momentPublished = '已发表';
  static const String articleCoverLabel = '封面图';
  static const String noDraft = '暂无草稿';
  static const String saveDraftConfirm = '保存草稿？';
  static const String saveDraftHint = '如果不保存，当前编辑的内容将会丢失。';
  static const String discardAndExit = '放弃并退出';
  static const String saveAndExit = '保存并退出';
  static const String draftCount = '草稿箱';
  static const String draftMoment = '点滴草稿';
  static const String draftPhoto = '图片草稿';
  static const String draftVideo = '视频草稿';
  static const String draftArticle = '笔记草稿';
  static const String unlabeled = '[未填写]';

  /// 创作页表单占位（美图/视频/文章）
  static const String createTitleHint = '标题';
  static const String createDescriptionHint = '描述';
  static const String createVideoTitleHint = '视频标题';
  static const String createArticleBodyHint = '正文...';

  /// 美图（UnifiedImagePostCard 1:1）
  static const String photoTitleHint = '添加作品标题...';
  static const String photoBodyHint = '添加作品配文...';
  static const String photoReorderHint = '长按拖动调整顺序';
  static const String photoTapToEdit = '点击编辑';
  static const String photoAddLabel = '添加图片作品';
  static const String photoShowMorePictures = '显示更多图片';
  static const String photoCollapseLabel = '收起';

  /// 视频（VideoEditorCard 1:1）
  static const String videoShortTypeName = '视频';
  static const String videoTitlePlaceholder = '视频标题';
  static const String videoDescPlaceholder = '添加视频描述...';
  static const String videoUploadLabel = '上传视频';
  static const String videoUploadHint = '';
  static const String videoChangeCover = '更换封面';
  static const String videoNoVideo = '暂无视频';
  static const String videoDurationTooLong = '视频时长超过1小时，请重新选择';
  // 媒体选择器（创作）
  static const String mediaPickerAlbumAll = '全部';
  static const String mediaPickerCategoryAll = '全部';
  static const String mediaPickerCategoryVideo = '视频';
  static const String mediaPickerCategoryPhoto = '照片';
  static const String mediaPickerCategoryLive = '实况图';
  static const String mediaPickerCategoryFullscreen = '全屏图';
  static const String mediaPickerCameraEntry = '拍摄';
  static const String mediaPickerOneTapMovie = '一键成片';
  static const String mediaPickerOneTapMovieQueued = '已加入一键成片，请在发视频页继续';
  static const String mediaPickerNextStep = '下一步';
  static const String mediaPickerOverLimit = '已达到可选数量上限';
  static const String mediaPickerPermissionDenied = '请允许相册访问权限后再选择媒体';
  static const String mediaPickerImageOnly = '当前入口仅支持选择图片';
  static const String cameraUnavailable = '相机不可用';
  static const String cameraCaptureFailed = '拍摄失败，请重试';
  static const String cameraPhotoMode = '拍照';
  static const String cameraVideoMode = '录像';

  /// 文章（ArticleEditorCard 1:1）
  static const String articleTitlePlaceholder = '请输入标题';

  static const String shareTemplateMomentTitle = '分享点滴';
  static const String shareTemplateMomentSubtitle = '保留当时的语境与氛围';
  static const String shareTemplateWorkTitle = '分享作品';
  static const String shareTemplateWorkSubtitle = '突出标题、摘要与收藏价值';

  static String contentLabelForKey(String labelKey) {
    switch (labelKey) {
      case 'discovery_rail_moment':
        return discoveryRailMoment;
      case 'discovery_rail_work':
        return discoveryRailWorks;
      case 'creation_filter_all':
        return creationFilterAll;
      case 'creation_filter_moment':
        return creationFilterMoment;
      case 'creation_filter_work':
        return creationFilterWork;
      case 'profile_tab_creations':
        return profileTabCreations;
      case 'profile_tab_circles':
        return profileTabCircles;
      case 'profile_tab_interaction':
        return profileTabInteraction;
      case 'creation_sub_all':
        return creationSubAll;
      case 'creation_sub_micro':
        return creationSubMicro;
      case 'creation_sub_image':
        return creationSubImage;
      case 'creation_sub_video':
        return creationSubVideo;
      case 'creation_sub_article':
        return creationSubArticle;
      case 'interaction_sub_likes':
        return interactionSubLikes;
      case 'interaction_sub_comments':
        return interactionSubComments;
      case 'interaction_sub_shares':
        return interactionSubShares;
      case 'work_format_all':
        return workFormatFilterAll;
      case 'work_format_image':
        return workFormatFilterImage;
      case 'work_format_video':
        return workFormatFilterVideo;
      case 'work_format_note':
        return workFormatFilterNote;
      case 'share_template_moment_title':
        return shareTemplateMomentTitle;
      case 'share_template_moment_subtitle':
        return shareTemplateMomentSubtitle;
      case 'share_template_work_title':
        return shareTemplateWorkTitle;
      case 'share_template_work_subtitle':
        return shareTemplateWorkSubtitle;
      case 'tab_photo':
        return discoveryTabPhoto;
      case 'tab_video':
        return discoveryTabVideo;
      case 'tab_moment':
        return discoveryTabMoment;
      case 'tab_article':
        return discoveryTabArticle;
      default:
        return labelKey;
    }
  }
}
