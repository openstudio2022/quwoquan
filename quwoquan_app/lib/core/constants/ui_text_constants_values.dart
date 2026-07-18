part of 'ui_text_constants.dart';

class UITextConstants {
  static const String home = '首页', discovery = '发现';
  static const String homeTabFollowing = '关注';
  static const String homeTabRecommended = '推荐';
  static const String homeTabFeatured = '视频书', homeTabCircles = '圈子';
  static const String homeTabTravel = '旅行', homeTabPhotography = '摄影';
  static const String homeTabTech = '科技', homeTabCarFriends = '车之家';
  static const String homeTodayIntersection = '发现交集';
  static const String homeMoodFollowing = '关注对象的新动态';
  static const String homeMoodRecommend = '为你挑选新的交集';
  static const String homeMoodCampus = '看看同校与校园动态';
  static const String homeMoodTravel = '看看地点与旅途动态';
  static const String homeMoodPhotography = '看看影像与摄影动态';
  static const String homeMoodTech = '看看科技与同行动态';
  static const String homeMoodCar = '看看汽车与车圈动态';
  static String homeChannelMoodCopy(String moodCopyKey) =>
      _homeChannelMoodCopy(moodCopyKey);

  /// 首页频道标签解析：labelKey（ContentUIConfig.homeChannels 真相源）→ 展示标签。
  /// 无匹配时回退「推荐」，避免空标签。
  static String homeChannelLabel(String labelKey) =>
      _homeChannelLabel(labelKey);
  static const String homeObjectActionFollow = '关注';
  static const String homeObjectActionJoin = '加入';
  static const String homeObjectActionAddContact = '添加联系人';
  static const String homeObjectActionView = '查看';
  // 共同点计数后缀（仅数字格式化，非交集句拼装）。
  static const String homeObjectSharedCountSuffix = ' 个共同点';
  static const String followingSubjectStripTitle = '关注动态';
  static const String followingSubjectEmptyTitle = '还没有关注的人、圈子或地点';
  static const String followingSubjectEmptySubtitle =
      '去推荐、校园、旅行里关注感兴趣的对象，回来这里查看它们的新动态。';
  static String homeObjectActionLabel(String actionType) =>
      _homeObjectActionLabel(actionType);
  static String homeObjectSharedCount(int count) =>
      _homeObjectSharedCount(count);
  static const String globalXiaoquSearchHint = '搜内容、圈子、讨论';
  static const String globalXiaoquSearchAsk = '找小趣';
  static const String webPcBrandName = '趣我圈', webPcPrimaryHome = home;
  static const String webPcPrimaryFeatured = homeTabFeatured;
  static const String webPcPrimaryCreate = '添加';
  static const String webPcPrimaryMessages = '消息';
  static const String webPcPrimaryProfile = '我的';
  static const String webPcCreateTabVideo = discoveryTabVideo;
  static const String webPcCreateTabGallery = '相册';
  static const String webPcCreateTabText = '文字';
  static const String webPcCreateTabDrafts = '草稿';
  static const String webPcMessagesTabMessages = '消息';
  static const String webPcMessagesTabContacts = '联系人';
  static const String webPcMessagesTabGroups = '群聊';
  static const String webPcProfileContextTitle = '我的主页';
  static const String webPcSearchHintHome = '搜索兴趣、圈子、作品、用户';
  static const String webPcSearchHintFeatured = '搜索视频书作品、视频、图文';
  static const String webPcSearchHintCreate = '搜索素材、草稿、发布模板';
  static const String webPcSearchHintMessages = '搜索联系人、群聊、消息';
  static const String webPcSearchHintProfile = '搜索我的内容、浏览、互动';
  static const String webPcWelcomeLogin = '登录';
  static const String webPcWelcomePublish = '发布作品';
  static const String webPcWelcomeHeadline = '以兴趣为半径，画出我们的交集。';
  static const String webPcWelcomeSubtitle =
      '在 Web 上浏览视频书内容、发现兴趣相近的人，也可以下载 App 获得完整创作和消息体验。';
  static const String webPcWelcomeContinue = '继续浏览 Web';
  static const String webPcWelcomeDownload = webInstallBannerDownloadApp;
  static const String webPcWelcomeScrollHint = '滚动鼠标也可以进入首页，工具栏会自动吸顶。';
  static const String webPcWelcomeDownloadPanelTitle = '扫码或选择安装包';
  static const String webPcWelcomeDownloadPanelBody =
      'iOS、Android 与鸿蒙入口都在安装页中。';
  static const String webPcMessagesRailTitle = '消息中心';
  static const String webPcMessagesRailBody = '在这里查看会话、联系人与群聊，点击任意会话进入对话详情。';
  static const String webPcProfileRailTitle = '我的主页';
  static const String webPcProfileRailBody =
      '在 Web 端浏览个人主页、作品与互动数据，保持与移动端一致的展示。';
  static const String webPcHomeRailTitle = homeTodayIntersection;
  static const String webPcHomeRailBody = '关注同校、旅行、摄影与科技等兴趣讨论，新的交集会在这里持续浮现。';
  static const String webPcHomeFeedTitle = '首页推荐';
  static const String webPcFeaturedRailTitle = '视频书发现';
  static const String webPcFeaturedRailBody =
      '以多列瀑布墙展示图片、视频与文章封面，点击任意内容进入沉浸浏览。';
  static const String webPcFeaturedFeedTitle = '视频书内容';
  static const String worksVideoBookLoadingTitle = '正在加载更多视频书内容';
  static const String worksVideoBookLoadingSubtitle = '继续停留即可自动预取新一批内容';
  static const String webPcCreateRailTitle = '创作';
  static const String webPcCreateRailBody = '从照片、视频或文字开始，Web 端保持与移动端一致的创作入口。';
  static const String webPcCreateWorkspaceTitle = '添加';
  static const String webPcCreateWorkspaceSubtitle = '选择一种方式开始创作。';
  static const String webPcCreateContentGroupTitle = '创作方式';
  static const String webPcCreateSocialGroupTitle = '社交关系';
  static const String webPcCreateCameraTitle = '发布视频';
  static const String webPcCreateCameraSubtitle = '从相册选视频或拍视频';
  static const String webPcCreateVideoTitle = webPcCreateCameraTitle;
  static const String webPcCreateVideoSubtitle = webPcCreateCameraSubtitle;
  static const String webPcCreateGalleryTitle = '发布照片';
  static const String webPcCreateGallerySubtitle = '从相册选照片或拍照';
  static const String webPcCreateTextTitle = '写文字';
  static const String webPcCreateTextSubtitle = '记录想法，也可以继续打磨成长文。';
  static const String webPcCreateDraftsTitle = '继续草稿';
  static const String webPcCreateDraftsSubtitle = '打开移动端同源草稿入口，继续未完成内容。';
  static const String webPcCreateGroupChatTitle = '发起群聊';
  static const String webPcCreateGroupChatSubtitle = '邀请联系人加入群聊，开始多人会话。';
  static const String webPcCreateAddContactTitle = '添加联系人';
  static const String webPcCreateAddContactSubtitle = '通过账号或二维码添加联系人。';
  static const String webPcCreateCircleTitle = '创建圈子';
  static const String webPcCreateCircleSubtitle = '创建兴趣圈子并邀请成员加入。';
  static const String webPcFeedEmpty = '暂无内容';
  static String webPcPrimaryLabel(String routeName) =>
      _webPcPrimaryLabel(routeName);
  static const String homeCirclesMy = '我的';
  static const String homeCirclesRecommendTab = '圈子推荐';
  static const String homeCirclesManage = '管理';
  static const String circleScenarioRecommended = '推荐';
  static const String circleScenarioMine = '我的';
  static const String circleScenarioCampus = '校园';
  static const String circleScenarioTravel = '旅行';
  static const String circleScenarioPhotography = '摄影';
  static const String circleScenarioTech = '科技';
  static const String circleScenarioTravelPhotography = '旅行摄影';
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

  static const String discoveryTabMoment = '点滴';
  static const String discoveryTabPhoto = '图片';
  static const String discoveryTabVideo = '视频';
  static const String discoveryTabArticle = '笔记';

  static const String discoveryRailMoment = '点滴';
  static const String discoveryRailWorks = '作品';

  static const String discoveryWorksFilterAll = '全部';
  static const String discoveryWorksFilterVideo = '视频';
  static const String discoveryWorksFilterImage = '图片';
  static const String discoveryWorksFilterArticle = '笔记';

  static const String creationFilterAll = '全部';
  static const String creationFilterMoment = '点滴';
  static const String creationFilterWork = '作品';
  static const String workFormatFilterAll = '全部作品';
  static const String workFormatFilterImage = '图片';
  static const String workFormatFilterVideo = '视频';
  static const String workFormatFilterArticle = '文章';
  static const String articlePaperThemeSystem = '系统适配';
  static const String articlePaperThemeDarkPaper = '深色纸';
  static const String articlePaperThemeCoolGray = '冷灰纸';
  static const String articlePaperThemeWarmBlack = '暖黑纸';
  static const String articlePaperThemeInkGreen = '墨绿纸';
  static const String articlePaperThemeDeepBrown = '深棕纸';

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
  static const String assistantEntryFindPersonal = '找私助';
  static const String assistantEntryAsk = '问小趣';
  static const String assistantEntryXiaoqu = '小趣';

  /// 半弹窗：进入完整对话按钮
  static const String assistantHalfSheetEnterFullChat = '进入完整对话';

  /// 半弹窗：输入框占位
  static const String assistantHalfSheetInputPlaceholder = '说点什么或选上面试试';

  /// 半弹窗：「当前适合干啥」区块标题
  static const String assistantHalfSheetSuggestionTitle = '当前适合干啥';
  static const String search = '搜索';
  static const String create = '创建', chat = '聊天';
  static const String profile = '个人资料';
  static const String edgeBackExitPrompt = '再滑动一次退出应用';
  static const String login = '登录', bottomNavGuestProfile = '未登录';
  static const String loginOneTap = '一键登录';
  static const String loginOneTapPrimary = '本机号码一键登录';
  static const String loginContinue = '继续登录';
  static const String loginSubmitting = '正在登录...';
  static const String loginOtherMethodFallback = '稍后接入其他方式';
  static const String loginCarrierUnsupported = '当前环境暂不支持本机号码一键登录';
  static const String loginCarrierUnavailable = '本机号码一键登录暂不可用';
  static const String loginMethodComingSoonToast = '该登录方式即将开放';
  static const String loginHelpComingSoon = '登录帮助即将开放';
  static const String loginPhoneOtpComingSoon = '手机号验证码登录将在下一版高保接入';
  static const String loginWechatComingSoon = '微信登录将在单独高保后接入';
  static const String loginQqComingSoon = 'QQ 登录将在单独高保后接入';
  static const String loginAlipayComingSoon = '支付宝登录将在单独高保后接入';
  static const String loginDefaultTitle = '登录后继续同步你的兴趣与交集';
  static const String loginDefaultSubtitle = '随时查看互动、消息和个性化推荐';
  static const String loginReturningHeroTitle = '登录后继续同步你的兴趣与交集';
  static const String loginReturningHeroSubtitle = '随时查看互动、消息和个性化推荐';
  static const String loginCarrierHeroTitle = '登录后继续同步你的兴趣与交集';
  static const String loginCarrierHeroSubtitle = '随时查看互动、消息和个性化推荐';
  static const String loginDismissSemanticLabel = '关闭登录页';
  static const String loginBackSemanticLabel = '返回上一页';
  static const String loginHelpSemanticLabel = '帮助';
  static const String loginBrandName = '趣我圈';
  static const String loginBrandIconSemanticLabel = '趣我圈应用图标';
  static const String loginMethodPhoneSemanticLabel = '使用其他手机号登录';
  static const String loginMethodWechatSemanticLabel = '使用微信登录';
  static const String loginMethodQqSemanticLabel = '使用 QQ 登录';
  static const String loginMethodAlipaySemanticLabel = '使用支付宝登录';
  static const String loginUseWechat = '使用微信登录';
  static const String loginUseQq = '使用 QQ 登录';
  static const String loginUseAlipay = '使用支付宝登录';
  static const String loginReturningDefaultName = '欢迎回来';
  static const String loginReturningDefaultAccount = '上次使用的账号';

