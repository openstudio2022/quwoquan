/// Chat 页面专属文案门面。
///
/// 业务页只消费本域常量，避免继续扩大全局 [UITextConstants] 大桶。
abstract final class ChatText {
  static const String localAttachmentMissing = '本地附件不存在，请重新选择后再试。';
  static const String attachmentUploadIncomplete = '附件上传未完成，请稍后再试。';
  static const String attachmentSendIncomplete = '附件发送未完成，请稍后再试。';
  static const String groupNameUpdateIncompleteTitle = '群名称修改未完成';
  static const String groupAdminsUpdateIncompleteTitle = '管理员更新未完成';
  static const String dissolveIncompleteTitle = '解散讨论未完成';
  static const String transferOwnershipIncompleteTitle = '转让群主未完成';
  static const String searchEntry = '已从搜索结果进入该聊天';

  static String selectedMessagesCount(int count) => '已选 $count 条';
  static String searchEntryForQuery(String query) => '已从“$query”进入相关聊天';

  // 从全局文案桶迁移的 Chat 域文案。
  static const String webPcPrimaryMessages = '消息';
  static const String webPcMessagesTabMessages = '消息';
  static const String webPcMessagesTabContacts = '联系人';
  static const String webPcMessagesTabGroups = '群聊';
  static const String webPcSearchHintMessages = '搜索联系人、群聊、消息';
  static const String webPcMessagesRailTitle = '消息中心';
  static const String webPcMessagesRailBody = '在这里查看会话、联系人与群聊，点击任意会话进入对话详情。';
  static const String webPcCreateGroupChatTitle = '发起群聊';
  static const String webPcCreateGroupChatSubtitle = '邀请联系人加入群聊，开始多人会话。';
  static const String chat = '聊天';
  static const String authGateTitleOpenChat = '登录后查看消息';
  static const String authGateTitleSendMessage = '登录后发送消息';
  static const String authGateTitleGreet = '登录后发送打招呼';
  static const String authGateTitleStartGroupChat = '登录后发起群聊';
  static const String authGateSubtitleOpenChat = '读取你的会话列表，并接收新的私信提醒。';
  static const String authGateSubtitleSendMessage = '消息将以你的账号身份发送，对方才能识别你。';
  static const String authGateSubtitleGreet = '用账号身份发起打招呼，对方回复后进入私信。';
  static const String authGateSubtitleStartGroupChat = '创建群聊会同步成员关系和后续消息。';
  static const String authGatePromptOpenChat = '登录后查看消息';
  static const String authGatePromptSendMessage = '登录后即可发送消息';
  static const String authGatePromptGreet = '登录后即可发起打招呼';
  static const String authGatePromptStartGroupChat = '登录后即可发起群聊';
  static const String chatListCacheFallback = '网络不太稳，先显示本机最近的聊天。';
  static const String chatListLoadFailedTitle = '聊天列表没加载出来';
  static const String chatListLoadFailedMessage = '聊天列表未能完成加载。';
  static const String searchContactFallback = '联系人';
  static const String searchChatDirect = '单聊';
  static const String searchChatGroup = '讨论';
  static const String searchChatRecord = '聊天记录';
  static const String searchOpenChat = '打开聊天';
  static String searchChatRecordCount(int count) => '共 $count 条相关的聊天记录';
  static const String chatOpenFailedTitle = '这个聊天打不开';
  static const String chatOpenFailedMessage = '可能已被删除，或你暂时不能查看。';
  static const String conversationInfoUnavailableTitle = chatOpenFailedTitle;
  static const String shareTargetGroup = '群聊';
  static const String shareTargetMessage = '私信';
  static const String shareSelectGroupTitle = '选择群聊';
  static const String shareSelectMessageTitle = '选择私信';

  /// 群成员搜索与 @选择器搜索框占位（服务端字面量搜索）。
  static const String searchGroupMembers = '搜索群成员';

