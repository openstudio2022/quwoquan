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
  static const String webPcPrimaryProfile = '我的';
  static const String webPcCreateTabVideo = discoveryTabVideo;
  static const String webPcCreateTabGallery = '相册';
  static const String webPcCreateTabText = '文字';
  static const String webPcCreateTabDrafts = '草稿';
  static const String webPcProfileContextTitle = '我的主页';
  static const String webPcSearchHintHome = '搜索兴趣、圈子、作品、用户';
  static const String webPcSearchHintFeatured = '搜索视频书作品、视频、图文';
  static const String webPcSearchHintCreate = '搜索素材、草稿、发布模板';
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
  static const String search = '搜索';
  static const String create = '创建';
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
  static const String authGateTitleComment = '登录后继续评论';
  static const String authGateTitleLike = '登录后继续点赞';
  static const String authGateTitleFollow = '登录后继续关注';
  static const String authGateTitleFollowingFeed = '登录后查看关注';
  static const String authGateTitleShare = '登录后同步分享记录';
  static const String authGateTitlePersona = '登录后管理分身';
  static const String authGateTitleSettingsAccount = '登录后管理账号';
  static const String authGateTitleMediaUpload = '登录后上传素材';
  static const String authGateTitleDeletePost = '登录后删除内容';
  static const String authGateTitleReport = '登录后提交举报';
  static const String authGateTitleJoinCircle = '登录后加入圈子';
  static const String authGateTitleAddContact = '登录后添加联系人';
  static const String authGateTitleCreateCircle = '登录后创建圈子';
  static const String authGateTitleStartCall = '登录后发起通话';
  static const String authGateTitleGeneric = '登录后继续使用';
  // 登录页副标题：表达「登录后获得什么 / 如何继续」，不得与主标题重复。
  static const String authGateSubtitleProfile = '同步你的作品、足迹、互动和分身资料。';
  static const String authGateSubtitleCreate = '保存草稿、发布记录和后续互动通知。';
  static const String authGateSubtitleComment = '评论会沉淀到内容页，并跟随账号同步。';
  static const String authGateSubtitleLike = '登录后可跨设备同步点赞记录。';
  static const String authGateSubtitleFollow = '关注关系会写入账号，后续可在关注流查看。';
  static const String authGateSubtitleFollowingFeed = '汇总你关注的人、圈子和地点的最新动态。';
  static const String authGateSubtitleShare = '同步分享记录，方便后续回看和归因。';
  static const String authGateSubtitlePersona = '管理分身资料，并保持内容身份一致。';
  static const String authGateSubtitleSettingsAccount = '查看登录方式、协议状态和账号安全设置。';
  static const String authGateSubtitleMediaUpload = '上传素材会绑定账号，便于继续编辑和发布。';
  static const String authGateSubtitleDeletePost = '确认账号身份后，才能删除自己的内容。';
  static const String authGateSubtitleReport = '举报将以账号身份提交，便于平台反馈处理进展。';
  static const String authGateSubtitleJoinCircle = '加入后圈子动态和成员关系会同步到账号。';
  static const String authGateSubtitleAddContact = '添加后可在联系人和私信中继续沟通。';
  static const String authGateSubtitleCreateCircle = '圈子资料、成员管理和后续运营会绑定账号。';
  static const String authGateSubtitleStartCall = '登录后将继续刚才的语音或视频通话。';
  static const String authGateSubtitleGeneric = '登录后保存记录，并继续刚才的操作。';
  // 轻提示：触发受限动作时在原页面给出的短提示（先提示，再进入登录页）。
  static const String authGatePromptProfile = '登录后查看我的主页';
  static const String authGatePromptCreate = '登录后即可发布内容';
  static const String authGatePromptComment = '登录后即可评论，评论会按账号发布并沉淀到对象页';
  static const String authGatePromptLike = '登录后即可点赞';
  static const String authGatePromptFollow = '登录后即可关注';
  static const String authGatePromptFollowingFeed = '登录后查看你关注的人、圈子和地点动态';
  static const String authGatePromptShare = '登录后即可同步分享';
  static const String authGatePromptPersona = '登录后即可管理分身';
  static const String authGatePromptSettingsAccount = '登录后即可管理账号';
  static const String authGatePromptMediaUpload = '登录后即可上传素材';
  static const String authGatePromptDeletePost = '登录后即可删除自己的内容';
  static const String authGatePromptReport = '登录后即可提交举报';
  static const String authGatePromptJoinCircle = '登录后即可加入圈子';
  static const String authGatePromptAddContact = '登录后即可添加联系人';
  static const String authGatePromptCreateCircle = '登录后即可创建圈子';
  static const String authGatePromptStartCall = '登录后即可继续发起通话';
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
  static const String myFootprintUnavailableTitle = '我的足迹暂不可用';
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
  static const String startupStillStartingInline = '启动中，马上进入';
  static const String startupRecoveryTitle = '应用暂时无法启动';
  static const String startupRecoveryMessage = '请检查网络或稍后重新打开应用。';
  static const String startupRecoveryRetry = '重新尝试';
  static const String startupRecoverySupportHint = '若问题持续出现，请联系支持并提供诊断标识。';
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
  static const String searchCloudSuggestUnavailable = '网络联想暂时不可用，已继续展示本地结果。';
  static const String searchLocalContactsUnavailable = '本地联系人暂时不可搜索。';
  static const String searchLocalMessagesUnavailable = '本地聊天记录暂时不可搜索。';
  static const String searchXiaoquLoading = '小趣正在整理搜索方向';
  static const String searchNoNetworkReferences = '暂时没有找到可引用的网络结果';
  static const String searchNoAppResults = '没有找到相关应用内结果';
  static const String searchAppResults = '应用内结果';
  static const String searchNoIntersectionResults = '还没有找到和你相关的交集';
  static const String searchRelatedTitle = '相关搜索';
  static const String searchRelatedEmpty = '暂无相关搜索词';
  static const String searchPartialGroupFailed = '部分搜索结果没加载出来，已继续展示其它结果。';
  static const String searchHistoryTitle = '搜索历史';
  static const String searchHistoryDeleteAll = '全部删除';
  static const String searchHistoryDone = '完成';
  static const String searchHistoryExpand = '展开';
  static const String searchHistoryCollapse = '收起';
  static const String searchHistoryClearTitle = '清空搜索历史';
  static const String searchHistoryClearMessage = '将移除全部搜索历史记录，且无法恢复。';
  static const String searchHistoryClearAction = '清空';
  static const String searchHomeGuessTitle = '猜你想搜';
  static const String searchHomeDiscoverCirclesTitle = '发现圈子';
  static const String searchHomeDiscoverLocationsTitle = '发现地点';
  static const String searchAllResults = '搜索全部结果';
  static const String searchBestConnections = '查看最值得连接的结果';
  static const String searchOnlyImages = '只看图片结果';
  static const String searchOnlyVideos = '只看视频结果';
  static const String searchOnlyArticles = '只看长文结果';
  static const String searchScopeContent = '内容';
  static const String searchScopeSocialRelation = '社交关系';
  static const String searchScopeMessages = '聊天';
  static const String searchScopeDiscussions = '讨论';
  static const String searchTargetContacts = '联系人';
  static const String searchTargetDirectChats = '单聊';
  static const String searchTargetGroupChats = '群聊';
  static const String searchContentTypeArticle = '文章';
  static const String searchContentTypeMicro = '微趣';
  static const String searchSuggestionContacts = '联系人';
  static const String searchSuggestionChatRecords = '聊天记录';
  static const String searchSuggestionJoinedCircles = '已加入圈子';
  static const String searchSuggestionFollowedLocations = '已关注地点';
  static const String searchSuggestionPeople = '人';
  static const String searchSuggestionNetwork = '搜索网络结果';
  static const String searchCategoryCircle = '圈子';
  static const String searchCategoryUser = '用户';
  static const String searchUserResultsTitle = '相关用户';
  static const String searchCategoryLocation = '地点';
  static const String searchCategoryImage = '图片';
  static const String searchCategoryVideo = '视频';
  static const String searchCategoryArticle = '长文';
  static const String searchLocationHomepage = '地点主页';
  static const String searchEntityHomepage = '实体主页';
  static const String searchVisitHomepage = '访问主页';
  static const String searchOpenHomepageDescription = '打开主页查看介绍';
  static const String searchOpenRelatedClue = '打开相关线索';
  static const String searchIntersectionLoading = '正在整理与你的交集';
  static const String searchEstablishedConnections = '已形成的连接';
  static const String searchEstablishedConnectionsSubtitle = '基于你的互动、关注和加入';
  static const String searchViewAll = '查看全部';
  static const String searchDiscoverMoreIntersections = '发现更多交集';
  static const String searchRecommendMoreContent = '为你推荐更多相关内容';
  static const String searchFollowedLocation = '已关注地点';
  static const String searchFollowed = '已关注';
  static const String searchXiaoquTab = '小趣';
  static const String searchAllTab = '全部';
  static const String searchIntersectionTab = '交集';
  static const String searchImageTab = '图片';
  static const String searchVideoTab = '视频';
  static const String searchArticleTab = '长文';
  static const String searchXiaoquTabDescription = '理解这个搜索词，并给出下一步方向';
  static const String searchAllTabDescription = '已连接优先，未连接按类别比例发现';
  static const String searchIntersectionTabDescription = '突出最值得连接的结果';
  static const String searchImageTabDescription = '双列浏览图片结果';
  static const String searchVideoTabDescription = '双列浏览视频结果';
  static const String searchArticleTabDescription = '单列阅读长文结果';
  static const String searchEmptySuggestion = '试试缩短关键词、检查错别字，或搜索更宽泛的对象。';
  static const String searchEditQuery = '调整关键词';
  static const String searchResultUnavailableTitle = '这个搜索结果已失效';
  static const String searchXiaoquTrendingSummary = '为你整理了当前热门网络结果';
  static const String searchCircleAggregationSummary =
      '先按圈子讨论分类聚合内容，再把最相关的创作和讨论铺开，方便继续筛选。';
  static const String searchNetworkResults = '网络结果';
  static const String searchOpenRelatedContent = '打开相关内容';
  static const String searchContentResults = '内容结果';
  static const String searchLocalFallback = '本地回退';
  static const String searchOpenRelatedCircle = '打开相关圈子';
  static const String searchDiscussionResults = '讨论结果';
  static const String searchCategoryDiscussion = '讨论';
  static String searchTabResults(String tabLabel) => '$tabLabel结果';
  static String searchDateMonthDay(int month, int day) => '$month月$day日';
  static const String searchDateToday = '今天';
  static const String searchDateYesterday = '昨天';
  static String searchCircleInspirationSubtitle(int count, String detail) =>
      '$count人 · $detail';
  static String searchLocationDiscoverySubtitle(
    String location,
    int ratingCount,
  ) => ratingCount > 0 ? '$location · $ratingCount条评价' : location;
  static String searchNoResultsForQuery(String query) =>
      query.trim().isEmpty ? searchEmptyResult : '没有找到“${query.trim()}”的结果';
  static String searchNoIntersectionForQuery(String query) =>
      query.trim().isEmpty
      ? searchNoIntersectionResults
      : '还没有找到“${query.trim()}”的真实交集';
  static String searchQueryIntersection(String query) => '$query 交集';
  static String searchQueryImages(String query) => '$query 图片';
  static String searchQueryVideos(String query) => '$query 视频';
  static String searchQueryArticles(String query) => '$query 长文';
  static String searchQueryGuide(String query) => '$query 攻略';
  static String searchQueryPhotoSpot(String query) => '$query 拍照机位';
  static String searchQueryCircles(String query) => '$query 圈子';
  static String searchRecommendForQuery(String query) => '为你推荐更多与“$query”相关的内容';
  static String searchFollowerCount(String count) => '$count关注';
  static String searchContentCount(String count) => '$count内容';
  static String searchTenThousands(double value) =>
      '${value.toStringAsFixed(1)}万';
  static String searchXiaoquQuerySummary(String query) => '正在为你整理“$query”的网络结果';
  static String searchCitationCount(int count) => '已整理 $count 条可继续查看的引用线索';
  static String searchSectionResultSummary(
    String title,
    int count,
    String description,
  ) => '$title · $count 条结果${description.isEmpty ? '' : ' · $description'}';
  static String searchMemberCount(int count) => '$count 人';
  static String searchPostCount(int count) => '$count 篇内容';
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
  static const String report = '举报';
  static const String moreActionsTitle = '更多操作';
  static const String contentFilterTitle = '内容过滤';
  static const String readingSettingsTitle = '阅读设置';
  static const String allWorks = '全部作品';
  static const String lightMode = '浅色模式';
  static const String darkMode = '深色模式';
  static const String viewOriginal = '查看原图';
  static const String notInterestedDescription = '减少类似内容推荐';
  static const String undo = '撤销';
  static const String notInterestedUndone = '已撤销不感兴趣';
  static const String blockAuthor = '拉黑作者';
  static const String blockAuthorDescription = '不再看到该作者内容或收到其消息';
  static const String blockKeywords = '屏蔽关键词';
  static const String blockKeywordsDescription = '选择并管理不想看到的词';
  static String blockKeywordConfirmLabel(String keyword) => '屏蔽“$keyword”';
  static String blockKeywordConfirmMessage(String keyword) =>
      '确认后将减少包含“$keyword”的内容，可在设置中随时移除。';
  static const String reportDescription = '选择原因并提交平台审核';
  static const String profileBlockUser = '拉黑';
  static const String profileBlockConfirmTitle = '确认拉黑该用户？';
  static const String profileBlockConfirmMessage = '拉黑后将不再看到对方内容，也不会收到其消息。';
  static const String profileBlockSuccess = '已拉黑该用户';
  static const String profileMoreOptionsTitle = '更多操作';
  static const String followingSubjectTypeUser = '用户';
  static const String followingSubjectTypeCircle = '圈子';
  static const String followingSubjectTypeObject = '对象';
  static const String personaCreateErrorTitle = '创建分身未完成';
  static const String personaCreateErrorMessage = '创建分身失败，请稍后重试。';
  static const String personaEditErrorTitle = '分身编辑未完成';
  static const String personaEditErrorMessage = '分身信息保存失败，请稍后重试。';
  static const String personaRetireErrorTitle = '退役分身未完成';
  static const String personaRetireErrorMessage = '退役分身失败，请稍后重试。';
  static const String personaSyncErrorTitle = '同步建议未完成';
  static const String personaSyncErrorMessage = '应用同步建议失败，请稍后重试。';
  static const String settingsBlockedUsers = '拉黑用户管理';
  static const String settingsBlockedKeywords = '屏蔽关键词管理';
  static const String blockedKeywordsTitle = '屏蔽关键词';
  static const String blockedKeywordsEmptyTitle = '没有屏蔽的关键词';
  static const String blockedKeywordsEmptySubtitle = '你屏蔽的关键词会显示在这里，可随时移除。';
  static const String blockedKeywordsAdd = '添加关键词';
  static const String blockedKeywordsRemove = '移除';
  static const String blockedKeywordsRemoveConfirmTitle = '移除这个屏蔽关键词？';
  static const String blockedKeywordsRemoveConfirmMessage =
      '移除后，相关内容可能重新出现在推荐中。';
  static const String blockedKeywordsRemoveSuccess = '已移除屏蔽关键词';
  static const String blockedKeywordsAddTitle = '屏蔽关键词';
  static const String blockedKeywordsAddHint = '输入不想看到的关键词';
  static const String blockedKeywordsAddSuccess = '已添加屏蔽关键词';
  static const String blockedKeywordsLoginTitle = '登录后管理屏蔽关键词';
  static const String blockedKeywordsLoginSubtitle = '屏蔽关键词仅对当前账号生效。';
  static const String myReportsSettingsTitle = '我的举报';
  static const String myReportsTitle = '举报进度';
  static const String myReportsEmptyTitle = '还没有举报记录';
  static const String myReportsEmptySubtitle = '你提交的举报及处理进度会显示在这里。';
  static const String myReportsLoginTitle = '登录后查看举报进度';
  static const String myReportsLoginSubtitle = '举报记录仅对当前账号可见。';
  static const String reportStatusPending = '已提交';
  static const String reportStatusReviewing = '审核中';
  static const String reportStatusResolved = '已处理';
  static const String reportStatusDismissed = '未发现违规';
  static const String reportReasonViolence = '暴力危险';
  static const String reportReasonCopyright = '侵犯版权';
  static const String reportSubmittedViewProgress = '举报已提交，可在“我的举报”查看进度';
  static const String reportTargetPost = '作品';
  static const String reportTargetComment = '评论';
  static const String reportTargetUser = '用户';
  static const String reportTargetCircle = '圈子';
  static const String reportTargetMessage = '消息';
  static const String blockedUsersTitle = '拉黑用户';
  static const String blockedUsersEmptyTitle = '没有拉黑的用户';
  static const String blockedUsersEmptySubtitle = '你拉黑的用户会显示在这里，可随时解除拉黑。';
  static const String blockedUsersUnblock = '解除拉黑';
  static const String blockedUsersUnblockConfirmTitle = '解除拉黑该用户？';
  static const String blockedUsersUnblockConfirmMessage = '解除后不会自动恢复此前的关注关系。';
  static const String blockedUsersUnblockSuccess = '已解除拉黑';
  static const String blockedUsersLoginTitle = '登录后管理拉黑用户';
  static const String blockedUsersLoginSubtitle = '拉黑列表仅对当前账号可见。';
  static const String loadMore = '加载更多';
  static const String authGateTitleBlockUser = '登录后管理拉黑关系';
  static const String authGateSubtitleBlockUser = '拉黑后可在设置中查看并解除。';
  static const String authGatePromptBlockUser = '登录后即可拉黑或解除拉黑用户';
  static const String authGateTitleHomepageWrite = '登录后共建主页';
  static const String authGateSubtitleHomepageWrite = '推荐主页、认领与状态报告需要账号身份。';
  static const String authGatePromptHomepageWrite = '登录后即可推荐或认领主页';
  static const String addContactRecentDiscoveryTitle = '最近一次通讯录匹配';
  static const String addContactRecentDiscoveryDismiss = '关闭结果';
  static const String addContactRecentDiscoveryDismissed = '已关闭匹配结果';
  static const String profileReportReasonTitle = '选择举报原因';
  static const String profileReportReasonSpam = '垃圾营销';
  static const String profileReportReasonMisinformation = '不实信息';
  static const String profileReportReasonHarassment = '骚扰辱骂';
  static const String profileReportReasonPornography = '色情低俗';
  static const String profileReportReasonOther = '其他';
  // 「打动」摘要模块（他人 / 我的双视角）：§18.7.1 前台由「影响力」收敛为「打动的人」列表视角（机器名 impact 字段不变）。
  static const String profileImpactTitleMine = '我打动的人';
  static const String profileImpactUnavailableTitle = '我打动的人暂不可用';
  // §24.8 他人主页统一「TA打动的人」，与「我打动的人」对称。
  static const String profileImpactTitleOther = 'TA打动的人';
  static const String profileImpactSubtitleMine = '我的内容真实帮到了谁';
  static const String profileImpactSubtitleOther = 'TA的内容真实帮到了谁';
  static const String profileImpactEmptyMine = profileInteractionEmptyGuidance;
  static const String profileImpactEmptyOther = 'TA 打动的人还在形成中，更多连接与带动会展示在这里';
  static const String profileShareHomepage = '分享主页';
  static const String notInterested = '不感兴趣';
  static const String shareTargetCircle = '圈子';
  static const String shareSelectCircleTitle = '选择圈子';
  static const String shareNoCircles = '还没有可分享的圈子';
  static const String shareCircleConfirmMessage = '内容会作为转发记录出现在该圈子中。';
  static const String shareCircleSuccess = '已分享到圈子';
  static const String shareCircleFailedTitle = '转发未完成';
  static String shareCircleConfirmTitle(String circleName) =>
      '转发到“$circleName”？';
  static const String shareCircleVisibilityNotice = '圈内可见内容将生成受控链接';
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
  static const String commentRelationFollowingBadge = '你关注的';
  static const String commentRelationFriendBadge = '互关好友';
  static const String commentSortHot = '热门';
  static const String commentSortLatest = '最新';
  static const String commentCopyAction = '复制';
  static const String commentDeleteAction = '删除';
  static const String commentMoreActions = '更多评论操作';
  static const String commentCopiedToast = '已复制';
  static const String commentReportAction = '举报';
  static const String commentIpLocationPrefix = 'IP·';
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
  static const String commentMentionPickerTitle = '选择要提及的人';
  static const String commentMentionPickerEmpty = '暂时没有可提及的人';
  static const String commentMentionPickerRetry = '重新加载';
  static const String commentDeleteConfirmTitle = '删除这条评论？';
  static const String commentDeleteConfirmMessage = '删除后无法恢复，相关回复仍会保留上下文占位。';
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
  // Work Browser 视频集进度（caption header：标题与时间轴上方）
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
  static const String homepageShareAction = '分享主页';
  static const String homepageShareUnavailable = '该主页暂不可分享';
  static const String homepageWishlistAction = '想去';
  static const String homepageWishlistedAction = '已想去';
  static const String homepageMaintainAction = '维护主页';
  static const String homepageMaintenanceSave = '保存主页信息';
  static const String homepageMaintenanceClaimRequired = '需先完成认领';
  static const String homepageMaintenanceOwnedDescription =
      '你可以维护标题、简介、位置与标签；用户记录和评价不会被改写。';
  static const String homepageMaintenanceUnavailableTitle = '当前账号不能维护此主页';
  static const String homepageMaintenanceUnavailableMessage =
      '只有已通过认领审核的主页所有者可以修改基础信息。';
  static const String homepageMaintenanceSafeReturn = '返回主页';
  static const String homepageMaintenanceNameLabel = '主页名称';
  static const String homepageMaintenanceNamePlaceholder = '填写主页名称';
  static const String homepageMaintenanceSubtitleLabel = '一句话简介';
  static const String homepageMaintenanceSubtitlePlaceholder = '用一句话介绍这里';
  static const String homepageMaintenanceCityLabel = '城市';
  static const String homepageMaintenanceCityPlaceholder = '填写所在城市';
  static const String homepageMaintenanceAddressLabel = '地址';
  static const String homepageMaintenanceAddressPlaceholder = '填写详细地址';
  static const String homepageMaintenanceTagsLabel = '分类标签';
  static const String homepageMaintenanceTagsPlaceholder =
      '用空格分隔，例如 景点 城市地标 赏景';
  static const String homepageMaintenanceNameRequired = '请填写主页名称';
  static const String homepageMaintenanceUpdated = '主页信息已更新';
  static const String homepageFormOverviewSection = '主页状态';
  static const String homepageFormDetailsSection = '基础信息';
  static const String homepageClaimAction = '认领主页';
  static const String homepageClaimPendingAction = '认领审核中';
  static const String homepageClaimAlreadyClaimed = '该主页已被认领';
  static const String homepageClaimHomepageOffline = '主页已下线';
  static const String homepageClaimSubmit = '提交认领申请';
  static const String homepageClaimHomepageFallback = '主页';
  static const String homepageClaimOfflineDescription =
      '该主页已下线，仅保留记录内容，当前不可继续认领。';
  static const String homepageClaimClaimedDescription =
      '该主页已被认领，如信息有误可通过状态上报反馈。';
  static const String homepageClaimReviewDescription =
      '提交后会进入审核，审核通过后即可维护主页基本信息。';
  static const String homepageClaimTier = '认领等级';
  static const String homepageClaimTierBasic = '基础';
  static const String homepageClaimTierVerified = '认证';
  static const String homepageClaimContactPhone = '联系电话';
  static const String homepageClaimContactPhoneHint = '用于审核联系';
  static const String homepageClaimBusinessLicense = '营业执照材料链接';
  static const String homepageClaimIdentityCardFront = '身份证正面材料链接';
  static const String homepageClaimIdentityCardBack = '身份证反面材料链接';
  static const String homepageClaimOptionalMaterialHint = '可选，上传后填入链接';
  static const String homepageClaimNote = '补充说明';
  static const String homepageClaimNoteHint = '说明你与该主页的关系';
  static const String homepageClaimPhoneRequired = '请填写联系电话';
  static const String homepageClaimSubmitted = '认领申请已提交';
  static const String homepageClaimMaterialsSection = '认领信息';
  static const String homepageStatusReportAction = '状态上报';
  static const String homepageStatusReportSubmit = '提交状态上报';
  static const String homepageStatusReportAlreadyOffline = '主页已下线';
  static const String homepageStatusReportOfflineDescription =
      '该主页已经下线，过往记录会继续保留供浏览。';
  static const String homepageStatusReportDescription =
      '如果主页信息失效、重复或长期停用，可以发起状态上报。';
  static const String homepageStatusReportReasonSection = '状态原因';
  static const String homepageStatusReportSelectReason = '选择原因';
  static const String homepageStatusReportReasonOffline = '已停业 / 已关闭';
  static const String homepageStatusReportReasonIncorrectInfo = '信息不准确';
  static const String homepageStatusReportReasonDuplicate = '重复主页';
  static const String homepageStatusReportReasonInactive = '长期失效';
  static const String homepageStatusReportDescriptionLabel = '补充说明';
  static const String homepageStatusReportDescriptionPlaceholder =
      '补充当前状态，例如已停业、地址变更或重复来源';
  static const String homepageStatusReportReasonRequired = '请选择状态原因';
  static const String homepageStatusReportSubmitted = '状态上报已提交';
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
  static const String homepageReviewSectionTitle = '真实评价';
  static const String homepageReviewWriteAction = '写评价';
  static const String homepageReviewEditAction = '编辑评价';
  static const String homepageReviewDeleteAction = '删除评价';
  static const String homepageReviewMineLabel = '我的评价';
  static const String homepageReviewSheetTitle = '评价这里';
  static const String homepageReviewSheetEditTitle = '编辑我的评价';
  static const String homepageReviewRatingLabel = '总体评分';
  static const String homepageReviewBodyPlaceholder = '分享你的真实体验（可选）';
  static const String homepageReviewTagsLabel = '亮点标签（可选）';
  static const String homepageReviewSubmitAction = '发布评价';
  static const String homepageReviewUpdateAction = '保存修改';
  static const String homepageReviewSubmitted = '评价已发布';
  static const String homepageReviewUpdated = '评价已更新';
  static const String homepageReviewDeleted = '评价已删除';
  static const String homepageReviewEmptyTitle = '还没有评价';
  static const String homepageReviewEmptyDescription = '来过这里的人留下的真实评价会展示在这里。';
  static const String homepageReviewDeleteConfirmTitle = '删除这条评价？';
  static const String homepageReviewDeleteConfirmMessage = '删除后可以重新发布新的评价。';
  static const String homepageReviewRatingRequired = '请先选择评分';
  static const String homepageReviewAnonymousAuthor = '趣友';
  static const String homepageRatingPending = '待积累口碑';
  static const String homepageRatingMetric = '评分';
  static const String homepageReviewMetric = '口碑';
  static const String homepageStatusMetric = '状态';
  static const String homepageRatingUnavailable = '--';
  static String homepageRatingScore(String score) => '$score 分';
  static String homepageRatingCount(int count) => '$count 条评分';
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
  static const String objectIntroNavigationTitle = '认识';
  static String objectIntroTitle(String objectName) => '认识$objectName';
  static const String objectIntroRelatedObjectsTitle = '相关地点和事物';
  static String objectIntroDiscussionCount(int count) => '$count 人讨论';
  static const String objectIntroViewHomepage = '查看主页';
  static const String objectIntroViewCircle = '查看圈子';
  static String objectIntroContinueTitle(String objectName) =>
      '继续了解 $objectName';
  static const String objectIntroReturnRecord = '看记录';
  static const String objectIntroReturnDiscussion = '看讨论';
  static const String objectIntroReturnCircles = '找相关圈子';
  static const String objectIntroEmptyTitle = '介绍正在整理中';
  static const String objectIntroEmptyMessage = '先回到主页查看相关内容和讨论。';
  static const String objectIntroBackToHomepage = '回到主页';
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
  static const String settingsPermissionLayerSection = '系统权限';
  static const String settingsContactsPermission = '联系人权限';
  static const String settingsPermissionUnavailable = '当前设备不可用';
  // 设置中枢：通知与提醒 / 通话与铃声（UserSettings 对象命令区块）。
  static const String settingsNotificationSection = '通知与提醒';
  static const String settingsEnablePush = '推送通知';
  static const String settingsEnablePushSubtitle = '互动、私信与关注动态的推送提醒';
  static const String settingsEnableMarketing = '活动与推荐通知';
  static const String settingsEnableMarketingSubtitle = '精选内容与活动推荐（可随时关闭）';
  static const String settingsCallSection = '通话与铃声';
  static const String settingsCallRingtone = '来电铃声';
  static const String settingsCallRingtoneDefault = '默认铃声';
  static const String settingsAllowCallerRingtoneOverride = '允许好友专属铃声';
  static const String settingsAllowCallerRingtoneOverrideSubtitle =
      '来电时使用发起方配置的专属铃声';
  static const String settingsEnableCallVibration = '来电振动';
  static const String settingsEnableGroupCallRing = '群通话响铃';
  static const String settingsEnableGroupCallRingSubtitle = '群语音/视频邀请按来电方式响铃';
  static const String settingsPrivacyPreferences = '隐私设置';
  static const String settingsAllowStrangerMessage = '允许陌生人私信';
  static const String settingsAssistantEnabled = '启用智能助手';
  static const String settingsProfileVisibility = '主页可见范围';
  static const String settingsProfileVisibilityPublic = '公开';
  static const String settingsProfileVisibilityPrivate = '仅自己';
  static const String settingsCallRingtoneClassic = '经典铃声';
  static const String settingsCallRingtoneSoft = '轻柔铃声';
  static const String settingsAccountSecurity = '账号安全';
  static const String settingsCredentialSection = '登录凭证';
  static const String settingsCredentialPhone = '手机号';
  static const String settingsCredentialCarrierPhone = '本机号码';
  static const String settingsCredentialBound = '已绑定';
  static const String settingsCredentialUnbind = '解除绑定';
  static const String settingsCredentialBindPhone = '绑定手机号';
  static const String settingsCredentialEmpty = '暂未绑定可管理的登录凭证';
  static const String settingsCredentialUnbindConfirmTitle = '解除登录凭证';
  static const String settingsCredentialUnbindConfirmMessage =
      '解除后将不能再用该方式登录；最后一个凭证受服务端保护，不允许解除。';
  static const String settingsCloseAccountSection = '注销';
  static const String settingsCloseAccountEntry = '注销账号';
  static const String settingsCloseAccountConfirmTitle = '确认注销账号';
  static const String settingsCloseAccountConfirmMessage =
      '注销后账号立即进入不可恢复的注销状态：所有登录方式与会话立即失效，'
      '分身、关注与联系人关系不再对外可见，你发布的内容将按数据删除策略在 30 天内删除或匿名化；'
      '法律要求保留的记录除外。此操作无法撤销。';
  static const String settingsCloseAccountConfirmAction = '注销账号';
  static const String settingsCloseAccountDoneToast = '账号已注销';
  static const String settingsCloseAccountFailedToast = '注销失败，请重试';
  static const String settingsSectionLoadFailed = '设置加载失败，请下拉重试';
  static const String settingsUpdateFailedToast = '设置更新失败，请重试';
  static const String settingsDarkMode = '深色模式';
  static const String settingsDarkModeOff = '关闭';
  static const String settingsDarkModeOn = '打开';
  static const String settingsDarkModeSystem = '跟随系统';
  static const String settingsDarkModeSystemDescription =
      '开启后，应用内夜间模式状态和系统保持一致';
  static const String settingsDarkModeManualSection = '手动选择';
  static const String settingsDarkModeLightOption = '浅色模式';
  static const String settingsDarkModeDarkOption = '深色模式';
  static const String settingsFontSizeSection = '字号';
  static const String settingsFontSizeXs = '特小';
  static const String settingsFontSizeSm = '较小';
  static const String settingsFontSizeMd = '标准';
  static const String settingsFontSizeLg = '较大';
  static const String settingsFontSizeXl = '特大';
  static const String settingsSyncFailed = '设置同步失败';
  static const String settingsRetrySync = '重试同步';
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
  static const String circleChatEntryTitle = '圈子讨论';
  static const String circleChatEntrySubtitle = '最近消息与未读会话统一在趣信中查看';
  static const String circleInviteMembers = '邀请成员';
  static const String circleApprovalTitle = '加入审批';
  static const String circleApprovalEmpty = '暂无待审批的加入申请';
  static const String circleApprovalApproveAction = '通过';
  static const String circleApprovalRejectAction = '拒绝';
  static const String circleApprovalApproved = '已通过加入申请';
  static const String circleApprovalRejected = '已拒绝加入申请';
  static const String circlePostManagementTitle = '管理圈内创作';
  static const String circlePostPinnedBadge = '置顶';
  static const String circlePostFeaturedBadge = '精华';
  static const String circlePostPinAction = '设为置顶';
  static const String circlePostUnpinAction = '取消置顶';
  static const String circlePostFeatureAction = '设为精华';
  static const String circlePostUnfeatureAction = '取消精华';
  static const String circlePostRemoveAction = '移出圈子';
  static const String circlePostRemoveConfirmTitle = '确认移出这条创作？';
  static const String circlePostRemoveConfirmMessage =
      '移出后该创作不再出现在本圈，原始创作内容不会被删除。';
  static const String circlePostPinUpdated = '置顶状态已更新';
  static const String circlePostFeatureUpdated = '精华状态已更新';
  static const String circlePostRemoved = '创作已移出圈子';
  static String circleInviteShareText(String circleName) =>
      '邀请你加入圈子「$circleName」';
  static String circleShareSubject(String circleName) => '圈子「$circleName」';
  static const String circleStorageSection = '圈子文件';
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
  static const String circleRulesLabel = '圈规';
  static const String circleRulesPlaceholder = '说明允许发布的内容、互动边界和违规处理方式';
  static const String circleWelcomeMessageLabel = '新成员欢迎语';
  static const String circleWelcomeMessagePlaceholder =
      '成员加入成功后展示，例如先读圈规、参与自我介绍或发布第一条作品';
  static const String circleRulesTitle = '圈规与共识';
  static const String circleWelcomeTitle = '欢迎加入';
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
  static const String callScreenShareConnecting = '正在接收共享画面…';
  static const String callShareScreen = '共享屏幕';
  static const String callStopScreenSharing = '停止共享';
  static const String callLockControls = '锁定控制';
  static const String callUnlockControls = '解锁控制';
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
  static const String callEntryUnavailableTitle = '暂时无法发起通话';
  static const String callContextUnavailable = '当前页面没有可用的讨论成员上下文';
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
  static const String callRedial = '回拨';
  static const String callInviteParticipants = '邀请参与者';
  static const String callSearchContacts = '搜索联系人';
  static const String callNoContacts = '暂无联系人';
  static const String callNoMatchingContacts = '未找到匹配的联系人';
  static const String callNoSwitchableConversation = '暂无可切换讨论';
  static const String callParticipants = '参与者';
  static const String callInviteMore = '邀请更多';
  static const String callInitiator = '发起人';
  static const String callMuted = '已静音';
  static const String callCameraOff = '关闭摄像头';
  static const String callCameraOn = '打开摄像头';
  static const String callEnableVideo = '开启视频';
  static const String callAudioOutput = '音频输出';
  static const String callAudioEarpiece = '听筒';
  static const String callAudioSpeaker = '扬声器';
  static String callConfirmSelected(int count) => '确定 ($count)';
  static String callSelectedCount(int count) => '已选 $count';
  static String callParticipantLimit(int count) => '最多 $count 人';
  static String callAdditionalParticipants(int count) => '+$count';
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
  static const String circleSubmitPost = '向圈子投稿';
  static const String addContact = '添加';
  static const String searchCircleFallback = '圈子';
  static const String searchFollowedPlaceFallback = '已关注地点';
  static const String searchFollowingFallback = '已关注';
  static const String clearSearchHistoryTitle = '清空搜索历史';
  static const String clearSearchHistoryMessage = '将移除全部搜索历史记录，且无法恢复。';
  static const String clearSearchHistoryAction = '清空';
  static const String addContactSheetTitle = '添加联系人';
  static const String noAddableContacts = '暂无可添加联系人';
  static const String globalSearchTitle = '搜索';
  static const String createActionCamera = '从摄像';
  static const String createActionTextShort = '写点字';
  static const String createActionContactHint = '找到新联系，发起对话';
  static const String relatedMutualFollow = '互相关注';
  static const String searchCircleHint = '搜索圈子';

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
  static const String permissionContactsLabel = '通讯录';
  static const String permissionContactsPrimerTitle = '需要通讯录权限';
  static const String permissionContactsPrimerMessage =
      '发现已注册联系人需要访问通讯录。点「继续」后，请在系统弹窗中选择「允许」。';
  static const String permissionContactsOpenSettings = '请在 设置 → 趣我圈 → 通讯录中开启权限';
  static const String permissionContactsDenied = '未获得通讯录权限';

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
  static const String personaInactive = '未激活';
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
  static const String personaRetireBlocked = '当前分身暂不可退役';
  static const String personaRetirePrimaryBlocked = '主分身不能退役';
  static const String personaRetireLastBlocked = '至少需要保留一个可用分身';
  static const String personaRetireActiveBlocked = '请先切换到其他分身后再退役';
  static const String personaRetireAlreadyBlocked = '该分身已退役';
  static const String personaRetireConfirmTemplate =
      '退役「%s」后，该分身将不能再使用，历史记录会继续保留。';
  static const String personaEditTitle = '编辑分身';
  static const String personaFormBasicSection = '基本信息';
  static const String personaFormContactSection = '联系方式';
  static const String personaFormVisibilitySection = '可见范围';
  static const String personaFormPurposePlaceholder = '用途备注（可选）';
  static const String personaFormNameRequiredHint = '请输入分身名称';

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
  static const String personaManagementLoadFailedTitle = '分身管理暂不可用';
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
  static const String careerInterestInvalidTagToast = '部分标签已失效，请重新选择';
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
  static const String editProfileProposalPrivateField = '私密资料';
  static const String editProfileProposalIsolationField = '资料隔离级别';
  static const String editProfileProposalPurposeField = '用途说明';
  static const String editProfileProposalSourceAssistant = '来自私助的建议';
  static const String editProfileProposalSourceExternal = '来自已授权外部服务的建议';
  static const String editProfileProposalSourcePersona = '来自当前身份的建议';
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
  static const String profileGreetComposerTitle = '发送打招呼';
  static const String profileGreetComposerPlaceholder = '说点什么打个招呼吧（可留空）';
  static const String profileGreetSend = '发送';
  static const String profileGreetingPendingHint = '已发送过打招呼，等待对方回复';
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
  static const String publishResultSuccessTitle = '发布成功';
  static const String publishResultSuccessDescription = '作品已发布，正在同步到首页和个人主页';
  static const String publishResultQueuedTitle = '正在处理并发布';
  static const String publishResultQueuedDescription = '媒体处理完成后会自动发布，你可以先返回首页';
  static const String publishResultPendingReviewTitle = '已提交审核';
  static const String publishResultPendingReviewDescription =
      '内容尚未公开，审核结果会在发布任务中更新';
  static const String publishResultViewWork = '查看作品';
  static const String publishResultViewTasks = '查看发布任务';
  static const String publishResultDone = '完成';
  static const String publishTasksTitle = '发布任务';
  static const String publishTaskPendingReviewStatus = '审核中';
  static const String publishTaskRejectedStatus = '未通过审核';
  static const String publishTaskSubmittingStatus = '正在提交';
  static const String publishTaskRetryWaitingStatus = '等待重试';
  static const String publishTaskBlockedStatus = '需要处理';
  static const String publishTaskFinalizingStatus = '正在完成分发';
  static const String publishTaskPendingReviewDescription = '内容尚未公开，可随时刷新审核结果';
  static const String publishTaskRejectedDescription = '草稿仍保留，修改后可重新发布';
  static const String publishTaskRetryWaitingDescription = '网络或服务恢复后会自动重试';
  static const String publishTaskPersonaChangedDescription = '请切换回原发布身份后重试';
  static const String publishTaskInvalidReceiptDescription = '发布状态异常，草稿已安全保留';
  static const String publishTaskBlockedDescription = '自动处理已暂停，请检查后重试';
  static const String publishTaskFinalizingDescription = '内容已公开，正在完成草稿清理与圈子分发';
  static const String publishTaskUntitled = '未命名内容';
  static const String publishTaskRefresh = '刷新状态';
  static const String publishTaskRetry = '重试';
  static const String publishTaskContinueEditing = '继续编辑';
  static const String publishTaskRemove = '移除任务';
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
  static const String attachHomepageCurrentSection = '当前关联';
  static const String attachHomepageResultsSection = '搜索结果';
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
  static const String addHomepageSubmitFailedTitle = '建议主页未完成';
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
  static const String homepageTypePoi = '地点';
  static const String homepageTypeAuthor = '作者';
  static const String homepageTypeCircle = '圈子';
  static const String homepageStatusCandidate = '待发布';
  static const String homepageStatusOffline = '已下线';
  static const String homepageStatusPublished = '已发布';
  static const String homepageStatusUnknown = '状态待确认';
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
  static const String imageEditorProTools = '专业工具';
  static const String imageEditorBeauty = '美颜';
  static const String imageEditorFrame = '边框';
  static const String imageEditorText = '文字';
  static const String imageEditorMosaic = '马赛克';
  static const String imageEditorDiscardTitle = '放弃编辑？';
  static const String imageEditorDiscardMessage = '当前修改尚未保存，放弃后无法恢复';
  static const String imageEditorDiscardConfirm = '放弃修改';
  static const String imageEditorUndo = '撤销';
  static const String imageEditorRedo = '重做';

  /// 图片编辑器记录与操作面板
  static const String imageEditorHistory = '记录';
  static const String imageEditorHistoryRevert = '回退到此步之前';

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

  /// 滤镜分类（面板顶部分类）
  static const String imageEditorFilterRecommended = '推荐';
  static const String imageEditorFilterFrequent = '常用';
  static const String imageEditorFilterRemove = '去滤镜';
  static const String imageEditorFilterLoadFailed = '滤镜暂时无法加载';

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
  static const String imageEditorProSharpen = '锐化';
  static const String imageEditorProDenoise = '降噪';
  static const String imageEditorProUnsharpen = '反锐化';
  static const String imageEditorProPerspective = '透视';
  static const String imageEditorProHeal = '修复';
  static const String imageEditorProToneContrast = '色调对比度';
  static const String imageEditorProGlamourGlow = '魅力光晕';
  static const String imageEditorTextStyle = '样式';
  static const String imageEditorTextColor = '颜色';
  static const String imageEditorTextAdd = '添加文字';
  static const String imageEditorTextEditHint = '输入文字';
  static const String imageEditorTextPlaceholder = '请输入文字';
  static const String imageEditorTextStylePlain = '纯色';
  static const String imageEditorTextStyleOutline = '描边';
  static const String imageEditorTextStyleBar = '底纹';
  static const String imageEditorTextEmptyHint = '点击下方按钮添加文字';
  static const String imageEditorMosaicPixel = '像素';
  static const String imageEditorMosaicBlur = '模糊';
  static const String imageEditorMosaicSize = '大小';
  static const String imageEditorMosaicBrush = '画笔大小';
  static const String imageEditorMosaicPaintHint = '在图片上涂抹添加马赛克';
  static const String imageEditorFrameSimple = '简约';
  static const String imageEditorFrameFilm = '胶片';
  static const String imageEditorFrameWhite = '留白';
  static const String imageEditorPanelPlaceholder = '该专业工具正在完善中';

  /// 专业修图子工具
  static const String imageEditorProCurve = '曲线';
  static const String imageEditorProCurveChannelRgb = 'RGB';
  static const String imageEditorProWhiteBalance = '白平衡';
  static const String imageEditorProWhiteBalanceAuto = '自动';
  static const String imageEditorProLocal = '局部';
  static const String imageEditorProHsl = 'HSL';
  static const String imageEditorProAdjustImage = '调整图片';
  static const String imageEditorProTabOverall = '调整图片';
  static const String imageEditorProTabLocal = '局部';
  static const String imageEditorProTabHsl = 'HSL';
  static const String imageEditorProTabBwLevels = '黑白色阶';
  static const String imageEditorProHue = '色相';
  static const String imageEditorProLuminance = '明度';
  static const String imageEditorProStructure = '结构';
  static const String imageEditorProWhiteLevel = '白色色阶';
  static const String imageEditorProBlackLevel = '黑色色阶';
  static const String imageEditorProAnchorAdd = '添加局部';
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
  static const String videoPlaybackProgressLabel = '视频播放进度';
  static const String videoPlaybackProgressHint = '左右滑动或使用方向键调整播放位置';
  static const String videoEditorTitle = '编辑视频';
  static const String videoEditorPreviewUnavailableTitle = '视频预览暂不可用';
  static const String videoEditorPreviewUnavailableMessage =
      '暂时无法加载视频预览，但仍可返回重新选择素材。';
  static const String videoEditorCapabilityUnavailable =
      '当前平台暂不支持视频剪辑，可直接发布原视频';
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
  static const String imageOriginalLoaded = '已加载原图';
  static const String imageOriginalUnavailable = '当前内容不支持查看原图';
  static String contentLabelForKey(String labelKey) =>
      _contentLabelForKey(labelKey);
}