  /// 快速登录凭证过期/不可用时，returning 态主按钮与引导文案（中性，不报错）。
  static const String loginReturningSmsPrimary = '短信验证码登录';
  static const String loginSessionExpiredHint = '登录信息已过期，请用短信验证码重新登录';
  static const String loginReturningSmsSubtitle = '为安全起见，请用短信验证码登录';
  static const String loginQuickLoginUnavailableHint = '为安全起见，请用短信验证码登录';
  static const String loginCarrierDefaultPhone = '本机号码';
  static const String loginCarrierCreateHint = '将创建趣我圈账号，登录后可完善头像和昵称';
  static const String loginResolvingHint = '正在确认可用登录方式';
  static const String loginAccountAvatarSemanticLabel = '账号头像';
  static const String loginMethodPhone = '其他手机号';
  static const String loginPhoneNumberPlaceholder = '请输入手机号';
  static const String loginOtpPlaceholder = '请输入验证码';
  static const String loginSendOtp = '获取验证码';
  static const String loginSendOtpSubmitting = '发送中...';
  static const String loginPhoneSubmit = '验证并登录';
  static const String loginPhoneChange = '更换手机号';
  static const String loginPhoneInvalid = '请输入正确的手机号';
  static const String loginOtpSentTo = '验证码已发送至 %s';
  static const String loginOtpResend = '重新获取验证码';
  static const String loginOtpResendCountdown = '重新获取(%ds)';
  static const String loginOtpMismatch = '验证码错误，请重新输入';
  static const String loginOtpExpired = '验证码已过期，请重新获取';
  static const String loginOtpRateLimited = '操作过于频繁，请稍后重试';
  static const String loginOtpSendFailed = '验证码发送失败，请稍后重试';
  static const String loginNetworkUnavailable = '网络连接异常，请检查后重试';
  static const String loginServiceUnavailable = '登录服务暂不可用，请使用其他方式登录';
  static const String loginSocialNotConfigured = '当前测试环境未配置，请改用短信验证码登录';
  static const String loginSocialClientNotInstalled = '未安装对应客户端，请改用短信验证码登录';
  static const String loginSocialProbeTimeout = '登录方式检测超时，请重试或改用短信验证码登录';
  static const String loginSocialSdkUnavailable = loginServiceUnavailable;
  static const String loginPhoneLoginLocked = '多次失败已锁定，请稍后再试或更换其它方式登录';
  static const String loginAccountSuspended = '账号已被限制登录，请按页面提示处理或更换其它方式登录';
  static const String loginAccountDeleted = '账号已注销或进入删除流程，无法直接登录，可更换手机号';
  static const String loginSwitchPhone = '换个手机号登录';
  static const String loginSuccess = '登录成功';
  static const String loginRedirecting = '正在为你跳转...';
  static const String loginLater = '稍后登录';
  static const String loginLaterHint = '稍后也可以在「我的」页面登录，同步作品、足迹和消息。';
  static const String loginContinueAsGuest = loginLater;
  static const String loginTitleFirstRun = '登录后，趣我圈更懂你的热爱';
  static const String loginTitleReturn = '欢迎回来，登录后继续同步';
  static const String loginTitleActionRequired = '登录后继续使用';
  static const String loginTitleManualLoggedOut = '重新登录趣我圈';
  static const String loginSubtitleFirstRun = '作品、足迹、赞过、消息与分身资料会跟随账号保存。';
  static const String loginSubtitleReturn = '你可以直接浏览，登录后继续同步点赞、关注和创作记录。';
  static const String loginSubtitleActionRequired = '该操作需要账号身份，用于保存你的记录和权限。';
  static const String loginSubtitleManualLoggedOut = '你已退出当前账号，可重新登录或稍后继续浏览。';
  static const String loginSubtitleSessionExpired = '为了保护账号安全，请重新登录后继续刚才的操作。';
  static const String loginRememberedMethodTitle = '继续上次登录方式';
  static const String loginRememberedMethodPhoneOtp = '上次使用手机号验证码登录';
  static const String loginRememberedMethodOneTap = '上次使用本机号码一键登录';
  static const String loginRememberedMethodWechat = '上次使用微信登录';
  static const String loginRememberedMethodApple = '上次使用 Apple 登录';
  static const String loginRememberedMethodPasskey = '上次使用 Passkey 登录';
  static const String loginRememberedMethodAnonymous = '上次以游客身份使用';
  static const String loginAgreementPrefix = '已阅读并同意 ';
  static const String loginAgreementAnd = ' 和 ';
  static const String userAgreement = '用户协议';
  static const String privacyPolicy = '隐私政策';
  static const String permissionsStatement = '权限说明';
  static const String thirdPartySdkList = '第三方 SDK 清单';
  static const String loginAgreementRequired = '请先阅读并同意用户协议和隐私政策';
  static const String loginOtherMethods = '其他登录方式';
  static const String loginMethodWechat = '微信', loginMethodApple = 'Apple';
  static const String loginMethodPasskey = 'Passkey';
  static const String loginMethodCredentialManager = '系统凭据';
  static const String loginMethodWeibo = '微博', loginMethodQq = 'QQ';
  static const String loginMethodAlipay = '支付宝';
  static const String loginMethodComingSoon = '即将支持';
  static const String loginMethodUnavailable = '当前设备暂不可用，请改用手机号登录';
  static const String loginPhoneRequired = '请输入手机号';
  static const String loginOtpRequired = '请输入验证码';
  static const String loginOtpSent = '验证码已发送';
  static const String loginOtpQueued = '验证码请求已受理，请留意短信';
  static const String loginOtpPassThroughDebugHint = '当前为非生产联调放通，验证码正确性校验已跳过';
  static const String loginHelp = '遇到问题';
  static const String loginFailed = loginServiceUnavailable;
  // 标题：进入全屏登录页后展示，按动作变化，只表达「需要账号身份」。
  static const String authGateTitleProfile = '登录后查看我的主页';
  static const String authGateTitleCreate = '登录后发布内容';
  static const String authGateTitleOpenChat = '登录后查看消息';
  static const String authGateTitleSendMessage = '登录后发送消息';
  static const String authGateTitleComment = '登录后继续评论';
  static const String authGateTitleLike = '登录后继续点赞';
  static const String authGateTitleFollow = '登录后继续关注';
  static const String authGateTitleGreet = '登录后发送打招呼';
  static const String authGateTitleFollowingFeed = '登录后查看关注';
  static const String authGateTitleShare = '登录后同步分享记录';
  static const String authGateTitlePersona = '登录后管理分身';
  static const String authGateTitleSettingsAccount = '登录后管理账号';
  static const String authGateTitleMediaUpload = '登录后上传素材';
  static const String authGateTitleDeletePost = '登录后删除内容';
  static const String authGateTitleReport = '登录后提交举报';
  static const String authGateTitleJoinCircle = '登录后加入圈子';
  static const String authGateTitleAddContact = '登录后添加联系人';
  static const String authGateTitleStartGroupChat = '登录后发起群聊';
  static const String authGateTitleCreateCircle = '登录后创建圈子';
  static const String authGateTitleGeneric = '登录后继续使用';
  // 登录页副标题：表达「登录后获得什么 / 如何继续」，不得与主标题重复。
  static const String authGateSubtitleProfile = '同步你的作品、足迹、互动和分身资料。';
  static const String authGateSubtitleCreate = '保存草稿、发布记录和后续互动通知。';
  static const String authGateSubtitleOpenChat = '读取你的会话列表，并接收新的私信提醒。';
  static const String authGateSubtitleSendMessage = '消息将以你的账号身份发送，对方才能识别你。';
  static const String authGateSubtitleComment = '评论会沉淀到内容页，并跟随账号同步。';
  static const String authGateSubtitleLike = '登录后可跨设备同步点赞记录。';
  static const String authGateSubtitleFollow = '关注关系会写入账号，后续可在关注流查看。';
  static const String authGateSubtitleGreet = '用账号身份发起打招呼，对方回复后进入私信。';
  static const String authGateSubtitleFollowingFeed = '汇总你关注的人、圈子和地点的最新动态。';
  static const String authGateSubtitleShare = '同步分享记录，方便后续回看和归因。';
  static const String authGateSubtitlePersona = '管理分身资料，并保持内容身份一致。';
  static const String authGateSubtitleSettingsAccount = '查看登录方式、协议状态和账号安全设置。';
  static const String authGateSubtitleMediaUpload = '上传素材会绑定账号，便于继续编辑和发布。';
  static const String authGateSubtitleDeletePost = '确认账号身份后，才能删除自己的内容。';
  static const String authGateSubtitleReport = '举报将以账号身份提交，便于平台反馈处理进展。';
  static const String authGateSubtitleJoinCircle = '加入后圈子动态和成员关系会同步到账号。';
  static const String authGateSubtitleAddContact = '添加后可在联系人和私信中继续沟通。';
  static const String authGateSubtitleStartGroupChat = '创建群聊会同步成员关系和后续消息。';
  static const String authGateSubtitleCreateCircle = '圈子资料、成员管理和后续运营会绑定账号。';
  static const String authGateSubtitleGeneric = '登录后保存记录，并继续刚才的操作。';
  // 轻提示：触发受限动作时在原页面给出的短提示（先提示，再进入登录页）。
  static const String authGatePromptProfile = '登录后查看我的主页';
  static const String authGatePromptCreate = '登录后即可发布内容';
  static const String authGatePromptOpenChat = '登录后查看消息';
  static const String authGatePromptSendMessage = '登录后即可发送消息';
  static const String authGatePromptComment = '登录后即可评论，评论会按账号发布并沉淀到对象页';
  static const String authGatePromptLike = '登录后即可点赞';
  static const String authGatePromptFollow = '登录后即可关注';
  static const String authGatePromptGreet = '登录后即可发起打招呼';
  static const String authGatePromptFollowingFeed = '登录后查看你关注的人、圈子和地点动态';
  static const String authGatePromptShare = '登录后即可同步分享';
  static const String authGatePromptPersona = '登录后即可管理分身';
  static const String authGatePromptSettingsAccount = '登录后即可管理账号';
  static const String authGatePromptMediaUpload = '登录后即可上传素材';
  static const String authGatePromptDeletePost = '登录后即可删除自己的内容';
  static const String authGatePromptReport = '登录后即可提交举报';
  static const String authGatePromptJoinCircle = '登录后即可加入圈子';
  static const String authGatePromptAddContact = '登录后即可添加联系人';
  static const String authGatePromptStartGroupChat = '登录后即可发起群聊';
  static const String authGatePromptCreateCircle = '登录后即可创建圈子';
  static const String authGatePromptGeneric = '登录后即可继续';
  // 协议未勾选约束提示（对应 AUTH.CONSENT.REQUIRED）。
  static const String authConsentRequired = '请先勾选并同意协议';
  // 会话过期（对应 AUTH.SESSION.EXPIRED）。
  static const String authSessionExpired = '登录状态已过期，请重新登录';
  // 权限不足（对应 AUTH.PERMISSION.DENIED）。
  static const String authPermissionDenied = '当前账号暂无权限';
  static const String legalLoadFailed = '页面加载失败，请重试';
  static const String legalUnavailableTitle = '页面暂时打不开';
  static const String legalUnavailableMessage =
      '协议内容暂时无法获取，请检查网络后重试。你可以返回继续登录流程。';
  static const String profileLoginCardTitle = '登录后，可同步使用记录';
  static const String profileLoginCardSubtitle = '作品、足迹、赞过、消息与分身资料会跟随账号保存。';
  static const String profileLoginNow = '立即登录';
  static const String profileLoggedOutDisplayName = '未登录用户';
  static const String profileLoggedOutTimelineHint = '登录后，这里会展示你的作品、足迹与互动记录。';
  static const String myFootprint = '足迹', myFootprintTitle = '我的足迹';
  static const String myFootprintEmpty = '还没有足迹，去看看推荐内容吧';
  static const String myFootprintPrivacyHint = '足迹仅自己可见，自动记录你看过、赞过、评论过、转发过的内容';
  static const String myFootprintLoadMore = '加载更多';
  static String footprintTypeLabel(String type) => _footprintTypeLabel(type);
  static const String profileLikedTab = '赞过', logout = '退出登录';
  static const String logoutConfirmTitle = '确定退出登录吗';
  static const String logoutConfirmMessage =
      '退出登录后，将不能发布内容和评论，无法同步点赞、关注、足迹记录等。你可以选择切换其他账号使用。';
  static const String logoutThinkAgain = '我再想想';
  static const String logoutConfirm = '确定退出';

  /// 退出登录二级选择：默认软退出（保留快速登录），可选彻底清除。
  static const String logoutDialogTitle = '退出登录';
  static const String logoutDialogMessage =
      '退出后本机会保留登录信息，有效期内可免验证码快速登录。也可以清除本机登录信息，下次登录需重新验证。';
  static const String logoutDialogSoftAction = '退出登录';
  static const String logoutDialogHardAction = '清除登录信息并退出';
  static const String logoutDialogCancel = '取消';

  /// 软退出后提示：有效期内可免验证码快速登录。{days} 为有效期天数。
  static const String loginSoftLogoutToast = '已退出登录，{days} 天内可免验证码快速登录';

  /// 彻底退出后提示：已清除本机登录信息。
  static const String loginHardLogoutToast = '已清除本机登录信息，下次登录需重新验证';
  static const String switchAccount = '切换账号';
  static const String like = '点赞', share = '分享';
  static const String follow = '关注', comment = '评论';
  static const String sourceFromPrefix = '来自 ', welcomeTitle = '趣我圈';
  static const String welcomeMainSlogan = '遇见同趣，绽放热爱';
  static const String welcomeButtonLabel = '开启发现之旅';
  static const String startupStillStartingInline = '启动中，马上进入';
  static const String startupRecoveryTitle = '应用暂时无法启动';
  static const String startupRecoveryMessage = '请检查网络或稍后重新打开应用。';
  static const String startupRecoveryRetry = '重新尝试';
  static const String startupRecoverySupportHint = '若问题持续出现，请联系支持并提供诊断标识。';
  static const String assistantWhisperSignature = '小趣';
  static const String assistantWhisperLine = '专注你的热爱，剩下的交给我';
  static const String commentPlaceholder = '添加评论...';
  static const String commentTooLong = '评论过长';
  static const String commentEmpty = '评论不能为空';
  static const String commentClosed = '评论已关闭';
  static const String needLogin = '需要登录';
  static const String loading = '加载中...', retry = '重试';
  static const String mediaRetrying = '重试中…';
  static const String requestWaitSlow = '加载时间稍长，请稍候';
  static const String requestActionSlow = '正在处理，请稍候';
  static const String requestOutcomePending = '操作结果待确认';
  static const String cancel = '取消', close = '关闭';
  static const String openSettings = '去设置';

  static const String ok = '确定', confirm = '确认';
  static const String user = '用户', following = '已关注';
  static const String followBack = '回关', unknownUser = '未知用户';
  static const String copyLink = '复制链接';
  static const String webInstallBannerTitle = '在 App 里继续趣我圈';
  static const String webInstallBannerMobileSubtitle =
      '手机或平板打开，可直接下载 App，也可以转发给朋友安装。';
  static const String webInstallBannerDesktopSubtitle =
      '电脑端可选择对应安装包，也可以把安装页发到手机或微信里继续安装。';
  static const String webInstallBannerDownloadApp = '下载 App';
  static const String webInstallBannerShareInstall = '分享安装页';
  static const String webInstallBannerDesktopPackages = '选择安装包';
  static const String webInstallBannerIosPackage = 'iPhone / iPad';
  static const String webInstallBannerAndroidPackage = 'Android / 鸿蒙';

  static const String shareTargetWechat = '微信';