  /// 成员搜索无结果。
  static const String noMatchingMembers = '暂无匹配成员';
  static const String mentionPickerTitle = '选择提醒的人';
  static const String mentionAll = '所有人';
  static const String mentionAllDescription = '提醒群内所有成员';
  static const String mentionPickerLoadFailed = '群成员暂时加载失败';
  static const String mentionPickerRetry = '重试';
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
  static const String noReminderMessages = '暂无提醒';
  static const String noReminderHint = '主页动态、圈子摘要和主动提醒会在这里汇总';
  static const String untitledConversation = '未命名对话';
  static const String chatPreviewImage = '[图片]';
  static const String chatPreviewVideo = '[视频]';
  static const String chatPreviewFile = '[文件]';
  static const String chatPreviewVoice = '[语音]';
  static const String chatPreviewCall = '[通话]';
  static const String chatPreviewCard = '[卡片]';

  /// 活动群一次性破冰卡的框架标签（交集主句本身来自云侧，端不拼句）。
  static const String chatIcebreakerCardLabel = '破冰时刻';

  /// 发送失败气泡的手动重发行动点（语义标签与可达性文案）。
  static const String chatRetrySendMessage = '重新发送';

  /// 手动重发仍失败时的提示。
  static const String chatRetrySendFailed = '重发失败，请稍后再试';

  /// 免打扰/置顶等会话设置更新失败时的提示（开关回滚）。
  static const String settingUpdateFailed = '设置更新失败，请稍后再试';

  /// 文件消息打开失败 / 媒体不可用的结构化提示。
  static const String chatFileOpenFailed = '文件打开失败，请稍后再试';
  static const String chatMediaUnavailable = '媒体暂不可用，请稍后再试';

  /// 会话内查找聊天记录（设置页入口与面板标题）。
  static const String searchInConversation = '查找聊天记录';
  static const String searchInConversationTitle = '查找聊天记录';
  static const String searchInConversationPlaceholder = '搜索本会话消息';
  static const String searchInConversationEmpty = '没有匹配的聊天记录';
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