  static const String shareTargetMoments = '朋友圈';
  static const String loadFailed = '加载失败';
  static const String temporarilyUnavailable = '暂时连不上';
  static const String contentTemporarilyUnavailable = workOpenFailedTitle;
  static const String contentNotLoadedYet = '这里还没加载出来';
  static const String checkNetworkAndTryAgain = '可能是网络问题。';
  static const String contentLoadSoftFailed = '服务暂时不可用，稍后自动恢复后再试';
  static const String refreshSoftFailed = refreshFailedRetained;
  static const String refreshTimeoutSoftFailed = '这次刷新有点慢，稍后再试。';
  static const String appendSoftFailed = appendFailedRetry;
  static const String appendTapToRetry = '加载更多没成功，轻点重试';
  static String pageLoadingA11y(String surface) => '正在加载$surface';
  static const String homeCacheFallback = '网络不太稳，先看看上次刷到的首页。';
  static const String profileCacheFallback = '网络不太稳，先显示上次看到的主页。';
  static const String chatListCacheFallback = '网络不太稳，先显示本机最近的聊天。';
  static const String chatListLoadFailedTitle = '聊天列表没加载出来';
  static const String chatListLoadFailedMessage = '可能是网络问题。';
  static const String refreshFailedRetained = '这次刷新没成功，页面先保持不变。';
  static const String appendFailedRetry = '后面没加载出来，轻点重试';
  static const String appendFailedTitle = '后面没加载出来';
  static const String pageLoadFailedTitle = '这页没加载出来';
  static const String pageLoadFailedMessage = '可能是网络问题。';
  static const String searchUnavailableTitle = '搜索没连上';
  static const String searchUnavailableMessage = '请稍后再搜一次。';
  static const String searchEmptyResult = '没有找到相关结果';
  static const String searchWaitSlow = '搜索时间稍长，请稍候';
  static const String searchPartialResult = '部分结果暂时没有加载出来';
  static const String searchXiaoquLoading = '小趣正在整理搜索方向';
  static const String searchNoNetworkReferences = '暂时没有找到可引用的网络结果';
  static const String searchNoAppResults = '没有找到相关应用内结果';
  static const String searchNoIntersectionResults = '还没有找到和你相关的交集';
  static const String searchRelatedTitle = '相关搜索';
  static const String searchRelatedEmpty = '暂无相关搜索词';
  static const String searchPartialGroupFailed = '部分搜索结果没加载出来，已继续展示其它结果。';
  static const String commentLoadFailedTitle = '评论暂时没加载出来';
  static const String commentDeeplinkTargetMissing = '没找到这条评论，可能已被删除';
  static String sectionLoadFailedTitle(String section) => '$section没加载出来';
  static const String sectionLoadFailedTitleDefault = '这里没加载出来';
  static const String circleDiscussionLoadFailedTitle = '讨论没加载出来';
  static const String imageLoadFailed = '图片没加载出来';
  static const String videoPlaybackNetworkTitle = '网络不太稳定';
  static const String videoPlaybackTemporaryTitle = '暂时无法播放';
  static const String videoPlaybackUnavailableTitle = '这条视频暂时无法观看';
  static const String videoPlaybackUnavailableMessage = '可以先看看别的内容';
  static const String videoPlaybackUnsupportedTitle = '这条视频暂不支持播放';
  static const String videoPlaybackUnsupportedMessage =
      videoPlaybackUnavailableMessage;
  static const String workOpenFailedTitle = '这个作品打不开';
  static const String chatOpenFailedTitle = '这个聊天打不开';
  static const String chatOpenFailedMessage = '可能已被删除，或你暂时不能查看。';
  static const String userProfileLoadFailedTitle = '用户资料没加载出来';
  static const String homepageLoadFailedTitle = '主页没加载出来';
  static const String circleLoadFailedTitle = '圈子没加载出来';
  static const String permissionRequiredTitle = '需要开启权限';
  static const String validationCheckFields = '请检查填写内容后重试';
  static const String loginThenRetry = '请先登录后再试';
  static const String rateLimitedRetryLater = '操作太频繁，请稍后重试';
  static const String operationFailedRetry = '操作失败，请稍后重试';
  static const String submitNotCompleted = '提交未完成';
  static const String checkFieldsTitle = '请检查填写内容';
  static const String tryAgain = '再试一次';
  static const String back = '返回';
  static const String gotIt = '我知道了';
  static const String loginToContinue = '登录后继续';
  static const String contentUnavailable = '这个作品不可用了';
  static const String contentUnavailableReason = '可能已被删除或暂时打不开。';
  static const String homepageInfoUnavailableTitle = '主页暂不可用';
  static const String userInfoUnavailableTitle = '用户暂不可用';
  static const String conversationInfoUnavailableTitle = chatOpenFailedTitle;
  static const String report = '举报';
  static const String profileBlockUser = '拉黑';
  static const String profileBlockConfirmTitle = '确认拉黑该用户？';
  static const String profileBlockConfirmMessage = '拉黑后将不再看到对方内容，也不会收到其消息。';
  static const String profileBlockSuccess = '已拉黑该用户';
  static const String profileReportReasonTitle = '选择举报原因';
  static const String profileReportReasonSpam = '垃圾营销';
  static const String profileReportReasonMisinformation = '不实信息';
  static const String profileReportReasonHarassment = '骚扰辱骂';
  static const String profileReportReasonPornography = '色情低俗';
  static const String profileReportReasonOther = '其他';
  // 「打动」摘要模块（他人 / 我的双视角）：§18.7.1 前台由「影响力」收敛为「打动的人」列表视角（机器名 impact 字段不变）。
  static const String profileImpactTitleMine = '我打动的人';
  // §24.8 他人主页统一「TA打动的人」，与「我打动的人」对称。
  static const String profileImpactTitleOther = 'TA打动的人';
  static const String profileImpactSubtitleMine = '我的内容真实帮到了谁';
  static const String profileImpactSubtitleOther = 'TA的内容真实帮到了谁';
  static const String profileImpactEmptyMine = profileInteractionEmptyGuidance;
  static const String profileImpactEmptyOther = 'TA 打动的人还在形成中，更多连接与带动会展示在这里';
  static const String profileShareHomepage = '分享主页';
  static const String shareComingSoon = '主页分享暂不可用';
  static const String notInterested = '不感兴趣';
  static const String shareTo = '分享到';
  static const String shareInternalTitle = '分享到趣我圈';
  static const String shareExternalTitle = '分享到其他平台';
  static const String shareTargetCircle = '圈子';
  static const String shareTargetGroup = '群聊';
  static const String shareTargetMessage = '私信';
  static const String shareActionMore = '更多';
  static const String shareSelectCircleTitle = '选择圈子';
  static const String shareSelectGroupTitle = '选择群聊';
  static const String shareSelectMessageTitle = '选择私信';
  static const String shareNoCircles = '还没有可分享的圈子';
  static const String shareCircleConfirmMessage = '内容会作为转发记录出现在该圈子中。';
  static const String shareCircleSuccess = '已分享到圈子';
  static const String shareCompleted = '分享完成';
  static const String shareCircleFailedTitle = '转发未完成';
  static String shareCircleConfirmTitle(String circleName) =>
      '转发到“$circleName”？';
  static const String shareActionSavePoster = '保存海报';
  static const String shareActionSystemShare = '系统分享';
  static const String sharePrivateBlocked = '仅自己可见内容不可分享';
  static const String shareCircleVisibilityNotice = '圈内可见内容将生成受控链接';
  static const String shareLinkCopied = '分享链接已复制';
  static const String sharePosterSaved = '海报已保存到本地文件';
  static const String shareCancelled = '已取消分享';
  static const String shareFailed = '分享失败，请稍后重试';
  static const String shareSeedWorkFallbackTitle = '作品';
  static const String shareSeedDefaultTitle = '内容分享';
  static String shareSeedVideoWorkTitle(String displayName) =>
      '$displayName 的视频作品';
  static String shareSeedImageWorkTitle(String displayName) =>
      '$displayName 的图片作品';
  static String shareSeedMomentTitle(String displayName) => '$displayName 的点滴';
  static const String savePhoto = '保存图片', saveVideo = '保存视频';
  static const String unknown = '未知', commentSent = '评论已发送';
  static const String replySent = '回复已发送';
  static const String pullToRefreshHint = '下拉刷新试试';
  static const String goToUserProfile = '前往用户主页';
  static const String loadMoreComments = '加载更多评论';
  static const String noComment = '暂无评论', replyAction = '回复';
  static const String commentAuthorBadge = '作者';
  static const String commentPinnedBadge = '置顶';
  static const String commentAuthorLikedBadge = '作者赞过';
  static const String commentPinAction = '置顶';
  static const String commentUnpinAction = '取消置顶';
  static const String commentPinnedToast = '已置顶';
  static const String commentUnpinnedToast = '已取消置顶';
  static const String commentPinForbidden = '仅内容作者可置顶评论';
  static const String commentDislike = '点踩';
  static const String commentExpandMoreReplies = '展开更多回复';
  static const String commentAttachImage = '图片';
  static const String commentAttachmentLimitReachedTemplate = '最多添加 %s 张图片';
  static const String commentMention = '@';
  static const String commentEntryCountIncreaseNoticeTemplate = '较打开前新增 %s 条评论';
  static const String commentEntryCountDecreaseNoticeTemplate = '较打开前删除 %s 条评论';
  static const String profileCommentsTabSent = '我发出的';
  static const String profileCommentsTabReceived = '我收到的';
  static const String profileCommentViewOriginal = '查看原内容';
  static const String profileCommentReplyInContext = '继续回复';
  static const String profileCommentOriginalUnavailable = '原作品暂时看不了';
  static const String commentReportSubmitted = '举报已提交';

  /// 评论区标题：共 N 条评论。
  static const String commentCountTitleTemplate = '共 %s 条评论';

  /// 评论输入浮层：发送按钮。
  static const String commentSend = '发送';

  /// 评论平铺区：回复某人占位。
  static const String commentReplyToTemplate = '回复 %s';

  /// 他人主页交集模块标题：从「为什么推荐TA」收敛为「我与TA的交集」。
  static const String profileWhyRecommendTitle = '我与TA的交集';

  /// 实体主页介绍卡标题（去「实体/认识XX」泛词，统一「关于这里」）。
  static const String entityAboutTitle = '关于这里';

  /// 实体主页头部官方认证徽标（已通过官方核验）。
  static const String entityVerifiedBadge = '已认证';

  /// 实体主页头部成立年份（如「1982 年创立」）。
  static String entityEstablishedYearLabel(int year) => '$year 年创立';

  /// 实体主页头部关注计数（如「1.2万 关注」，数量由调用方格式化）。
  static String entityFollowerCountLabel(String formattedCount) =>
      '$formattedCount $follow';
  // Work Browser 视频集进度（时间轴下方、标题上方）
  static String videoSeriesProgress(int current, int total) =>
      '视频集 · $current/$total';
  // Work Browser 文章页码（正文下方、作者工具栏上方）
  static String workArticlePageProgress(int current, int total) =>
      '$current / $total';
  static const String profileStatementFallbackSubtitle = '新的交集正在生成';
  static const String objectIntersectionCtaFollowAuthor = '关注作者';
  static const String objectIntersectionCtaJoinCircle = '加入圈子';
  static const String objectIntersectionCtaAddContact = '加为联系人';
  static const String objectIntersectionCtaAskAssistant = '问问小趣';
  static const String objectIntersectionCtaView = '查看这条交集';

  /// 对象/圈子主页「我的交集」模块统一标题（与我的主页同语义 token）。
  static const String objectMyIntersectionsTitle = '我的交集';

  /// 实体主页「打动」模块标题（§24.8「这里打动的人」）。
  static const String objectImpactTitleEntity = '这里打动的人';

  /// 圈子主页「打动」模块标题（§24.8「圈子打动的人」）。
  static const String objectImpactTitleCircle = '圈子打动的人';

  /// 实体主页「我的交集」空态：你与这里尚无可展示事实交集，行动引导生成真实连接。
  static const String objectIntersectionEmptyEntity =
      '你和这里暂时没有可展示交集，发记录或关注相关内容后会在这里沉淀';

  /// 圈子主页「我的交集」空态：不否认圈子本身影响力，只表达 viewer × circle 暂无交集。
  static const String objectIntersectionEmptyCircle =
      '你和这个圈子暂时没有可展示交集，进入讨论或关注成员后会在这里沉淀';

  /// 实体主页核心动作次按钮：围绕这里沉淀记录。
  static const String entityActionPublishRecord = '发记录';

  /// 圈子主页核心动作次按钮：进入讨论（切换到讨论 tab）。
  static const String circleActionEnterDiscussion = '进入讨论';
  static const String objectConnectionWithYou = '与你的交集';
  static const String impactEnumerableHintMine = '可查看与你内容相关的连接来源';
  static const String impactEnumerableHintOther = '可查看与TA内容相关的连接来源';
  static const String impactEnumerableHintCircle = '可查看这个影响的连接来源';
  static const String impactEnumerableHintEntity = '可查看这个影响的连接来源';
  static const String objectIntersectionsTitle = '全部交集';
  static const String objectIntersectionsEmpty = '暂时没有可展示的交集';
  static const String objectIntersectionsUnavailableTitle = '交集暂不可用';
  static const String objectHomepageDefaultTitle = '这个主页';
  static const String homepageMaintainAction = '维护主页';
  static const String homepageClaimAction = '认领主页';
  static const String homepageClaimPendingAction = '认领审核中';
  static const String homepageStatusReportAction = '状态上报';
  static const String homepageAttachPublishEnabled = '关联到本次发布';
  static const String homepageAttachPublishDisabled = '这个主页待审核，暂不可操作';
  static const String homepageContentSectionTitle = '相关内容';
  static const String homepageDiscussionSectionTitle = '大家在聊';
  static String homepageDiscussionSectionTitleFor(String objectName) =>
      '大家在聊$objectName';
  static const String homepageInterestCircleSectionTitle = '相关圈子';
  static const String homepageContentEmptyTitle = '还没有相关内容';
  static const String homepageContentEmptyDescription = '后续围绕这个主页发布的内容会展示在这里。';
  static const String homepageDiscussionEmptyTitle = '还没有讨论';
  static const String homepageDiscussionEmptyDescription = '大家围绕这个主页的讨论会展示在这里。';
  static const String homepageInterestCircleEmptyTitle = '还没有相关圈子';
  static const String homepageInterestCircleEmptyDescription =
      '围绕这个主页形成的圈子会展示在这里。';
  static const String homepageRelatedGroupSubtitle = '位成员也在这里';
  static const String homepageContentTypeArticle = '文章';
  static const String homepageContentTypeVideo = '视频';
  static const String homepageContentTypeImage = '图片';
  static const String homepageContentTypeOpinion = '口碑';
  static const String homepageContentTypeQuestion = '提问';
  static const String homepageContentTypeDefault = '内容';
  static const String homepageTypeDefault = '地点和事物';
  static const String circleInfoUnavailableTitle = '圈子信息暂不可用';
  static const String publishAssistantSuggestTitle = '小趣推荐';
  static const String publishAssistantSuggestAction = '推荐标签和关联主页';
  static const String publishAssistantSuggestSubtitle =
      '基于草稿内容推荐标签、关联主页和摘要，结果可继续调整';
  static const String publishAssistantSuggestUnavailable = '创作助手暂未启用';
  static const String publishAssistantSuggestNoResult = '暂时没有新的推荐';
  static const String publishAssistantSuggestFailed = '小趣推荐失败，请稍后再试';
  static const String objectTabContent = '内容';
  static const String objectTabRecord = '记录';
  static const String objectTabDiscussion = '讨论';
  static const String objectTabRelatedCircles = '相关圈子';
  static const String objectTabMembers = '成员';
  static const String homepageSubCampusLife = '校园生活';
  static const String homepageSubOpinion = '口碑';
  static const String homepageSubQuestion = '提问';
  static const String objectIntroMoreLabel = '查看更多';
  static String objectIntroTitle(String objectName) => '认识$objectName';
  static const String objectIntroSourceTitle = '内容来源';
  static const String objectIntroSourceOpen = '查看原始来源';
  static String objectIntroSourcePlatform(String sourceKind) =>
      _objectIntroSourcePlatform(sourceKind);
  static const String editProfile = '编辑资料', settings = '设置';
  static const String settingsAccountSection = '账号';
  static const String settingsPrivacySection = '权限';
  static const String settingsAppearanceSection = '外观';
  static const String settingsAboutSection = '关于';
  static const String settingsPermissionManagement = '权限管理';
  static const String settingsPermissionLayerSection = '权限层级';
  static const String settingsContactsPermission = '联系人权限';
  static const String settingsCirclesPermission = '圈子权限';
  static const String settingsEntitiesPermission = '实体权限';
  static const String settingsPermissionReserved = '待接入';
  static const String settingsDarkMode = '深色模式';
  static const String settingsDarkModeOff = '关闭';
  static const String settingsDarkModeOn = '打开';
  static const String settingsDarkModeSystem = '跟随系统';
  static const String settingsDarkModeSystemDescription =
      '开启后，应用内夜间模式状态和系统保持一致';
  static const String settingsDarkModeManualSection = '手动选择';
  static const String settingsDarkModeLightOption = '浅色模式';
  static const String settingsDarkModeDarkOption = '深色模式';
  static const String settingsAboutQuwoquan = '关于趣我圈';
  static const String settingsVersion = '版本';
  static const String settingsAboutDefaultVersion = '1.1.0';
  static const String settingsAppOfficialName = '趣我圈';
  static String settingsPendingSync(String value) => '$value · 待同步';
  static String settingsVersionValue(String value) => value;
  static const String createCircle = '创建圈子';
  static const String circleCreateSuccess = '圈子已创建';
  static const String editCircle = '编辑圈子';
  static const String manageCenter = '管理中心';
  static const String circleEditSettings = '圈子设置';
  static const String followCircle = '关注圈子';
  static const String followedCircle = '已关注圈子';
  static const String joinCircle = '加入圈子';
  static const String joinedCircle = '已加入圈子';
  static const String joinPending = '加入审批中';
  static const String circleMembers = '成员', circleGroups = '讨论';
  static const String circleFans = '粉丝', circleLikes = '获赞';
  static const String circlePosts = '创作', circleWeeklyActive = '活跃';
  static const String searchMembersHint = '搜索成员...';

  /// 群成员搜索页搜索框占位（端侧过滤）。
  static const String searchGroupMembers = '搜索群成员';

  /// 成员列表本地过滤无结果。
  static const String noMatchingMembers = '暂无匹配成员';
  static const String searchGroupsHint = '搜索讨论...';
  static const String searchFansHint = '搜索粉丝...';
  static const String searchLikesHint = '搜索获赞记录...';
  static const String noData = '暂无数据';
  static const String noLikesRecord = '暂无获赞记录';
  static const String circleWorksTab = '创作';
  static const String circleInteractionTab = '互动';
  static const String circleAssetsTab = '资料', circleLifestyleTab = '生活';
  static const String circleSubAll = '全部', circleSubPhoto = '图片';
  static const String circleSubVideo = '视频', circleSubArticle = '笔记';
  static const String circleSubLikes = '赞', circleSubComments = '评论';
  static const String circleSubMicro = '点滴', circleSortLatest = '最新';
  static const String circleSortHot = '最热', circleSortFeatured = '精选';
  static const String circleNoCreations = '暂无创作内容';
  static const String circleNoChatEnabled = '讨论尚未开启';
  static const String circleUploadFile = '上传文件';
  static const String circleStorageUsed = '已用';
  static const String circleStorageRemaining = '剩余';
  static const String circleStorageBackToParent = '返回上级目录';
  static const String circleComments = '评论';
  static const String circleOfficialBadge = '官方认证 | 优质社区';
  static const String circlesRecommendedTitle = '推荐圈子';
  static const String circlesDirectoryTitle = '圈子广场';
  static const String circlesSearchHint = '搜索圈子、对象和内容';
  static const String circlesEntitySectionTitle = '地点和事物';
  static const String circlesEntitySectionHint = '从景点到车型，看看大家在聊什么';
  static const String circlesFollowingEmpty = '关注暂无内容';
  static const String discoveryEndHint = '已经到底啦';
  static const String circleManageChannels = '讨论管理';
  static const String circleMyChannels = '我的讨论';
  static const String circleAllChannels = '全部讨论';
  static const String circleDragToSort = '拖动排序';
  static const String circleTapToAdd = '点击添加讨论';
  static const String circleInfoSectionTitle = '基本信息';
  static const String circlePermissionSectionTitle = '访问与加入';
  static const String circleSurfaceSectionTitle = '展示与协作';
  static const String circleMediaSectionTitle = '头像与封面';
  static const String circleCategoryLabel = '圈子分类';
  static const String circleCoverLabel = '圈子封面';
  static const String circleCoverHint = '建议使用横图，创建后会展示在圈子主页头图和推荐列表中';
  static const String circleAvatarLabel = '圈子头像';
  static const String circleAvatarTitle = '主页头像';
  static const String circleAvatarHint = '圆形头像会展示在圈子主页、成员入口和圈子卡片中';
  static const String circleAddAvatar = '添加头像';
  static const String circleChangeAvatar = '更换头像';
  static const String circleRemoveAvatar = '移除头像';
  static const String circleRemoveCover = '移除封面';
  static const String circleSelectFromPhotos = '从照片中选择';
  static const String circleNameLabel = '圈子名称';
  static const String circleNamePlaceholder = '输入圈子名称';
  static const String circleDescriptionLabel = '圈子简介';
  static const String circleDescriptionPlaceholder = '写一句能代表圈子气质的介绍';
  static const String circleTagsLabel = '圈子标签';
  static const String circleTagsPlaceholder = '用空格分隔标签，如 摄影 胶片 城市漫步';
  static const String circleVisibilityLabel = '可见范围';
  static const String visibilityMembers = '成员可见';
  static const String circleVisibilityPublicDescription = '公开展示，所有人都可发现';
  static const String circleVisibilityMembersDescription = '仅成员可见，更适合小范围共创';
  static const String circleJoinPolicyLabel = '加入方式';
  static const String circleJoinApproval = '申请加入';
  static const String circleJoinOpenDescription = '可直接加入，降低新成员进入门槛';
  static const String circleJoinApprovalDescription = '提交申请后由管理员审核';
  static const String circleAutoSyncChatLabel = '同步圈聊';
  static const String circleAutoSyncChatHint = '保持主页圈聊入口和成员状态一致';
  static const String circleSectionDisplayLabel = '主页板块';
  static const String circleSectionVisible = '显示在主页';
  static const String circleSaveChanges = '保存更改';
  static const String circleSaveSuccess = '圈子设置已更新';
  static const String done = '完成';
  static const String seeMore = '查看更多', fullText = '全文';
  static const String collapse = '收起', ellipsis = '...';
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
  static const String atMe = '@我', atXiaoqu = '@小趣';
  static const String unread = '未读', reminders = '提醒';
  static const String secretMessage = '密信', friends = '联系人';
  static const String groupChat = '群聊', chatPrivateMessages = '私聊';
  static const String chatNotifications = '通知';
  static const String secretLockedTitle = '密信已锁定';
  static const String secretUnlockButton = '解锁密信';
  static const String secretPasswordHint = '请输入密信密码';
  static const String secretPasswordPrompt = '输入密码以查看对话';
  static const String secretPasswordError = '密码错误，请重试';
  static const String secretUnlockedBanner = '密信已解锁';
  static const String secretLockButton = '锁定';
  static const String noSecretConversations = '暂无密信对话';
  static const String noConversations = '暂无对话';
  static const String startChatHint = '开始与圈友聊天吧！';
  static const String noMentionsMessages = '暂无@我的消息';
  static const String noMentionsHint = '有人提到你时，会在这里提醒你';
  static const String noUnreadMessages = '暂无未读消息';
  static const String noUnreadHint = '新消息来了，会第一时间出现在这里';
  static const String noXiaoquMessages = '暂无小趣回复';
  static const String noXiaoquHint = '你在评论或圈子里 @小趣 后，回复会出现在这里';
  static const String commentAtXiaoqu = '@小趣';
  static const String commentXiaoquBadge = '小趣回复';
  static const String commentXiaoquSource = '基于当前内容与评论上下文生成，可继续追问或纠错';
  static const String noReminderMessages = '暂无提醒';
  static const String noReminderHint = '主页动态、圈子摘要和主动提醒会在这里汇总';
  static const String untitledConversation = '未命名对话';
  static const String chatPreviewImage = '[图片]';
  static const String chatPreviewVideo = '[视频]';
  static const String chatPreviewFile = '[文件]';
  static const String chatPreviewVoice = '[语音]';
  static const String chatPreviewCall = '[通话]';
  static const String chatPreviewCard = '[卡片]';
  static const String chatPreviewRecalled = '[消息已撤回]';
  static const String contactsTabAll = '全部', chatPrimaryContacts = '联系';
  static const String contactsTabCircles = '圈子';

  /// 联系人一级 Tab 下的二级：互相关注
  static const String contactsTabMutualFollow = '互相关注';

  /// 联系人一级 Tab 下的二级：群聊（wire filter 仍为 group）
  static const String contactsTabFunGroup = '群聊';
  static const String contactsTabFriends = '联系人';
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
  static const String send = '发送', emoji = '表情';
  static const String keyboard = '键盘', more = '更多';
  static const String voiceInput = '语音输入', expand = '展开';

  /// 实时通话
  static const String call = '语音通话', videoCall = '视频通话';
  static const String callVoice = '语音通话', callVideo = '视频通话';
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
  static const String callReject = '拒绝', callDecline = '拒接';
  static const String callAccept = '接听', callHangup = '挂断';
  static const String callMute = '静音', callUnmute = '取消静音';
  static const String callFlipCamera = '翻转摄像头';
  static const String callSpeaker = '扬声器';
  static const String callInvite = '邀请', callIncoming = '来电';
  static const String callIncomingVoice = '语音来电';
  static const String callIncomingVideo = '视频来电';
  static const String callSourceCurrentConversation = '当前会话';
  static const String callSourceMutualFollow = '互相关注';
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
  static const String callRecordingBadge = 'REC';
  static const String callConnectFailed = '连接通话失败，请重试';
  static const String callAnswerFailed = '接听失败，请重试';
  static const String callSwitchInviteSourceFailed = '切换邀请来源失败';
  static const String callSwitchGroupMembersFailed = '切换群聊成员失败';
  static const String callTrustUnknownBadge = '可能不认识';
  static const String callOngoing = '通话中';
  static const String callBarTapToReturn = '点击返回';
  static const String callHangupConfirmTitle = '结束通话';
  static const String callHangupConfirmBody = '确定要挂断当前通话吗？';
  // 通话结束摘要（FaceTime 级）：时长 + 结束原因的统一文案前缀。
  static const String callSummaryDurationPrefix = '通话时长 ';
  static const String callSummaryCancelled = '已取消';
  static const String callSummaryRejected = '对方已拒绝';
  static const String callSummaryMissed = '未接听';
  static const String callSummaryNoAnswer = '无人接听';
  // 通话权限（S6）：麦克风/摄像头权限卡片与降级文案。
  static const String callPermissionMicTitle = '需要麦克风权限';
  static const String callPermissionMicDenied = '开启麦克风后才能进行通话';
  static const String callPermissionCameraTitle = '需要摄像头权限';
  static const String callPermissionCameraDenied = '开启摄像头后才能进行视频通话';
  static const String callPermissionOpenSettings = '请在系统设置中开启权限';
  static const String callPermissionFallbackVoiceOnly = '仅语音通话';
  // 通话过程态（S5）：由 [resolveCallStage] 统一派生，页面只读对应文案。
  static const String callStageConnecting = '正在接通...';
  static const String callStageRinging = '等待对方接听...';
  static const String callStageWaitingPeer = '等待对方加入...';
  static const String callStageReconnecting = '连接不稳定，正在重连...';
  static const String callStageWeakNetwork = '当前网络较弱';
  static const String callStagePeerNoAnswer = '对方未接听';
  static const String callStagePeerLeft = '对方已离开通话';
  static const String callStageEnded = '通话已结束';

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
  static const String groupName = '群聊名称', qrCode = '二维码';
  static const String groupAnnouncement = '群公告';
  static const String groupAnnouncementEmpty = '未设置';
  static const String groupSourcePrefix = '来自：';
  static const String groupMemberCountSuffix = '成员';
  static const String groupCapabilityAlbum = '相册';
  static const String groupCapabilityFile = '文件';
  static const String groupCapabilityActivity = '活动';
  static const String groupCapabilityMembers = '成员';
  static const String muteNotifications = '消息免打扰';
  static const String pinChat = '置顶聊天';
  static const String privacyShield = '隐私屏障(禁截屏、禁转发)';
  static const String setChatBackground = '设置当前聊天背景';
  static const String clearChatHistory = '清空聊天记录';
  static const String circleSubmitPost = '向圈子投稿';
  static const String exitGroupChat = '退出群聊';
  static const String exitGroupChatConfirmMessage = '退出后将不再接收该群聊消息，确定退出吗？';
  static const String exitGroupChatSuccess = '已退出群聊';
  static const String dissolveGroupChat = '解散该群聊';
  static const String dissolveGroupChatConfirmMessage =
      '解散后所有成员将被移出群聊，此操作不可撤销。';
  static const String groupChatDissolvedToast = '群聊已解散';
  static const String dissolveGroupChatFailedToast = '解散群聊失败，请稍后重试';
  static const String addMember = '添加成员', groupManagement = '群管理';
  static const String groupNameAdminOnly = '群聊已设定为只有群主或管理员才能修改名称';
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
  static const String groupAdminDescription = '管理员可协助群主管理群聊，拥有发布公告、移除成员等能力。';
  static const String groupAdminOnlyOwner = '只有群主具备设置管理员、解散群聊的能力。';
  static const String groupAdminMaxCount = '最多可设置3个管理员。';
  static const String admin = '管理员';
  static const String owner = '群主';