  /// 消息长按菜单（1:1 对应 MessageActionMenu.tsx）
  static const String messageActionForward = '转发';
  static const String messageActionSelect = '多选';
  static const String messageActionCopy = '复制';
  static const String messageActionRecall = '撤回';
  static const String messageActionDelete = '删除';
  static const String messageActionReceipts = '已读回执';
  static const String messageReceiptTitle = '消息已读回执';
  static const String messageReceiptEmpty = '暂无已读回执';
  static const String messageReceiptMember = '会话成员';
  static String messageReceiptSemanticLabel(String displayName) =>
      '$displayName 已读';
  static const String inputHint = '输入消息...';
  static const String send = '发送', emoji = '表情';
  static const String keyboard = '键盘';
  static const String voiceInput = '语音输入';

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
  static const String setChatBackground = '设置当前聊天背景';
  static const String clearChatHistory = '清空聊天记录';
  static const String exitGroupChat = '退出群聊';
  static const String exitGroupChatConfirmMessage = '退出后将不再接收该群聊消息，确定退出吗？';
  static const String exitGroupChatSuccess = '已退出群聊';
  static const String dissolveGroupChat = '解散该群聊';
  static const String dissolveGroupChatConfirmMessage =
      '解散后所有成员将被移出群聊，此操作不可撤销。';
  static const String groupChatDissolvedToast = '群聊已解散';
  static const String dissolveGroupChatFailedToast = '解散群聊失败，请稍后重试';
  static const String addMember = '添加成员', groupManagement = '群管理';
  static const String circleGroupManagedNotice = '该群由圈群管理';
  static const String openCircleGroupManagement = '前往圈子详情管理';
  static const String removeMemberEntry = '移出成员';
  static const String removeMemberConfirmPrefix = '将 ';
  static const String removeMemberConfirmSuffix = ' 移出群聊？';
  static const String removeMemberSuccess = '已移出群聊';
  static const String exitRemoveMemberMode = '完成';
  static const String groupAnnouncementEditTitle = '群公告';
  static const String groupAnnouncementHint = '请输入群公告内容';
  static const String groupAnnouncementPublish = '发布';
  static const String groupAnnouncementPublished = '群公告已发布';
  static const String groupAnnouncementCleared = '群公告已清空';
  static const String groupAnnouncementViewOnlyNote = '仅群主和管理员可编辑群公告';
  static const String groupAnnouncementPublishConfirm = '发布后将通知全部群成员，确定发布吗？';
  static const String groupNameAdminOnly = '群聊已设定为只有群主或管理员才能修改名称';
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
  static const String startGroupChat = '发起群聊';
  static const String chatMutualFollowRtcHint = '互相关注后可发起语音和视频通话';
  static const String chatBlockedConversationHint = '当前会话已被关系门禁限制，暂时无法继续发送消息';
  static const String chatBlockedConversationInputHint = '当前会话暂不可发送消息';
  static const String chatGreetingInboxTitle = '新的打招呼';
  static const String chatGreetingInboxEmpty = '暂时没有待处理的打招呼';
  static const String chatConversationNoMessages = '还没有消息，发一条开始聊天吧';
  static const String chatTimelineOfflineReadOnlyHint = '暂时无法刷新，正在展示本机保存的消息';
  static const String messageActionReply = '回复';
  static const String chatReplyOriginalUnavailable = '原消息不可用';
  static const String chatGreetingCenterTitle = '打招呼';
  static const String chatGreetingReceived = '收到的';
  static const String chatGreetingSentTab = '发出的';
  static const String chatGreetingReceivedEmpty = '暂时没有收到打招呼';
  static const String chatGreetingSentEmpty = '暂时没有发出打招呼';
  static const String chatGreetingDefaultMessage = '想和你打个招呼';
  static const String chatGreetingPeerFallback = '用户';
  static const String chatGreetingInboxReply = '回复并建会话';
  static const String chatGreetingInboxIgnore = '忽略';
  static const String chatGreetingCancel = '撤回';
  static const String chatGreetingCancelConfirmTitle = '撤回这条打招呼？';
  static const String chatGreetingCancelConfirmMessage = '撤回后对方将无法再处理该请求。';
  static const String chatGreetingCancelled = '已撤回打招呼';
  static const String chatGreetingStatusPending = '等待回复';
  static const String chatGreetingStatusReplied = '已建立会话';
  static const String chatGreetingStatusIgnored = '已忽略';
  static const String chatGreetingStatusBlocked = '不可继续';
  static const String chatGreetingStatusCancelled = '已撤回';
  static const String chatGreetingStatusExpired = '已过期';
  static const String chatEmptyGroupTitle = '暂无讨论消息';
  static const String chatEmptyGroupSubtitle = '加入讨论后的最近动态会出现在这里';
  static const String chatEmptyDirectTitle = '暂无私聊消息';
  static const String chatEmptyDirectSubtitle = '与互关用户或已建立连接的人交流后会出现在这里';
  static const String chatGreetingSent = '打招呼已发送';
  static const String chatGreetingReplySucceeded = '已回复，正式会话已建立';
  static const String chatGreetingIgnored = '已忽略打招呼';
  static const String createActionGroupChatHint = '邀请联系人加入群聊';
  static const String createNewGroupChat = '创建新群聊';
  static const String selectFriendsFromGroupChat = '选择群聊成员';
  static const String selectFriendsFromCircle = '选择圈子成员';
  static const String selectGroupChat = '选择群聊';
  static const String searchGroupChatHint = '搜索群聊';
  static const String selectAll = '全选', selectAction = '选择';
  static const String friendsCount = '个朋友';

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
  static const String chatVoicePermissionGrantedAfterSettings =
      '麦克风已开启，可以发送语音了';
  static const String permissionNotificationsLabel = '通知';
  static const String permissionNotificationsPrimerTitle = '需要通知权限';
  static const String permissionNotificationsPrimerMessage =
      '接收消息提醒需要通知权限。点「继续」后，请在系统弹窗中选择「允许」。';
  static const String permissionNotificationsOpenSettings =
      '请在 设置 → 趣我圈 → 通知中开启权限';
  static const String permissionNotificationsDenied = '未获得通知权限';
  static const String chatVoiceRecordUnavailable = '暂时无法录音，请稍后重试';
  static const String chatVoicePendingRetry = '语音没发出去，已保存，点重试';
  static const String chatVoiceUploadFailed = '语音上传失败，请重试';
  static const String chatVoicePlayUnavailable = '语音暂不可播放';

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
  static String forwardRecipientGroupMemberCount(int count) => '$count人';
  static const String createActionCreateGroupShort = '发起群聊';
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
  static const String startGroupChatPickFromCircle = '从圈子中选择';
  static const String startGroupChatPickFromGroupSearch = '搜索群聊';
  static const String startGroupChatPickFromCircleSearch = '搜索圈子';
  static const String startGroupChatGroupPickerTitle = '选择群聊';
  static const String startGroupChatCirclePickerTitle = '选择圈子';
  static const String startGroupChatGroupPickerEmpty = '暂无可选的群聊';
  static const String startGroupChatCirclePickerEmpty = '暂无已绑定群聊的可选圈子';
  static const String startGroupChatCompanionContextTitle = '正在拉群约伴';
  static const String startGroupChatCompanionContextSubtitle =
      '已带入共同想去对象与交集来源，新群会按该对象命名；提交前仍会经过登录、实名、青少年模式和频控等安全门。';