  /// 发起群聊页（wire filter/type 仍为 group）
  static const String startGroupChat = '发起群聊', addContact = '添加';
  static const String chatMutualFollowRtcHint = '互相关注后可发起语音和视频通话';
  static const String chatBlockedConversationHint = '当前会话已被关系门禁限制，暂时无法继续发送消息';
  static const String chatBlockedConversationInputHint = '当前会话暂不可发送消息';
  static const String chatGreetingInboxTitle = '新的打招呼';
  static const String chatGreetingInboxEmpty = '暂时没有待处理的打招呼';
  static const String chatGreetingInboxReply = '回复并建会话';
  static const String chatGreetingInboxIgnore = '忽略';
  static const String chatGreetingSent = '打招呼已发送';
  static const String chatGreetingReplySucceeded = '已回复，正式会话已建立';
  static const String chatGreetingIgnored = '已忽略打招呼';
  static const String addContactSheetTitle = '添加联系人';
  static const String noAddableContacts = '暂无可添加联系人';
  static const String globalActionSheetTitle = '发起';
  static const String globalSearchTitle = '搜索';
  static const String createActionCamera = '从摄像';
  static const String createActionTextShort = '写点字';
  static const String createActionGroupChatHint = '邀请联系人加入群聊';
  static const String createActionContactHint = '找到新联系，发起对话';
  static const String createNewGroupChat = '创建新群聊';
  static const String selectFriendsFromGroupChat = '选择群聊成员';
  static const String selectFriendsFromCircle = '选择圈子成员';
  static const String relatedMutualFollow = '互相关注';
  static const String selectGroupChat = '选择群聊';
  static const String searchGroupChatHint = '搜索群聊';
  static const String selectCircle = '选择圈子';
  static const String searchCircleHint = '搜索圈子';
  static const String selectAll = '全选', selectAction = '选择';
  static const String friendsCount = '个朋友';

  /// 添加联系人（主页/扫一扫/手机通讯录/我的二维码/搜索/确认）
  static const String addContactSearchHubPlaceholder = '搜索手机号或趣我圈号';
  static const String addContactScanEntrySubtitle = '扫描二维码名片';
  static const String addContactPhoneEntryTitle = '手机联系人';
  static const String addContactPhoneEntrySubtitle = '从通讯录中查找';
  static const String addContactMyQrCardSubtitle = '让对方扫一扫加你为联系人';
  static const String addContactSearchTitle = '查找联系人';
  static const String addContactSearchEmptyPrompt = '输入手机号或趣我圈号查找';
  static const String addContactSearchNoResult = '没有找到相关用户';
  static const String contactAlreadyAdded = '已添加';
  static const String contactAddBack = '回关';
  static const String addContactConfirmSourceScan = '来自扫一扫';
  static const String addContactConfirmSourcePhone = '来自手机联系人';
  static const String addContactConfirmSourceSearch = '来自搜索';
  static const String addContactConfirmSourceQr = '来自二维码';
  static const String addContactConfirmedToast = '已添加';
  static const String addContactFailedTitle = '添加未完成';
  static const String addContactFailedMessage = '这次没有添加成功，稍后可以再试一次。';
  static const String scanQrHint = '将二维码放入框内，即可自动扫描';
  static const String scanQrAlbum = '相册';
  static const String scanQrNoCodeFound = '未识别到联系人二维码，请选择对方的二维码图片';
  static const String scanQrInvalidCode = '无法识别该联系人二维码，请让对方提供自己的二维码';
  static const String scanQrCameraPermissionTitle = '开启相机以扫码';
  static const String scanQrCameraPermissionBody = '扫描二维码需要使用相机。';
  static const String scanQrCameraPermissionCta = '去开启相机权限';
  static const String scanQrCameraUnavailableTitle = '当前无法使用相机';
  static const String scanQrCameraUnavailableBody = '可以稍后再试，或从相册选择对方的联系人二维码。';
  static const String phoneContactsPermissionTitle = '查找通讯录联系人';
  static const String phoneContactsPermissionBody =
      '开启通讯录权限后，可发现已注册趣我圈的联系人。手机号仅在本机哈希后用于匹配，原文不会上传。';
  static const String phoneContactsPermissionCta = '去开启通讯录权限';
  static const String phoneContactsPermissionDenied = '通讯录权限未开启';
  static const String phoneContactsMatchedSectionTitle = '通讯录中的趣我圈用户';
  static const String phoneContactsNoMatch = '通讯录里暂时没有已注册的联系人';
  static const String phoneContactsEmpty = '通讯录是空的';
  static const String phoneContactsSearchPlaceholder = '搜索联系人';
  static const String phoneContactsUnavailable = '当前设备不支持读取通讯录';
  static const String addContactPrivacyHashNote = '手机号仅在本机哈希后用于匹配，不会上传原文';
  static String phoneContactsMatchedCount(int count) => '$count 位联系人已注册趣我圈';

  /// 聊天信息页：超过首屏成员时展开入口
  static const String moreMembers = '更多成员';

  /// 聊天信息页：收起成员列表
  static const String collapseMembers = '收起来';

  /// 聊天底部「更多」面板（图二：两行六项）
  static const String chatMorePhoto = '照片', chatMoreShoot = '拍摄';
  static const String chatMoreFile = '文件', chatMoreVideo = '视频';
  static const String chatMoreBurnAfterRead = '阅后即焚';
  static const String chatMoreLocation = '位置';
  static const String chatMoreAudioVideo = '音视频';
  static const String chatMoreRedPacket = '红包';
  static const String chatAttachmentTypeConflict = '图片与文件不能同时添加';
  static const String chatAttachmentMaxCount = '最多添加 %s 个';
  static const String chatAttachmentUploadFailed = '附件上传失败';
  static const String chatAttachmentSendFailed = '附件发送失败';
  static const String chatVoiceHoldToTalk = '按住说话';
  static const String chatVoiceHoldTip = '按住开始录音';
  static const String chatVoiceReleaseToSend = '松开发送';
  static const String chatVoiceSlideCancel = '上滑取消';
  static const String chatVoiceReleaseCancel = '松开取消';
  static const String chatVoiceRecording = '正在录音';
  static const String chatVoiceMaxDurationSoon = '即将到达最长录音时长';
  static const String chatVoiceUploading = '语音上传中';
  static const String chatVoiceQueued = '语音已加入待发送队列';
  static const String chatVoiceTooShort = '说话时间太短';
  static const String chatVoiceCanceled = '已取消';
  static const String chatVoiceSending = '发送中';
  static const String chatVoicePermissionDenied = '未获得录音权限';
  static const String chatVoicePermissionOpenSettings =
      '请在 设置 → 趣我圈 → 麦克风中开启权限后再发送语音';
  static const String chatVoicePermissionPrimerTitle = '需要麦克风权限';
  static const String chatVoicePermissionPrimerMessage =
      '按住说话发送语音消息需要使用麦克风。点「继续」后，请在系统弹窗中选择「允许」。';
  static const String chatVoicePermissionPrimerContinue = '继续';
  static const String permissionPrimerContinue = '继续';
  static const String chatVoicePermissionGrantedAfterSettings =
      '麦克风已开启，可以发送语音了';
  static const String permissionMicrophoneLabel = '麦克风';
  static const String permissionCameraLabel = '相机';
  static const String permissionPhotosLabel = '相册';
  static const String permissionLocationLabel = '定位';
  static const String permissionContactsLabel = '通讯录';
  static const String permissionNotificationsLabel = '通知';
  static const String permissionRetryAuthorization = '重试授权';
  static String permissionSettingsGateTitle(String permissionLabel) =>
      '需要在设置中开启$permissionLabel';
  static const String permissionPhotosOpenSettings =
      '请在 设置 → 趣我圈 → 相册中开启权限后再选择媒体';
  static const String permissionPhotosPrimerTitle = '需要相册权限';
  static const String permissionPhotosPrimerMessage =
      '选择图片或视频需要访问相册。点「继续」后，请在系统弹窗中选择「允许」。';
  static const String permissionLocationPrimerTitle = '需要定位权限';
  static const String permissionLocationPrimerMessage =
      '展示附近地点需要获取你的位置。点「继续」后，请在系统弹窗中选择「允许」。';
  static const String permissionLocationOpenSettings =
      '请在 设置 → 趣我圈 → 定位中开启权限，并确认系统定位服务已打开';
  static const String permissionLocationDenied = '未获得定位权限';
  static const String permissionContactsPrimerTitle = '需要通讯录权限';
  static const String permissionContactsPrimerMessage =
      '发现已注册联系人需要访问通讯录。点「继续」后，请在系统弹窗中选择「允许」。';
  static const String permissionContactsOpenSettings = '请在 设置 → 趣我圈 → 通讯录中开启权限';
  static const String permissionContactsDenied = '未获得通讯录权限';
  static const String permissionNotificationsPrimerTitle = '需要通知权限';
  static const String permissionNotificationsPrimerMessage =
      '接收消息提醒需要通知权限。点「继续」后，请在系统弹窗中选择「允许」。';
  static const String permissionNotificationsOpenSettings =
      '请在 设置 → 趣我圈 → 通知中开启权限';
  static const String permissionNotificationsDenied = '未获得通知权限';
  static String permissionStillDeniedMessage(String permissionLabel) =>
      '$permissionLabel 仍未开启，请按 设置 → 趣我圈 → $permissionLabel 手动开启';

  static String permissionGrantedMessage(String permissionLabel) =>
      '$permissionLabel 已开启';

  static String permissionRestrictedMessage(String permissionLabel) =>
      '$permissionLabel 权限受系统限制，暂不可用';
  static const String chatVoiceRecordUnavailable = '暂时无法录音，请稍后重试';
  static const String chatVoicePendingRetry = '语音没发出去，已保存，点重试';
  static const String chatVoiceUploadFailed = '语音上传失败，请重试';
  static const String chatVoiceSendFailedTitle = '语音发送失败';
  static const String chatVoiceSendFailed = '语音发送失败，请重试';
  static const String chatVoicePlayUnavailable = '语音暂不可播放';
  static const String timeFormatAM = '上午', timeFormatPM = '下午';
  static const String assistantHome = '助理主页';

  /// 助手 run 失败时展示的通用提示（会话/存储/模型等任一步骤异常均会触发）
  static const String assistantUnavailable = '助手暂时不可用，请稍后重试。';
  static const String assistantModelUnavailable =
      '当前未配置可用模型，请先在模型配置中接入远程模型或桥接服务。';
  static const String assistantRunningHint = '小趣正在规划与执行中...';

  /// v3 用户视角阶段：先帮用户理清问题
  static const String assistantPhaseUnderstanding = '理解问题';

  /// v3 用户视角阶段：替用户核对资料（工具执行，由元数据覆盖）
  static const String assistantPhaseSearching = '检索设计';

  /// v3 用户视角阶段：替用户整理判断
  static const String assistantPhaseAnalyzing = '检索处理';

  /// v3 用户视角阶段：替用户组织最终回答
  static const String assistantPhaseAnswering = '生成答案';

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
  static const String assistantHistoryEmpty = '暂无对话记录';

  /// 身份/分身（1:1 对应 PersonaSwitcher.tsx）
  static const String personaManage = '管理分身';
  static const String personaSwitchProfile = '切换分身';
  static const String personaDefaultOnlyHint = '为不同兴趣创建分身，记录和互动会更清晰';
  static const String personaPrimary = '主分身';
  static const String personaCreate = '新增分身';
  static const String personaCreateTitle = '创建分身';
  static const String personaCreateSuccess = '分身已创建';
  static const String personaSwitchNow = '立即切换';
  static const String personaSwitchLater = '稍后切换';
  static const String personaCurrentUsing = '当前使用';
  static const String personaInactive = '未激活', personaDelete = '删除';
  static const String personaRetire = '退役', personaRetired = '已退役';
  static const String personaSyncApply = '同步资料';
  static const String personaSyncIgnore = '暂不处理';
  static const String personaSyncApplyAll = '同步到全部分身';
  static const String personaSyncApplySelected = '同步到指定分身';
  static const String personaUserHandleLabel = '用户号';
  static const String personaPhoneLabel = '手机号';
  static const String personaEmailLabel = '邮箱';
  static const String personaInheritanceDefault = '默认继承';
  static const String personaInheritanceSynced = '继承中';
  static const String personaInheritanceCustom = '已独立';
  static const String personaSyncStatusReady = '已同步';
  static const String personaSyncStatusMissing = '待补充';
  static const String personaSyncSuggestionTitle = '同步资料建议';
  static const String personaSyncSuggestionBody = '你刚刚更新了分身资料，可同步到其它分身以保持资料一致。';
  static const String personaDeleteBlocked = '当前分身暂不可删除';
  static const String personaRetireBlocked = '当前分身暂不可退役';

  /// 内容时间展示（创作时间 / 更新时间）。
  /// 规则：更新时间不晚于创作时间（或相等）只显示创作时间；更晚才显示更新时间。
  static const String contentCreatedAtPrefix = '创作于';
  static const String contentUpdatedAtPrefix = '更新于';
  static const String contentEditedSuffix = '已编辑';

  /// 我的主页统计与子页（关注数用 follow，此处为统计栏标题）
  static const String profileEditLabel = '编辑资料';
  static const String profilePersonasLabel = '分身管理';
  static const String profileUploadAvatar = '上传头像';
  static const String profileUploadCover = '添加封面';
  static const String profileChangeAvatar = '更换头像';
  static const String profileChangeCover = '更换封面';
  static const String profileAvatarNoun = '头像', profileCoverNoun = '封面';
  static const String profileEmptyBioPrompt = '添加一句简介，让同好更快认识你并关注你';
  static const String profileEmptyTagsPrompt = '添加身份标签，让同好更快找到你';

  /// 编辑资料页（与我的主页空态文案保持一致）。
  static const String editProfileMediaSectionHeader = '头像与封面';
  static const String editProfileInfoSectionHeader = '个人资料';
  static const String editProfileCoverLabel = '封面';
  static const String editProfileAvatarLabel = '头像';
  static const String editProfileNicknameLabel = '昵称';
  static const String editProfileNicknamePlaceholder = '填写昵称';
  static const String editProfileGenderLabel = '性别';
  static const String editProfileBirthdayLabel = '生日';
  static const String editProfileRegionLabel = '地区';
  static const String editProfilePhoneLabel = '手机号';
  static const String editProfileQuwoquanIdLabel = '趣我圈号';
  static const String editProfileQrCodeLabel = '我的二维码';
  static const String editProfileBioLabel = '签名';
  static const String editProfileTagsLabel = '标签';
  static const String editProfileOccupationLabel = '职业';
  static const String editProfileInterestsLabel = '兴趣标签';
  static const String editProfileUnsetValue = '未填写';
  static const String editProfileFillCtaValue = '让同好认识你';
  static const String editProfileSelectCtaValue = '帮你找到同好';
  static const String editProfileBindCtaValue = '账号更安全';
  static const String editProfileSystemGeneratingValue = '生成中';
  static const String editProfileNotBoundValue = '未绑定';
  static const String editProfileCopiedToast = '已复制';
  static const String editProfileGenderMale = '男';
  static const String editProfileGenderFemale = '女';
  static const String editProfileGenderUnsetValue = '可填写';
  static const String editProfileGenderUnspecified = '不展示';
  static const String editProfileMediaCamera = '拍照';
  static const String editProfileMediaPhotoLibrary = '从照片中选择';
  static const String editProfileBirthdayTitle = '生日';
  static const String editProfileBirthdayInputPlaceholder = 'YYYY-MM-DD';
  static const String editProfileBirthdayInvalid = '请输入有效生日';
  static const String editProfileRegionTitle = '选择地区';
  static const String editProfileSelectedRegion = '已选地区';
  static const String profileEmptyRegionOptions = '暂无可选地区';
  static const String editProfilePhoneTitle = '手机号';
  static const String editProfilePhoneBoundPrefix = '已绑定手机号';
  static const String editProfilePhoneShowAction = '显示';
  static const String editProfilePhoneBoundHint = '已绑定手机号，可用于登录与账号安全验证。';
  static const String editProfilePhoneOneTapBind = '本机号码一键绑定';
  static const String editProfilePhoneManualBind = '验证码绑定';
  static const String editProfilePhoneInputPlaceholder = '你的手机号';
  static const String editProfileOtpInputPlaceholder = '验证码';
  static const String editProfileSendOtp = '获取验证码';
  static const String editProfileBindNow = '绑定手机号';
  static const String editProfilePhoneOneTapUnavailable = '当前设备暂不可一键绑定';
  static const String editProfilePhoneBindSuccess = '手机号已绑定';
  static const String editProfilePhoneBindFailedTitle = '手机号绑定未完成';
  static const String editProfileQrCardTitle = '我的二维码';
  static const String editProfileQrCardHeading = '添加我为联系人';
  static const String editProfileQrCardHint = '扫一扫，添加我为联系人。';
  static const String editProfileQrScanAction = '扫一扫';
  static const String editProfileQrShareAction = '分享';
  static const String editProfileQrSaveAction = '保存图片';
  static const String editProfileQrSaveFallbackToast = '二维码链接已复制';
  static String profileQrForwardTitle(String displayName) =>
      '${displayName.trim().isNotEmpty ? displayName.trim() : editProfileQrCardTitle} 的二维码';

  /// 应用内统一转发旅程。
  static const String forwardSheetTitle = '转发给';
  static const String forwardMostContacted = '最常联系';
  static const String forwardActionAppContacts = '发送给联系人';
  static const String forwardActionWechatFriend = '发送给微信好友';
  static const String forwardActionWechatMoments = '微信朋友圈';
  static const String forwardSelectChatTitle = '选择聊天';
  static const String forwardRecentForwards = '最近转发';
  static const String forwardRecentChats = '最近聊天';
  static const String forwardContacts = '联系人';
  static const String forwardSendToLabel = '发送给：';
  static const String forwardMessagePlaceholder = '发消息';
  static const String forwardNoRecentChats = '暂无最近聊天';
  static const String forwardNoRecipients = '暂无可转发联系人';
  static const String forwardSendSuccess = '已发送';
  static const String forwardSendFailed = '转发失败，请稍后再试';
  static const String forwardOpeningWechat = '正在打开微信';
  static const String forwardShareSystemFallback = '已打开系统分享，请在系统面板选择目标';
  static const String forwardExternalShareUnavailable = '当前平台暂不支持分享';
  static const String forwardCardUnavailable = '此联系人暂不可转发';
  static const String personaManagementLoadFailedTitle = '分身管理暂不可用';
  static String forwardRecipientGroupMemberCount(int count) => '$count人';
  static const String editProfileSignatureTitle = '个性签名';
  static const String editProfileSignaturePlaceholder = '写一句介绍自己';
  static const String editProfileTagsTitle = '标签';
  static const String editProfileTagsValidationFailedTitle = '标签校验未通过';
  static const String editProfileTagsSummaryEmpty = '未选择';
  static const String editProfileOccupationSection = '职业';
  static const String editProfileInterestSection = '兴趣';
  static const String careerInterestTitle = '职业与兴趣';
  static const String careerInterestOccupationSection = '职业身份';
  static const String careerInterestSelectOccupation = '选择你的职业身份';
  static const String careerInterestMyTagsSection = '我的标签';
  static const String careerInterestMyTagsEmptyHint = '从下方添加几个兴趣，主页和推荐会更贴近你';
  static const String careerInterestAllSection = '全部兴趣';
  static const String careerInterestCategoryAll = '全部';
  static const String careerInterestCategoryTravelPhoto = '旅行摄影';
  static const String careerInterestCategoryCampus = '校园';
  static const String careerInterestCategoryLife = '生活';
  static const String careerInterestCategoryArt = '艺术';
  static const String careerInterestCategoryTech = '科技';
  static const String careerInterestMaxToast = '最多可选择 30 个标签';
  static const String careerInterestLoadingFailed = '加载失败，点击重试';
  static const String careerInterestEmptyCategory = '该分类暂无更多标签';
  static const String careerInterestSaving = '保存中…';
  static const String careerInterestSaved = '已保存';
  static const String careerInterestSaveFailed = '保存失败，请重试';
  static const String careerInterestUnsavedTitle = '修改尚未保存';
  static const String careerInterestUnsavedMessage =
      '离开前可以保存本次职业与兴趣修改，或放弃未保存内容。';
  static const String careerInterestDiscard = '放弃修改';
  static const String careerInterestKeepEditing = '继续编辑';
  static const String careerInterestOccupationPickerTitle = '选择职业身份';
  static const String careerOccupationCategoryProductOps = '产品/运营';
  static const String careerOccupationCategoryEngineering = '研发/技术';
  static const String careerOccupationCategoryDesign = '设计/创意';
  static const String careerOccupationCategoryStudent = '学生';
  static const String careerOccupationCategoryFreelance = '自由职业';
  static const String editProfileSaveAction = '保存';
  static const String editProfileProposalTitle = '资料修改建议';
  static const String editProfileProposalPending = '待确认';
  static const String editProfileProposalConfirmed = '待应用';
  static const String editProfileProposalApplying = '正在安全应用';
  static const String editProfileProposalLoadFailed = '加载失败，点此重试';
  static const String editProfileProposalApprove = '确认并应用';
  static const String editProfileProposalResumeApply = '继续安全应用';
  static const String editProfileProposalReject = '拒绝建议';
  static const String editProfileProposalApplied = '资料建议已应用';
  static const String editProfileProposalRejected = '资料建议已拒绝';
  static const String editProfileProposalChanges = '建议修改内容';
  static const String editProfileProposalEmptyValue = '清空当前内容';
  static const String editProfileCancelAction = '取消';
  static const String editProfileSavedToast = '资料已更新';
  static const String editProfileSaveFailedTitle = '资料保存未完成';
  static const String editProfileDiscardTitle = '放弃修改？';
  static const String editProfileDiscardMessage = '你有尚未保存的改动，离开后将不会保存。';
  static const String editProfileDiscardConfirm = '放弃修改';
  static const String editProfileKeepEditing = '继续编辑';
  static const String profileIntersectionEmptyGuidance =
      '多关注感兴趣的人、圈子和地点，系统会帮你发现更多真实交集';
  static const String profileIntersectionEmptyOther =
      '现在还没有足够清晰的共同线索。共同关注、互动或加入同一圈子后，这里会呈现你们真正相关的连接。';
  static const String profileInteractionEmptyGuidance = '发布记录、点赞和评论，会让更多同好看见你';
  static const String profileBrowseHistory = '浏览历史';
  static const String profileDirectMessage = '私信';
  static const String profileTabCreations = '记录';
  static const String profileTabIntersection = '交集';
  static const String profileTabImpact = '打动';

  /// 主页统计行列名（记录 / 粉丝）。关注复用 [follow]，获赞复用 [circleLikes]。
  static const String profileStatRecords = '记录';
  static const String profileStatFollowers = '粉丝';
  static const String profileStatsSearchFollowingHint = '搜索关注';
  static const String profileStatsMutual = '互关';
  static const String profileStatsFollowedBy = '关注了你';
  static const String profileStatsUnfollow = '取消关注';
  static const String profileStatsDiscoverCircles = '去发现圈子';
  static const String profileStatsMessageUnavailable = '当前关系暂不可直接发消息';
  static const String profileStatsBlockedTitle = '当前无法查看统计详情';
  static const String profileStatsBlockedBody = '该主页的隐私或关系状态限制了这部分信息的展示。';
  static const String profileStatsPrivateTitle = '统计详情暂不可见';
  static const String profileStatsPrivateBody = '该主页仅向可见范围开放统计详情，当前无法展示列表。';
  static const String profileStatsEmptyFansMineTitle = '还没有粉丝';
  static const String profileStatsEmptyFansMineBody =
      '继续完善主页和发布记录后，会有更多同好在这里出现。';
  static const String profileStatsEmptyFansOtherTitle = '公开粉丝为空';
  static const String profileStatsEmptyFansOtherBody = '当前没有可公开展示的粉丝。';
  static const String profileStatsEmptyFollowingMineTitle = '还没有关注任何人';
  static const String profileStatsEmptyFollowingMineBody =
      '去发现页和圈子里逛逛，把感兴趣的人先关注起来。';
  static const String profileStatsEmptyFollowingOtherTitle = '公开关注为空';
  static const String profileStatsEmptyFollowingOtherBody = '当前没有可公开展示的关注对象。';
  static const String profileStatsEmptyCirclesMineTitle = '还没有加入圈子';
  static const String profileStatsEmptyCirclesMineBody =
      '加入几个感兴趣的圈子后，这里会展示你正在参与的社区。';
  static const String profileStatsEmptyCirclesOtherTitle = '公开圈子为空';
  static const String profileStatsEmptyCirclesOtherBody = '当前没有可公开展示的已加入圈子。';
  static const String profileStatsVisibilityContacts = '仅联系人可见';
  static const String profileStatsVisibilitySelfOnly = '仅自己可见';
  static const String profileStatsVisibilityBlocked = '不可见';
  static const String profileStatsCircleMembersUnit = '成员';
  static const String profileStatsCircleCreationsUnit = '创作';