  /// 交集约伴群的默认群名：约伴群是关于某个共同对象的，不是成员名拼接的普通群。
  static String startGroupChatCompanionGroupTitle(String objectName) =>
      '$objectName · 约伴';
  static String startGroupChatRemovedMember(String name) => '已移除 $name';
  static String startGroupChatFriendsCount(int count) => '$count 个朋友';
  static String startGroupChatGroupMemberTitle(String name, int count) =>
      '$name（$count 个朋友）';

  static const String shareTargetWechat = '微信';
  static const String shareTargetMoments = '朋友圈';
  static const String shareTo = '分享到';
  static const String shareInternalTitle = '分享到趣我圈';
  static const String shareExternalTitle = '分享到其他平台';
  static const String shareActionMore = '更多';
  static const String shareCompleted = '分享完成';
  static const String shareActionSavePoster = '保存海报';
  static const String shareActionSystemShare = '系统分享';
  static const String sharePrivateBlocked = '仅自己可见内容不可分享';
  static const String shareLinkCopied = '分享链接已复制';
  static const String sharePosterSaved = '海报已保存到本地文件';
  static const String shareCancelled = '已取消分享';
  static const String shareFailed = '分享失败，请稍后重试';
  static const String commentAtXiaoqu = '@小趣';
  static const String commentXiaoquBadge = '小趣回复';
  static const String commentXiaoquSource = '基于当前内容与评论上下文生成，可继续追问或纠错';
  static const String copiedToClipboard = '已复制';
  static const String more = '更多';
  static const String expand = '展开';
  static const String globalActionSheetTitle = '发起';
  static const String selectCircle = '选择圈子';
  static const String permissionPrimerContinue = '继续';
  static const String permissionMicrophoneLabel = '麦克风';
  static const String permissionCameraLabel = '相机';
  static const String permissionPhotosLabel = '相册';
  static const String permissionLocationLabel = '定位';
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
  static String permissionStillDeniedMessage(String permissionLabel) =>
      '$permissionLabel 仍未开启，请按 设置 → 趣我圈 → $permissionLabel 手动开启';
  static String permissionGrantedMessage(String permissionLabel) =>
      '$permissionLabel 已开启';
  static String permissionRestrictedMessage(String permissionLabel) =>
      '$permissionLabel 权限受系统限制，暂不可用';
  static const String timeFormatAM = '上午', timeFormatPM = '下午';
}