  /// 主页「记录」二级过滤入口（右侧过滤图标弹层标题）。
  static const String profileWorksFilterTitle = '筛选';
  static String profileRecordsTotal(int count) => '共有 $count 条记录';
  static const String profileTabCircles = '圈子';
  static const String profileTabInteraction = '互动';
  static const String profileTabFootprint = myFootprint;
  static const String profileTabLifestyle = '生活';
  static const String lifestyleSubFootprint = '足迹';
  static const String lifestyleSubSoul = '书影音';
  static const String lifestyleSubTaste = '味蕾';
  static const String lifestyleSubPrivate = '爱物';
  static const String creationSubAll = '全部', creationSubMicro = '点滴';
  static const String creationSubImage = '图片', creationSubVideo = '视频';
  static const String creationSubArticle = '文章', creationSubText = '长文';
  static String profileCompletenessPrompt(int percent) => '完善主页（$percent%）';
  static const String profileCompletenessSubtitle = '补全头像、标签、圈子与实体，让连接更容易被看见';
  static const String profileCompletenessAvatar = '头像';
  static const String profileCompletenessTags = '标签';
  static const String profileCompletenessCircles = '圈子';
  static const String profileCompletenessEntities = '实体';
  static const String profileCreationEmptyAllMine = '还没有作品内容';
  static const String profileCreationEmptyAllOther = 'TA还没有作品内容';
  static const String profileCreationEmptyImageMine = '还没有图片内容';
  static const String profileCreationEmptyImageOther = 'TA还没有图片内容';
  static const String profileCreationEmptyVideoMine = '还没有视频内容';
  static const String profileCreationEmptyVideoOther = 'TA还没有视频内容';
  static const String profileCreationEmptyTextMine = '还没有文字内容';
  static const String profileCreationEmptyTextOther = 'TA还没有文字内容';
  static const String interactionSubAll = '全部';
  static const String interactionSubLikes = '点赞';
  static const String interactionSubComments = '评论';
  static const String interactionSubShares = '转发';
  static const String interactionSubViews = '浏览';
  static const String interactionSubVisitors = '访客';
  static const String profileInteractionViewReceivedText = '看过你的主页';
  static const String profileInteractionViewSentText = '你看过这个主页';
  static const String profileInteractionEmptyVisitors = '还没有访客，发布记录后会更容易被同好发现';
  static const String profileInteractionEmptyBrowseHistory =
      '你看过的主页会出现在这里，方便回访';
  static const String profileInteractionDirectionTitle = '互动方向';
  static const String profileInteractionDirectionReceived = '收到的';
  static const String profileInteractionDirectionSent = '我发起的';
  static const String profileInteractionOriginalUnavailable = '原文已失效';
  static const String profileInteractionPreviewUnavailable = '无法预览';
  static const String profileInteractionPreviewLoading = '加载中';
  static const String profileInteractionPreviewLoadFailed = '封面加载失败';
  static const String profileInteractionEmpty = '暂无互动';
  static const String profileInteractionEmptyLikes = '暂无点赞记录';
  static const String profileInteractionEmptyComments = '暂无评论记录';
  static const String profileInteractionEmptyShares = '暂无转发记录';
  static const String profileShareReceivedEmptyTitle = '还没有收到转发';
  static const String profileShareReceivedEmptyDescription =
      '当别人转发你的记录或讨论后，会显示在这里';
  static const String profileShareReceivedEmptyAction = '去发布记录';
  static const String profileShareInitiatedEmptyTitle = '你还没有转发过内容';
  static const String profileShareInitiatedEmptyDescription =
      '看到想分享的记录或讨论，可以转发给更多同好';
  static const String profileShareInitiatedEmptyAction = '去发现内容';
  static const String profileShareReceivedRecordAction = '转发了你的记录';
  static const String profileShareReceivedDiscussionAction = '转发了你的讨论';
  static const String profileShareInitiatedRecordPrefix = '你转发了';
  static const String profileShareInitiatedRecordSuffix = '的记录';
  static const String profileShareInitiatedDiscussionSuffix = '的讨论';
  static const String profileShareDeleted = '原记录已删除';
  static const String profileSharePrivate = '该记录已设为私密';
  static const String profileShareReviewing = '该记录正在审核';
  static const String profileShareAuthorDeactivated = '作者已注销，内容不可查看';
  static const String profileShareImageUnavailable = '图片暂不可加载';
  static const String profileShareVideo = '视频';
  static const String profileShareDiscussionRepliesSuffix = '条回复';
  static const String profileShareToday = '今天';
  static const String profileShareYesterday = '昨天';
  static const String profileShareOlder = '更早';
  static const String profileShareLoading = '正在加载';
  static const String profileShareNoMore = '没有更多了';
  static const String profileShareLoadFailed = '加载失败，点击重试';
  static const String profileShareRefreshFailed = '刷新失败，请稍后重试';
  static const String profileInteractionEmptyViews = '暂无浏览记录';
  // 我的主页·互动（received）小红书式内联动作：
  // 点赞类活动 → 谢谢 / 私信；评论类活动 → 赞 / 回复评论。
  static const String profileInteractionThank = '谢谢';
  static const String profileInteractionThanked = '已感谢';
  static const String profileInteractionLikeComment = '赞';
  static const String profileInteractionCommentLiked = '已赞';
  static const String profileInteractionReplyComment = '回复评论';
  static const String profileInteractionReplyHint = '回复这条评论…';
  static const String profileInteractionReplySubmit = '回复';

  /// 私信入口预置感谢私信内容（私信「谢谢点赞」）。
  static const String profileInteractionThanksLikeMessage = '谢谢点赞🙏';

  /// 内联动作反馈（toast）。
  static const String profileInteractionThanksAcknowledged = '已表达感谢';
  static const String profileInteractionDirectMessageSent = '私信已发送';
  static const String profileInteractionDirectMessageFailed = '私信发送失败，请稍后再试';
  static const String profileInteractionReplySentToast = '回复已发送';
  static const String profileInteractionReplyFailed = '回复发送失败，请稍后再试';
  static const String profileInteractionLikeFailed = '操作失败，请稍后再试';
  static const String profileGreet = '打招呼';
  static const String profileSubAccountManagement = '子账号管理';
  static const String profileSubAccountDeleteTitle = '删除子账号';
  static const String profileSubAccountDeleteConfirmTemplate =
      '确定要删除「%s」吗？此操作不可撤销。';
  static const String contentDeleteSuccess = '内容已删除';
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
  static const String profileSubAccountSemiDescription = '半隐私 · 仅联系人可发现';
  static const String profileSubAccountOpenDescription = '公开 · 可被通讯录发现';
  static const String operationFailed = '操作失败';
  static const String momentPlaceholder = '这一刻的想法...';
  static const String drafts = '草稿箱';
  static const String createExitConfirmTitle = '保存草稿？';
  static const String createExitConfirmDesc = '如果不保存，当前编辑的内容将会丢失。';
  static const String discard = '放弃';
  static const String saveDraft = '保存草稿';
  static const String createActionGallery = '从相册选择';
  static const String createActionGalleryHint = '先挑素材，再决定发成点滴还是作品';
  static const String createActionWrite = '写文字';
  static const String createActionWriteHint = '快速记录当下，也能随时升级成作品';
  static const String createActionContinueFromDraft = '从草稿继续';
  static const String createDraftPickerEmptyTitle = '暂无保存的草稿';
  static const String createDraftPickerPreviewFallback = '继续完善这条内容';
  static const String createActionCapture = '相机';
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
  static const String postPhoto = '发图片', postVideo = '发视频';
  static const String postArticle = '写笔记', publish = '发表';
  static const String publishAction = '发布';
  static const String publishQueued = '已保存，将在网络恢复后自动发布';
  static const String createActionPostPhotoShort = '发布照片';
  static const String createActionPhotoSubtitle = '从相册选照片或拍照';
  static const String createActionPostVideoShort = '发布视频';
  static const String createActionCameraSubtitle = '从相册选视频或拍视频';
  static const String createActionWriteLong = '写文字';
  static const String createActionResumeDraft = '从草稿开始';
  static const String localDraftsTitle = '本地草稿';
  static const String localDraftsDeviceOnlyNotice =
      '草稿仅保存在当前设备，卸载应用后会被删除，请及时发布。';
  static const String localDraftEmptySubtitle = '继续创作后的草稿会出现在这里。';
  static const String localDraftDeleteConfirmTitle = '删除这条草稿？';
  static const String localDraftDeleteConfirmDesc = '删除后将无法恢复。';
  static const String localDraftDeleteAction = '删除草稿';
  static const String localDraftMissingImage = '无图片';
  static const String localDraftMissingVideo = '无视频';
  static const String localDraftUnavailableTitle = '这条草稿暂时无法恢复';
  static const String localDraftMissingImageDesc = '原始图片已不可用，可删除这条草稿或返回。';
  static const String localDraftMissingVideoDesc = '原始视频已不可用，可删除这条草稿或返回。';
  static const String createDraftToolbar = '草稿';
  static const String createDraftSaving = '保存中...';
  static const String createDraftSaved = '已保存';
  static const String createDraftSaveFailed = '保存失败，点按重试';
  static const String createActionAddContactShort = homeObjectActionAddContact;
  static const String createActionCreateGroupShort = '发起群聊';
  static const String createActionCreateCircleShort = createCircle;
  static const String createActionInterestMatchShort = '交集配对';
  static const String createActionInterestMatchSubtitle = '发现同趣的人、圈子与地点';
  static const String createActionPublishGroupTitle = publishAction;
  static const String createActionSocialGroupTitle = profileTabInteraction;
  static const String createPageTitle = '创作';

  /// 沉浸文章顶栏分段：纵向长文编辑态
  static const String createArticleSurfaceLongEdit = '长文编辑';

  /// 沉浸文章第二步：独立长文排版页
  static const String createArticleSurfaceTypography = '排版';

  /// 创作顶栏短标签（与「草稿箱」全局面板入口区分）
  static const String createToolbarDraftShort = '草稿';
  static const String publishSettingsTitle = '发布设置';
  static const String locationLabel = '所在位置';
  static const String locationHidden = '不显示位置';
  static const String remindWhoLabel = '提醒谁看';
  static const String whoCanSeeLabel = '谁可以看';
  static const String visibilityPublic = '公开', visibilityPrivate = '私密';

  /// 发布可见性：仅作者本人（与 [visibilityPrivate]「私密」展示口径区分）
  static const String visibilitySelfOnly = '仅自己可见';
  static const String isPublicLabel = '是否公开';
  static const String attachHomepageTitle = '关联主页';
  static const String attachHomepageNone = '未关联主页';
  static const String attachHomepageClear = '暂不关联主页';
  static const String attachHomepageClearHint = '移除当前关联，按普通公开内容发布';
  static const String attachHomepageSearchHint = '搜索景点、酒店、餐厅、车型';
  static const String attachHomepageSuggest = '找不到？添加一个主页';
  static const String attachHomepageEmpty = '没有找到匹配主页，试试添加一个新主页';
  static const String attachHomepageUnavailable = '主页暂时不可用，请稍后重试';
  static const String addHomepageTitle = '添加主页';
  static const String addHomepageIntroTitle = '添加一个缺失主页';
  static const String addHomepageIntroSubtitle =
      '先选择主页类型，再补充最少必要信息。提交后会进入审核，审核通过后才会出现在搜索和关联中。';
  static const String addHomepageTypeSectionTitle = '主页类型';
  static const String addHomepageBasicInfoSectionTitle = '基础信息';
  static const String addHomepageFutureTypeHint = '校园大学与旅行摄影主页已纳入首批模板。';
  static const String addHomepageNameLabel = '主页名称';
  static const String addHomepageNamePlaceholder = '输入主页名称';
  static const String addHomepageClueLabel = '补充说明';
  static const String addHomepageCityLabel = '城市';
  static const String addHomepageCityPlaceholder = '输入城市';
  static const String addHomepageAddressLabel = '地址';
  static const String addHomepageAddressPlaceholder = '输入地址';
  static const String addHomepageVehicleManufacturerLabel = '厂商';
  static const String addHomepageVehicleManufacturerPlaceholder = '例如 丰田';
  static const String addHomepageVehicleSeriesLabel = '车系 / 型号';
  static const String addHomepageVehicleSeriesPlaceholder = '例如 RAV4';
  static const String addHomepageVehicleTrimLabel = '版本补充';
  static const String addHomepageVehicleTrimPlaceholder = '例如 双擎四驱';
  static const String addHomepageVehicleHint = '车型主页按厂商 + 车系创建，版本信息可作为补充说明提交。';
  static const String addHomepageSubmit = '提交添加';
  static const String addHomepageSubmitted = '已提交添加，等待审核';
  static const String addHomepageSubmitFailed = '提交失败，请稍后重试';
  static const String addHomepageNameRequired = '请先填写主页名称';
  static const String addHomepageVehicleRequired = '请补充厂商和车系 / 型号';
  static const String locationPlaceLandingTitle = '地点';
  static const String locationPlaceLandingTempBadge = '临时地点';
  static const String locationPlaceLandingDescription =
      '这个地点被内容提到过，但还没有建立实体主页。提升为主页后，可以聚合相关内容、关注与交集。';
  static const String locationPlaceLandingPromoteCta = '提升为实体主页';
  static const String locationPlaceLandingMissingAddress = '暂无地址信息';
  static const String homepageTypeSight = '景点';
  static const String homepageTypeSightHint = '景区、公园、展馆';
  static const String homepageTypeHotel = '酒店';
  static const String homepageTypeHotelHint = '酒店、民宿、度假住处';
  static const String homepageTypeRestaurant = '餐厅';
  static const String homepageTypeRestaurantHint = '正餐、小馆、咖啡酒馆';
  static const String homepageTypeVehicle = '车型';
  static const String homepageTypeVehicleHint = '车型、车系、版本';
  static const String homepageTypeUniversity = '大学';
  static const String homepageTypeUniversityHint = '高校、学院、校园公共主页';
  static const String homepageTypeTravelPhoto = '旅行摄影';
  static const String homepageTypeTravelPhotoHint = '目的地、机位、摄影路线';
  static const String addHomepageSightCluePlaceholder = '例如 景区入口或游玩亮点';
  static const String addHomepageHotelCluePlaceholder = '例如 房型特色或所在片区';
  static const String addHomepageRestaurantCluePlaceholder = '例如 菜系或招牌菜';
  static const String addHomepageVehicleCluePlaceholder = '例如 动力形式或主要卖点';
  static const String addHomepageUniversityCluePlaceholder = '例如 院系、校区或校园亮点';
  static const String addHomepageTravelPhotoCluePlaceholder = '例如 机位、路线或最佳拍摄时段';
  static const String unsavedChangesTitle = '放弃本次修改？';
  static const String unsavedChangesMessage = '未提交的内容会丢失。';
  static const String continueEditing = '继续编辑';
  static const String circleWorksCountSuffix = '件作品';

  /// 创作页圈子入口/空态；国际化请用 l10n.selectPublishCirclesLabel / l10n.noCirclesAvailable
  static const String selectPublishCirclesLabel = '发布到圈子';
  static const String circlePublishModeLabel = '圈子内形式';
  static const String circlePublishModeMoment = '点滴';
  static const String circlePublishModeWork = '作品';
  static const String noCirclesAvailable = '加入圈子，发现兴趣相近的人';
  static String startGroupChatMembersAddedCount(int count) => '已添加 $count 位联系人';
  static const String startGroupChatNoMutualContactsInGroup = '该群暂无可添加的互关联系人';
  static const String startGroupChatNoMutualContactsInCircle = '该圈暂无可添加的互关联系人';
  static const String startGroupChatCreatedToast = '群聊已创建';
  static const String startGroupChatCreateIncompleteTitle = '发起群聊未完成';
  static const String startGroupChatAddMembersIncompleteTitle = '添加成员未完成';
  static String startGroupChatSelectedCount(int count) => '已选 $count 人';
  static String startGroupChatActionCount(int count) => '发起群聊（$count）';
  static const String startGroupChatMaxMembersReached = '群成员数量超过上限';
  static const String startGroupChatSyncingMemberState = '正在同步群成员状态…';
  static const String startGroupChatAlreadyInGroup = '已在群中';
  static const String startGroupChatNoMatchedMembers = '暂无匹配成员';
  static const String startGroupChatPickFromGroup = '从群聊中选择';
  static const String startGroupChatPickFromGroupSearch = '搜索群聊';
  static const String startGroupChatGroupPickerTitle = '选择群聊';
  static const String startGroupChatGroupPickerEmpty = '暂无可选的群聊';
  static const String startGroupChatCompanionContextTitle = '正在发起交集结伴';
  static const String startGroupChatCompanionContextSubtitle =
      '已带入共同想去对象与交集来源，提交前仍会经过登录、实名、青少年模式和频控等安全门。';
  static String startGroupChatRemovedMember(String name) => '已移除 $name';
  static String startGroupChatFriendsCount(int count) => '$count 个朋友';
  static String startGroupChatGroupMemberTitle(String name, int count) =>
      '$name（$count 个朋友）';
  static const String locationSearchHint = '搜索地点';
  static const String locationNearbyTitle = '附近位置';
  static const String locationSearchingNearby = '正在搜索附近位置';

  /// 与 integration/location/errors.location_unavailable 保持一致
  static const String locationLoadFailed = '暂时无法获取当前位置，请稍后重试';
  static const String locationSearchTitle = '搜索位置';
  static const String locationSearchEmpty = '未找到相关位置';
  static const String circleSelectTitle = '选择圈子';

  /// 发布设置：私密态下关联主页/圈子的禁用说明
  static const String createPublishHomepagePublicOnlyHint = '仅公开内容可关联';
  static const String createPublishCirclesPublicOnlyHint = '仅公开内容可选';
  static const String createPublishNoCirclesSelected = '未选圈子';
  static const String createPublishConfirmButton = '确认发布';
  static const String createPublishPreviewVideoKind = '视频内容';
  static const String createPublishPreviewTextKind = '文字内容';
  static const String createPublishPreviewOverviewTitle = '内容概览';
  static const String createPublishPreviewExpandFull = '展开全文';
  static const String createPublishNeedContentToast = '先写点内容';
  static const String createPublishPersonaContextNotReady = '当前分身上下文未就绪，请稍后重试';

  /// 媒体区提示与操作
  static const String createMediaHintVideoCover = '轻点视频编辑，可设置封面';
  static const String createMediaHintAddFirst = '先添加图片或视频';
  static const String createMediaOneTapMovieLockedHint = '一键成片作品，仅支持 1 个素材';
  static const String createMediaHintDragReorder = '拖拽排序，轻点编辑';
  static const String createDeleteVideoBeforeImages = '请先删除当前视频，再改为图片';
  static const String createClearImagesBeforeVideo = '请先删空图片，再改为视频';
  static const String createTextEditorVideoNotSupported = '写文字编辑器暂不支持视频';
  static const String createReplaceVideoLabel = '更换视频';
  static const String createEditorRollbackBanner =
      '当前处于编辑器回退模式，保留双编辑器骨架并关闭增强提示。';
  static const String createMediaSingleVideoCaption = '仅 1 个视频';
  static const String createMediaOneTapMovieSingleCaption = '仅 1 个素材';
  static const String createMediaBodySectionLabel = '正文';
  static const String createMediaBodyPlaceholder = '补一段配文，让内容更完整';
  static const String createVideoEditFeaturesHint = '轻点视频编辑，支持裁切、静音和精细选帧';
  static const String createVideoBadgeEditLabel = '视频编辑';
  static const String createVideoKindBadgeLabel = '视频';
  static const String createAddTitleWithOptional = '添加标题（可选）';
  static const String createFieldOptionalTag = '可选';
  static const String createTitleSummaryPlaceholder = '补一个能概括内容的标题';

  /// 图片选择/编辑（微趣、美图、文章共用）
  static const String addCover = '添加封面';
  static const String articleCoverOptionNone = '无图封面';
  static const String articleCoverOptionNoneDesc = '不使用封面图';
  static const String articleCoverOptionOne = '一图封面';
  static const String articleCoverOptionTwo = '二图封面';
  static const String articleCoverOptionThree = '三图封面';
  static const String addImage = '添加图片';
  static const String selectFromGallery = '从相册选择';
  static const String editImage = '编辑图片', imageEditDone = '完成';

  /// 图片编辑器（图四 Snapseed 式）
  static const String imageEditTools = '工具', imageEditStyles = '样式';
  static const String imageEditOriginal = '原图', imageEditVivid = '鲜艳';
  static const String imageEditWarm = '暖色', imageEditCool = '冷色';
  static const String imageEditMono = '黑白', imageEditCameraVivid = '鲜明';
  static const String imageEditCameraWarm = '鲜暖';
  static const String imageEditCameraCool = '鲜冷';
  static const String imageEditPortrait = '人像';
  static const String imageEditLandscape = '风景';
  static const String imageEditStillLife = '静物';
  static const String imageEditVintage = '复古';
  static const String imageEditDrama = '戏剧', imageEditFaded = '褪色';
  static const String imageEditNostalgic = '怀旧';
  static const String imageEditCompare = '对比';

  /// 图片编辑器底栏工具（重建后三段式布局）
  static const String imageEditorRotate = '旋转', imageEditorCrop = '裁剪';
  static const String imageEditorFilter = '滤镜';
  static const String imageEditorBeauty = '美颜';
  static const String imageEditorProTools = '专业工具';
  static const String imageEditorFrame = '相框';
  static const String imageEditorText = '文字';
  static const String imageEditorMosaic = '马赛克';

  /// 图片编辑器记录与操作面板
  static const String imageEditorHistory = '记录';
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
  static const String articleCoverLabel = '封面图', noDraft = '暂无草稿';
  static const String saveDraftConfirm = '保存草稿？';
  static const String saveDraftHint = '如果不保存，当前编辑的内容将会丢失。';
  static const String discardAndExit = '放弃并退出';
  static String attachHomepageSuggestWithQuery(String query) =>
      '添加“$query”这个主页';
  static const String saveAndExit = '保存并退出', draftCount = '草稿箱';
  static const String draftMoment = '点滴草稿', draftPhoto = '图片草稿';
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
  static const String videoUploadHint = '', videoChangeCover = '更换封面';
  static const String videoNoVideo = '暂无视频';
  static const String videoDurationTooLong = '视频时长超过1小时，请重新选择';
  static const String videoEditorTitle = '编辑视频';
  static const String videoEditorPreviewUnavailableTitle = '视频预览暂不可用';
  static const String videoEditorPreviewUnavailableMessage =
      '暂时无法加载视频预览，但仍可返回重新选择素材。';
  static const String videoEditorFramesUnavailableTitle = '时间轴帧暂不可用';
  static const String videoEditorExportFailedTitle = '视频导出未完成';
  static const String videoEditorMuted = '已静音';
  static const String videoEditorKeepSound = '保留原声';
  static const String videoEditorReset = '恢复初始编辑';
  static const String videoEditorPreviewTimeline = '播放头预览';
  static const String videoEditorPreviewTimelineHint = '拖动播放头，边拖边看当前帧';
  static const String videoEditorCurrentTimePrefix = '当前';
  static const String videoEditorTrimSegment = '裁切片段';
  static const String videoEditorDurationSuffix = '时长';
  static const String videoEditorStartPrefix = '开始';
  static const String videoEditorEndPrefix = '结束';
  static const String videoEditorCoverPrefix = '封面';
  static const String videoEditorCoverTool = '封面';
  static const String videoEditorCropTool = '裁剪';
  static const String videoEditorMuteTool = '静音';
  static const String videoEditorVolumeTool = '音量';
  static const String videoEditorCoverTimeline = '封面时间轴';
  static const String videoEditorGenerating = '生成中';
  static const String videoEditorFrameCountSuffix = '帧';
  static const String videoEditorPreviewFramesLoading = '正在缓存更细颗粒度视频帧...';
  static const String videoEditorNoPreviewFrames = '暂无可用预览帧';
  static const String videoEditorFramesLoading = '正在生成视频帧...';
  static const String videoEditorNoFrames = '暂无可选封面帧';
  // 媒体选择器（创作）
  static const String mediaPickerAlbumAll = '全部';
  static const String mediaPickerAlbumAllPhotos = '全部照片';
  static const String mediaPickerAlbumCamera = '相机';
  static const String mediaPickerAlbumRecents = '最近项目';
  static const String mediaPickerCategoryAll = '全部';
  static const String mediaPickerCategoryVideo = '视频';
  static const String mediaPickerCategoryPhoto = '照片';
  static const String mediaPickerCategoryLive = '实况图';
  static const String mediaPickerCategoryFullscreen = '全屏图';
  static const String mediaPickerCameraEntry = '拍照';
  static const String mediaPickerMixedTitle = '照片和视频';
  static const String mediaPickerMixedCameraEntry = '拍摄';
  static const String mediaPickerMixedAlbumEmpty = '暂无照片或视频';
  static const String mediaPickerMixedImageLocked = '已选择图片，清空后可选视频';
  static const String mediaPickerMixedVideoLocked = '已选择视频，清空后可选图片';
  static const String mediaPickerVideoTitle = '全部视频';
  static const String mediaPickerVideoCameraEntry = '拍视频';
  static const String mediaPickerOneTapMovie = '一键成片';
  static const String mediaPickerOneTapMovieOriginal = '使用原片';
  static const String mediaPickerOneTapMovieGentleMotion = '轻动效';
  static const String mediaPickerOneTapMovieBeat = '卡点';
  static const String mediaPickerOneTapMovieScenery = '风景';
  static const String mediaPickerOneTapMovieComposing = '生成中...';
  static const String mediaPickerOneTapMovieUnavailable = '当前设备暂不支持一键成片';
  static const String mediaPickerOneTapMovieFailed = '成片失败，请重试';
  static const String mediaPickerOneTapMovieQueued = '已加入一键成片，请在发布页继续';
  static const String mediaPickerNextStep = '下一步';
  static const String mediaPickerPhotoTitle = '图片选择';
  static const String mediaPickerAlbumSelectionTitle = '选择相册';
  static const String mediaPickerAlbumEmpty = '暂无图片';
  static const String mediaPickerEditImage = '编辑图片';
  static const String mediaPickerComplete = '完成';
  static const String mediaPickerOverLimit = '已达到可选数量上限';
  static const String mediaPickerPermissionDenied = '请允许相册访问权限后再选择媒体';
  static const String mediaPickerImageOnly = '当前入口仅支持选择图片';
  static const String mediaPickerVideoOnly = '当前入口仅支持选择视频';
  static const String desktopPickerChooseFolder = '选择文件夹';
  static const String desktopPickerChangeFolder = '更换文件夹';
  static const String desktopPickerEmptyTitle = '还没有选择图片文件夹';
  static const String desktopPickerEmptyHint = '从本机选择一个文件夹，将自动扫描其中的图片';
  static const String desktopPickerScanning = '正在扫描文件夹…';
  static const String desktopPickerNoImages = '该文件夹及其子目录中没有可用图片';
  static const String desktopPickerUnsupportedTitle = '当前平台暂不支持本地相册';
  static const String desktopPickerUnsupportedHint = '请在支持本地文件系统的桌面端选择图片';
  static const String cameraUnavailableTitle = '相机暂时打不开';
  static const String cameraUnavailable = '相机不可用';
  static const String cameraUnavailableRecovery = '请检查相机权限，或切换到支持相机的设备后再试';
  static const String cameraPermissionRequiredTitle = '需要相机权限';
  static const String cameraPermissionPrimerMessage =
      '拍照或录像需要使用相机。点「继续」后，请在系统弹窗中选择「允许」。';
  static const String cameraPermissionRequired = '请允许相机权限后再拍照';
  static const String cameraPermissionRequiredRecovery =
      '可前往系统设置开启相机权限，或返回继续选择相册图片';
  static const String cameraCaptureNotCompletedTitle = '拍照未完成';
  static const String cameraCaptureFailed = '拍照失败，请重试';
  static const String cameraPhotoMode = '拍照';
  static const String cameraPhotoModeTitle = '拍照模式';
  static const String cameraVideoMode = '拍视频', cameraFlash = '闪光灯';
  static const String cameraFlashAuto = '自动', cameraFlashOff = '关闭';
  static const String cameraFlashOn = '开启', cameraSwitchLens = '翻转';
  static const String cameraFilter = '滤镜';
  static const String cameraRetakePhoto = '重新拍照';
  static const String cameraUsePhoto = '使用照片';
  static const String cameraMotionPhoto = '动图';
  // 视频摄像模式（与拍照共享高保壳，但语义独立）
  static const String cameraVideoModeTitle = '摄像模式';
  static const String cameraVideoLight = '灯光';
  static const String cameraVideoRecord = '录像', cameraVideoStop = '停止';
  static const String cameraVideoRecordTooShort = '录制时间太短';
  static const String cameraVideoCaptureNotCompletedTitle = '录制未完成';
  static const String cameraVideoCaptureFailed = '录制失败，请重试';
  static const String cameraVideoPermissionRequired = '请允许相机权限后再录制';
  static const String cameraVideoPermissionRequiredRecovery =
      '可前往系统设置开启相机权限，或返回继续选择相册视频';
  static const String cameraMicrophonePermissionTitle = '需要麦克风权限';
  static const String cameraMicrophonePermission = '开启麦克风后录制的视频才会有声音';
  static const String cameraMicrophoneContinueMuted = '继续无声录制';
  static const String cameraVideoRetake = '重拍';
  static const String cameraVideoNext = '下一步';
  static const String cameraVideoPreviewUnavailable = '暂时无法播放预览';
  static const String cameraVideoPreviewUnavailableHint =
      '这段视频已保留，建议重拍；也可以继续下一步再尝试编辑';
  static const String cameraVideoDiscardTitle = '放弃这段视频？';
  static const String cameraVideoDiscardMessage = '返回会丢弃当前录制的视频片段';
  static const String cameraVideoDiscardConfirm = '放弃';
  static const String cameraVideoDiscardCancel = '继续录制';

  /// 文章（ArticleEditorCard 1:1）
  static const String articleTitlePlaceholder = '请输入标题';
  static const String shareTemplateMomentTitle = '分享点滴';
  static const String shareTemplateMomentSubtitle = '保留当时的语境与氛围';
  static const String shareTemplateWorkTitle = '分享作品';
  static const String shareTemplateWorkSubtitle = '突出标题、摘要与长期参考价值';
  static String contentLabelForKey(String labelKey) =>
      _contentLabelForKey(labelKey);
}
