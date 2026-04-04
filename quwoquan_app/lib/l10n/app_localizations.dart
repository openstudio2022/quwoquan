import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_en.dart';
import 'app_localizations_zh.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('en'),
    Locale('zh'),
  ];

  /// No description provided for @home.
  ///
  /// In zh, this message translates to:
  /// **'首页'**
  String get home;

  /// No description provided for @discovery.
  ///
  /// In zh, this message translates to:
  /// **'发现'**
  String get discovery;

  /// No description provided for @discoveryTabMoment.
  ///
  /// In zh, this message translates to:
  /// **'微趣'**
  String get discoveryTabMoment;

  /// No description provided for @discoveryTabPhoto.
  ///
  /// In zh, this message translates to:
  /// **'美图'**
  String get discoveryTabPhoto;

  /// No description provided for @discoveryTabVideo.
  ///
  /// In zh, this message translates to:
  /// **'视频'**
  String get discoveryTabVideo;

  /// No description provided for @discoveryTabArticle.
  ///
  /// In zh, this message translates to:
  /// **'文章'**
  String get discoveryTabArticle;

  /// No description provided for @discoveryTabHelperRead.
  ///
  /// In zh, this message translates to:
  /// **'帮读'**
  String get discoveryTabHelperRead;

  /// No description provided for @discoveryHelperSummaryTitle.
  ///
  /// In zh, this message translates to:
  /// **'小趣已为你读完'**
  String get discoveryHelperSummaryTitle;

  /// No description provided for @discoveryHelperSummarySubtitle.
  ///
  /// In zh, this message translates to:
  /// **'今日值得看 3 条，已筛选 27 条重复信息'**
  String get discoveryHelperSummarySubtitle;

  /// No description provided for @discoveryHelperOneLinerTemplate.
  ///
  /// In zh, this message translates to:
  /// **'自上次阅读以来，{placeholder}'**
  String discoveryHelperOneLinerTemplate(String placeholder);

  /// No description provided for @discoveryHelperDimensionFriendPublish.
  ///
  /// In zh, this message translates to:
  /// **'趣友新动态'**
  String get discoveryHelperDimensionFriendPublish;

  /// No description provided for @discoveryHelperDimensionNewFollowPublish.
  ///
  /// In zh, this message translates to:
  /// **'刚加入的趣友'**
  String get discoveryHelperDimensionNewFollowPublish;

  /// No description provided for @discoveryHelperDimensionDormantFriendPublish.
  ///
  /// In zh, this message translates to:
  /// **'久未发·最近有互动'**
  String get discoveryHelperDimensionDormantFriendPublish;

  /// No description provided for @discoveryHelperDimensionCircleMoment.
  ///
  /// In zh, this message translates to:
  /// **'圈子发生了什么'**
  String get discoveryHelperDimensionCircleMoment;

  /// No description provided for @discoveryHelperDimensionInteractionWithYou.
  ///
  /// In zh, this message translates to:
  /// **'谁与你互动'**
  String get discoveryHelperDimensionInteractionWithYou;

  /// No description provided for @discoveryHelperDimensionExplore.
  ///
  /// In zh, this message translates to:
  /// **'探索推荐'**
  String get discoveryHelperDimensionExplore;

  /// No description provided for @discoveryHelperTimelineToday.
  ///
  /// In zh, this message translates to:
  /// **'今天'**
  String get discoveryHelperTimelineToday;

  /// No description provided for @discoveryHelperTimelineYesterday.
  ///
  /// In zh, this message translates to:
  /// **'昨天'**
  String get discoveryHelperTimelineYesterday;

  /// No description provided for @discoveryHelperTimelineThisWeek.
  ///
  /// In zh, this message translates to:
  /// **'本周'**
  String get discoveryHelperTimelineThisWeek;

  /// No description provided for @discoveryHelperExpandMoments.
  ///
  /// In zh, this message translates to:
  /// **'展开微趣'**
  String get discoveryHelperExpandMoments;

  /// No description provided for @discoveryHelperExpandArticles.
  ///
  /// In zh, this message translates to:
  /// **'查看文章列表'**
  String get discoveryHelperExpandArticles;

  /// No description provided for @discoveryHelperSectionMoments.
  ///
  /// In zh, this message translates to:
  /// **'微趣'**
  String get discoveryHelperSectionMoments;

  /// No description provided for @discoveryHelperSectionArticles.
  ///
  /// In zh, this message translates to:
  /// **'文章'**
  String get discoveryHelperSectionArticles;

  /// No description provided for @discoveryHelperActionReadOriginal.
  ///
  /// In zh, this message translates to:
  /// **'看原文'**
  String get discoveryHelperActionReadOriginal;

  /// No description provided for @discoveryHelperActionLater.
  ///
  /// In zh, this message translates to:
  /// **'稍后处理'**
  String get discoveryHelperActionLater;

  /// No description provided for @discoveryHelperActionPreference.
  ///
  /// In zh, this message translates to:
  /// **'更像这个'**
  String get discoveryHelperActionPreference;

  /// No description provided for @assistantCommandRead.
  ///
  /// In zh, this message translates to:
  /// **'帮我读'**
  String get assistantCommandRead;

  /// No description provided for @assistantCommandRemember.
  ///
  /// In zh, this message translates to:
  /// **'帮我记'**
  String get assistantCommandRemember;

  /// No description provided for @assistantCommandHandle.
  ///
  /// In zh, this message translates to:
  /// **'帮我办'**
  String get assistantCommandHandle;

  /// No description provided for @assistantCommandShare.
  ///
  /// In zh, this message translates to:
  /// **'帮我发'**
  String get assistantCommandShare;

  /// No description provided for @assistantCommandFind.
  ///
  /// In zh, this message translates to:
  /// **'帮我找'**
  String get assistantCommandFind;

  /// No description provided for @assistantCommandPlan.
  ///
  /// In zh, this message translates to:
  /// **'帮我排'**
  String get assistantCommandPlan;

  /// No description provided for @assistantActionNoRemind.
  ///
  /// In zh, this message translates to:
  /// **'不再提醒'**
  String get assistantActionNoRemind;

  /// No description provided for @assistantFeedbackSavedToMemory.
  ///
  /// In zh, this message translates to:
  /// **'已加入记忆'**
  String get assistantFeedbackSavedToMemory;

  /// No description provided for @assistantFeedbackTaskDraftCreated.
  ///
  /// In zh, this message translates to:
  /// **'已生成待办草案'**
  String get assistantFeedbackTaskDraftCreated;

  /// No description provided for @assistantFeedbackShareDraftCreated.
  ///
  /// In zh, this message translates to:
  /// **'已生成分享草稿'**
  String get assistantFeedbackShareDraftCreated;

  /// No description provided for @assistantFeedbackPlanCreated.
  ///
  /// In zh, this message translates to:
  /// **'已生成安排建议'**
  String get assistantFeedbackPlanCreated;

  /// No description provided for @assistantFeedbackRemindLater.
  ///
  /// In zh, this message translates to:
  /// **'已设为稍后提醒'**
  String get assistantFeedbackRemindLater;

  /// No description provided for @assistantFeedbackReduceProactive.
  ///
  /// In zh, this message translates to:
  /// **'已减少主动提醒'**
  String get assistantFeedbackReduceProactive;

  /// No description provided for @assistantFeedbackOptimizeRecommendation.
  ///
  /// In zh, this message translates to:
  /// **'收到，将优化推荐'**
  String get assistantFeedbackOptimizeRecommendation;

  /// No description provided for @assistantFeedbackAddedToLater.
  ///
  /// In zh, this message translates to:
  /// **'已加入稍后处理'**
  String get assistantFeedbackAddedToLater;

  /// No description provided for @assistantEntryFind.
  ///
  /// In zh, this message translates to:
  /// **'找小趣'**
  String get assistantEntryFind;

  /// No description provided for @assistantEntryAsk.
  ///
  /// In zh, this message translates to:
  /// **'问小趣'**
  String get assistantEntryAsk;

  /// No description provided for @assistantHalfSheetEnterFullChat.
  ///
  /// In zh, this message translates to:
  /// **'进入完整对话'**
  String get assistantHalfSheetEnterFullChat;

  /// No description provided for @assistantHalfSheetInputPlaceholder.
  ///
  /// In zh, this message translates to:
  /// **'说点什么或选上面试试'**
  String get assistantHalfSheetInputPlaceholder;

  /// No description provided for @assistantHalfSheetSuggestionTitle.
  ///
  /// In zh, this message translates to:
  /// **'当前适合干啥'**
  String get assistantHalfSheetSuggestionTitle;

  /// No description provided for @search.
  ///
  /// In zh, this message translates to:
  /// **'搜索'**
  String get search;

  /// No description provided for @create.
  ///
  /// In zh, this message translates to:
  /// **'创建'**
  String get create;

  /// No description provided for @chat.
  ///
  /// In zh, this message translates to:
  /// **'聊天'**
  String get chat;

  /// No description provided for @profile.
  ///
  /// In zh, this message translates to:
  /// **'个人资料'**
  String get profile;

  /// No description provided for @like.
  ///
  /// In zh, this message translates to:
  /// **'点赞'**
  String get like;

  /// No description provided for @share.
  ///
  /// In zh, this message translates to:
  /// **'分享'**
  String get share;

  /// No description provided for @follow.
  ///
  /// In zh, this message translates to:
  /// **'关注'**
  String get follow;

  /// No description provided for @comment.
  ///
  /// In zh, this message translates to:
  /// **'评论'**
  String get comment;

  /// No description provided for @welcomeTitle.
  ///
  /// In zh, this message translates to:
  /// **'趣我圈'**
  String get welcomeTitle;

  /// No description provided for @welcomeSubtitle.
  ///
  /// In zh, this message translates to:
  /// **'以兴趣为半径，画出我们的交集'**
  String get welcomeSubtitle;

  /// No description provided for @welcomeMainSlogan.
  ///
  /// In zh, this message translates to:
  /// **'专注你的热爱，其余交给小趣'**
  String get welcomeMainSlogan;

  /// No description provided for @welcomeButtonLabel.
  ///
  /// In zh, this message translates to:
  /// **'开启发现之旅'**
  String get welcomeButtonLabel;

  /// No description provided for @welcomeFooterCredit.
  ///
  /// In zh, this message translates to:
  /// **'小趣私人助手 · 与你相伴'**
  String get welcomeFooterCredit;

  /// No description provided for @commentPlaceholder.
  ///
  /// In zh, this message translates to:
  /// **'添加评论...'**
  String get commentPlaceholder;

  /// No description provided for @commentTooLong.
  ///
  /// In zh, this message translates to:
  /// **'评论过长'**
  String get commentTooLong;

  /// No description provided for @commentEmpty.
  ///
  /// In zh, this message translates to:
  /// **'评论不能为空'**
  String get commentEmpty;

  /// No description provided for @commentClosed.
  ///
  /// In zh, this message translates to:
  /// **'评论已关闭'**
  String get commentClosed;

  /// No description provided for @needLogin.
  ///
  /// In zh, this message translates to:
  /// **'需要登录'**
  String get needLogin;

  /// No description provided for @loading.
  ///
  /// In zh, this message translates to:
  /// **'加载中...'**
  String get loading;

  /// No description provided for @retry.
  ///
  /// In zh, this message translates to:
  /// **'重试'**
  String get retry;

  /// No description provided for @cancel.
  ///
  /// In zh, this message translates to:
  /// **'取消'**
  String get cancel;

  /// No description provided for @confirm.
  ///
  /// In zh, this message translates to:
  /// **'确认'**
  String get confirm;

  /// No description provided for @user.
  ///
  /// In zh, this message translates to:
  /// **'用户'**
  String get user;

  /// No description provided for @following.
  ///
  /// In zh, this message translates to:
  /// **'已关注'**
  String get following;

  /// No description provided for @unknownUser.
  ///
  /// In zh, this message translates to:
  /// **'未知用户'**
  String get unknownUser;

  /// No description provided for @copyLink.
  ///
  /// In zh, this message translates to:
  /// **'复制链接'**
  String get copyLink;

  /// No description provided for @shareTargetWechat.
  ///
  /// In zh, this message translates to:
  /// **'微信'**
  String get shareTargetWechat;

  /// No description provided for @shareTargetMoments.
  ///
  /// In zh, this message translates to:
  /// **'朋友圈'**
  String get shareTargetMoments;

  /// No description provided for @loadFailed.
  ///
  /// In zh, this message translates to:
  /// **'加载失败'**
  String get loadFailed;

  /// No description provided for @report.
  ///
  /// In zh, this message translates to:
  /// **'举报'**
  String get report;

  /// No description provided for @shareTo.
  ///
  /// In zh, this message translates to:
  /// **'分享到'**
  String get shareTo;

  /// No description provided for @unknown.
  ///
  /// In zh, this message translates to:
  /// **'未知'**
  String get unknown;

  /// No description provided for @commentSent.
  ///
  /// In zh, this message translates to:
  /// **'评论已发送'**
  String get commentSent;

  /// No description provided for @replySent.
  ///
  /// In zh, this message translates to:
  /// **'回复已发送'**
  String get replySent;

  /// No description provided for @pullToRefreshHint.
  ///
  /// In zh, this message translates to:
  /// **'下拉刷新试试'**
  String get pullToRefreshHint;

  /// No description provided for @goToUserProfile.
  ///
  /// In zh, this message translates to:
  /// **'前往用户主页'**
  String get goToUserProfile;

  /// No description provided for @loadMoreComments.
  ///
  /// In zh, this message translates to:
  /// **'加载更多评论'**
  String get loadMoreComments;

  /// No description provided for @editProfile.
  ///
  /// In zh, this message translates to:
  /// **'编辑资料'**
  String get editProfile;

  /// No description provided for @settings.
  ///
  /// In zh, this message translates to:
  /// **'设置'**
  String get settings;

  /// No description provided for @bookmarks.
  ///
  /// In zh, this message translates to:
  /// **'收藏'**
  String get bookmarks;

  /// No description provided for @createCircle.
  ///
  /// In zh, this message translates to:
  /// **'创建圈子'**
  String get createCircle;

  /// No description provided for @editCircle.
  ///
  /// In zh, this message translates to:
  /// **'编辑圈子'**
  String get editCircle;

  /// No description provided for @manageCenter.
  ///
  /// In zh, this message translates to:
  /// **'管理中心'**
  String get manageCenter;

  /// No description provided for @followCircle.
  ///
  /// In zh, this message translates to:
  /// **'关注圈子'**
  String get followCircle;

  /// No description provided for @followedCircle.
  ///
  /// In zh, this message translates to:
  /// **'已关注圈子'**
  String get followedCircle;

  /// No description provided for @joinCircle.
  ///
  /// In zh, this message translates to:
  /// **'加入圈子'**
  String get joinCircle;

  /// No description provided for @joinedCircle.
  ///
  /// In zh, this message translates to:
  /// **'已加入圈子'**
  String get joinedCircle;

  /// No description provided for @joinPending.
  ///
  /// In zh, this message translates to:
  /// **'加入审批中'**
  String get joinPending;

  /// No description provided for @circleMembers.
  ///
  /// In zh, this message translates to:
  /// **'成员'**
  String get circleMembers;

  /// No description provided for @circleGroups.
  ///
  /// In zh, this message translates to:
  /// **'群聊'**
  String get circleGroups;

  /// No description provided for @circleFans.
  ///
  /// In zh, this message translates to:
  /// **'粉丝'**
  String get circleFans;

  /// No description provided for @circleLikes.
  ///
  /// In zh, this message translates to:
  /// **'获赞'**
  String get circleLikes;

  /// No description provided for @searchMembersHint.
  ///
  /// In zh, this message translates to:
  /// **'搜索成员...'**
  String get searchMembersHint;

  /// No description provided for @searchGroupsHint.
  ///
  /// In zh, this message translates to:
  /// **'搜索群聊...'**
  String get searchGroupsHint;

  /// No description provided for @searchFansHint.
  ///
  /// In zh, this message translates to:
  /// **'搜索粉丝...'**
  String get searchFansHint;

  /// No description provided for @searchLikesHint.
  ///
  /// In zh, this message translates to:
  /// **'搜索获赞记录...'**
  String get searchLikesHint;

  /// No description provided for @noData.
  ///
  /// In zh, this message translates to:
  /// **'暂无数据'**
  String get noData;

  /// No description provided for @noLikesRecord.
  ///
  /// In zh, this message translates to:
  /// **'暂无获赞记录'**
  String get noLikesRecord;

  /// No description provided for @circleWorksTab.
  ///
  /// In zh, this message translates to:
  /// **'创作'**
  String get circleWorksTab;

  /// No description provided for @circleInteractionTab.
  ///
  /// In zh, this message translates to:
  /// **'互动'**
  String get circleInteractionTab;

  /// No description provided for @circleLifestyleTab.
  ///
  /// In zh, this message translates to:
  /// **'生活'**
  String get circleLifestyleTab;

  /// No description provided for @circleSubAll.
  ///
  /// In zh, this message translates to:
  /// **'全部'**
  String get circleSubAll;

  /// No description provided for @circleSubPhoto.
  ///
  /// In zh, this message translates to:
  /// **'图片'**
  String get circleSubPhoto;

  /// No description provided for @circleSubVideo.
  ///
  /// In zh, this message translates to:
  /// **'视频'**
  String get circleSubVideo;

  /// No description provided for @circleSubArticle.
  ///
  /// In zh, this message translates to:
  /// **'文章'**
  String get circleSubArticle;

  /// No description provided for @circleSubLikes.
  ///
  /// In zh, this message translates to:
  /// **'赞'**
  String get circleSubLikes;

  /// No description provided for @circleSubComments.
  ///
  /// In zh, this message translates to:
  /// **'评论'**
  String get circleSubComments;

  /// No description provided for @circleOfficialBadge.
  ///
  /// In zh, this message translates to:
  /// **'官方认证 | 优质社区'**
  String get circleOfficialBadge;

  /// No description provided for @circlesRecommendedTitle.
  ///
  /// In zh, this message translates to:
  /// **'推荐圈子'**
  String get circlesRecommendedTitle;

  /// No description provided for @circlesFollowingEmpty.
  ///
  /// In zh, this message translates to:
  /// **'关注暂无内容'**
  String get circlesFollowingEmpty;

  /// No description provided for @discoveryEndHint.
  ///
  /// In zh, this message translates to:
  /// **'已经到底啦'**
  String get discoveryEndHint;

  /// No description provided for @seeMore.
  ///
  /// In zh, this message translates to:
  /// **'查看更多'**
  String get seeMore;

  /// No description provided for @fullText.
  ///
  /// In zh, this message translates to:
  /// **'全文'**
  String get fullText;

  /// No description provided for @collapse.
  ///
  /// In zh, this message translates to:
  /// **'收起'**
  String get collapse;

  /// No description provided for @ellipsis.
  ///
  /// In zh, this message translates to:
  /// **'...'**
  String get ellipsis;

  /// No description provided for @assistantPanelTitleSuffix.
  ///
  /// In zh, this message translates to:
  /// **'智能助手'**
  String get assistantPanelTitleSuffix;

  /// No description provided for @assistantPanelSubtitle.
  ///
  /// In zh, this message translates to:
  /// **'可总结图片与评论，给出推荐与标注信息'**
  String get assistantPanelSubtitle;

  /// No description provided for @assistantAskPlaceholder.
  ///
  /// In zh, this message translates to:
  /// **'可以问：这张图有什么亮点？'**
  String get assistantAskPlaceholder;

  /// No description provided for @assistantSuggestedQuestionsTitle.
  ///
  /// In zh, this message translates to:
  /// **'推荐问题'**
  String get assistantSuggestedQuestionsTitle;

  /// No description provided for @assistantAskAboutSummary.
  ///
  /// In zh, this message translates to:
  /// **'帮我总结这张图片'**
  String get assistantAskAboutSummary;

  /// No description provided for @assistantAskAboutOutfit.
  ///
  /// In zh, this message translates to:
  /// **'分析人物穿搭/风格'**
  String get assistantAskAboutOutfit;

  /// No description provided for @assistantAskAboutLocation.
  ///
  /// In zh, this message translates to:
  /// **'这可能是什么地方'**
  String get assistantAskAboutLocation;

  /// No description provided for @assistantAskAboutRecommendations.
  ///
  /// In zh, this message translates to:
  /// **'给出相关推荐'**
  String get assistantAskAboutRecommendations;

  /// No description provided for @assistantAskAboutComments.
  ///
  /// In zh, this message translates to:
  /// **'结合评论给出观点'**
  String get assistantAskAboutComments;

  /// No description provided for @assistantInitialSummaryPrefix.
  ///
  /// In zh, this message translates to:
  /// **'我已经浏览了当前内容：'**
  String get assistantInitialSummaryPrefix;

  /// No description provided for @assistantInitialSummaryNoContent.
  ///
  /// In zh, this message translates to:
  /// **'我已经浏览了当前图片，可以帮你总结亮点、推荐类似内容或解析拍摄信息。'**
  String get assistantInitialSummaryNoContent;

  /// No description provided for @assistantInitialSummaryTitleLabel.
  ///
  /// In zh, this message translates to:
  /// **'标题：'**
  String get assistantInitialSummaryTitleLabel;

  /// No description provided for @assistantInitialSummaryCaptionLabel.
  ///
  /// In zh, this message translates to:
  /// **'配文：'**
  String get assistantInitialSummaryCaptionLabel;

  /// No description provided for @assistantPromptFollowUp.
  ///
  /// In zh, this message translates to:
  /// **'你还可以继续问我：'**
  String get assistantPromptFollowUp;

  /// No description provided for @assistantAutoResponsePrefix.
  ///
  /// In zh, this message translates to:
  /// **'收到，我来看看：'**
  String get assistantAutoResponsePrefix;

  /// No description provided for @assistantCardHighlightsTitle.
  ///
  /// In zh, this message translates to:
  /// **'图片亮点'**
  String get assistantCardHighlightsTitle;

  /// No description provided for @assistantCardHighlightsBody.
  ///
  /// In zh, this message translates to:
  /// **'构图集中在主体与光影对比，画面层次清晰。'**
  String get assistantCardHighlightsBody;

  /// No description provided for @assistantCardCommentsTitle.
  ///
  /// In zh, this message translates to:
  /// **'评论总结'**
  String get assistantCardCommentsTitle;

  /// No description provided for @assistantCardCommentsBody.
  ///
  /// In zh, this message translates to:
  /// **'当前讨论聚焦于拍摄地点与色调风格。'**
  String get assistantCardCommentsBody;

  /// No description provided for @assistantCardRecommendationsTitle.
  ///
  /// In zh, this message translates to:
  /// **'推荐内容'**
  String get assistantCardRecommendationsTitle;

  /// No description provided for @assistantCardRecommendationsBody.
  ///
  /// In zh, this message translates to:
  /// **'可以看看同风格拍摄与相似场景合集。'**
  String get assistantCardRecommendationsBody;

  /// No description provided for @atMe.
  ///
  /// In zh, this message translates to:
  /// **'@我'**
  String get atMe;

  /// No description provided for @unread.
  ///
  /// In zh, this message translates to:
  /// **'未读'**
  String get unread;

  /// No description provided for @secretMessage.
  ///
  /// In zh, this message translates to:
  /// **'密信'**
  String get secretMessage;

  /// No description provided for @friends.
  ///
  /// In zh, this message translates to:
  /// **'好友'**
  String get friends;

  /// No description provided for @groupChat.
  ///
  /// In zh, this message translates to:
  /// **'群聊'**
  String get groupChat;

  /// No description provided for @secretLockedTitle.
  ///
  /// In zh, this message translates to:
  /// **'密信已锁定'**
  String get secretLockedTitle;

  /// No description provided for @secretUnlockButton.
  ///
  /// In zh, this message translates to:
  /// **'解锁密信'**
  String get secretUnlockButton;

  /// No description provided for @secretPasswordHint.
  ///
  /// In zh, this message translates to:
  /// **'请输入密信密码'**
  String get secretPasswordHint;

  /// No description provided for @secretUnlockedBanner.
  ///
  /// In zh, this message translates to:
  /// **'密信已解锁'**
  String get secretUnlockedBanner;

  /// No description provided for @secretLockButton.
  ///
  /// In zh, this message translates to:
  /// **'锁定'**
  String get secretLockButton;

  /// No description provided for @noSecretConversations.
  ///
  /// In zh, this message translates to:
  /// **'暂无密信对话'**
  String get noSecretConversations;

  /// No description provided for @noConversations.
  ///
  /// In zh, this message translates to:
  /// **'暂无对话'**
  String get noConversations;

  /// No description provided for @startChatHint.
  ///
  /// In zh, this message translates to:
  /// **'开始与圈友聊天吧！'**
  String get startChatHint;

  /// No description provided for @contactsTabAll.
  ///
  /// In zh, this message translates to:
  /// **'全部'**
  String get contactsTabAll;

  /// No description provided for @contactsTabCircles.
  ///
  /// In zh, this message translates to:
  /// **'圈子'**
  String get contactsTabCircles;

  /// No description provided for @contactsTabSameInterest.
  ///
  /// In zh, this message translates to:
  /// **'同好'**
  String get contactsTabSameInterest;

  /// No description provided for @contactsTabFunGroup.
  ///
  /// In zh, this message translates to:
  /// **'趣群'**
  String get contactsTabFunGroup;

  /// No description provided for @contactsTabFriends.
  ///
  /// In zh, this message translates to:
  /// **'好友'**
  String get contactsTabFriends;

  /// No description provided for @contactsTabGroups.
  ///
  /// In zh, this message translates to:
  /// **'群聊'**
  String get contactsTabGroups;

  /// No description provided for @starredFriends.
  ///
  /// In zh, this message translates to:
  /// **'星标朋友'**
  String get starredFriends;

  /// No description provided for @encryptedMessagePreview.
  ///
  /// In zh, this message translates to:
  /// **'[加密消息] 查看需要验证身份'**
  String get encryptedMessagePreview;

  /// No description provided for @copiedToClipboard.
  ///
  /// In zh, this message translates to:
  /// **'已复制'**
  String get copiedToClipboard;

  /// No description provided for @messageActionForward.
  ///
  /// In zh, this message translates to:
  /// **'转发'**
  String get messageActionForward;

  /// No description provided for @messageActionSelect.
  ///
  /// In zh, this message translates to:
  /// **'多选'**
  String get messageActionSelect;

  /// No description provided for @messageActionCopy.
  ///
  /// In zh, this message translates to:
  /// **'复制'**
  String get messageActionCopy;

  /// No description provided for @messageActionRecall.
  ///
  /// In zh, this message translates to:
  /// **'撤回'**
  String get messageActionRecall;

  /// No description provided for @messageActionDelete.
  ///
  /// In zh, this message translates to:
  /// **'删除'**
  String get messageActionDelete;

  /// No description provided for @inputHint.
  ///
  /// In zh, this message translates to:
  /// **'输入消息...'**
  String get inputHint;

  /// No description provided for @send.
  ///
  /// In zh, this message translates to:
  /// **'发送'**
  String get send;

  /// No description provided for @emoji.
  ///
  /// In zh, this message translates to:
  /// **'表情'**
  String get emoji;

  /// No description provided for @emojiRecent.
  ///
  /// In zh, this message translates to:
  /// **'最近'**
  String get emojiRecent;

  /// No description provided for @emojiCategorySmileys.
  ///
  /// In zh, this message translates to:
  /// **'表情'**
  String get emojiCategorySmileys;

  /// No description provided for @emojiCategoryAnimals.
  ///
  /// In zh, this message translates to:
  /// **'动物'**
  String get emojiCategoryAnimals;

  /// No description provided for @emojiCategoryFood.
  ///
  /// In zh, this message translates to:
  /// **'食物'**
  String get emojiCategoryFood;

  /// No description provided for @emojiCategoryDrink.
  ///
  /// In zh, this message translates to:
  /// **'饮料'**
  String get emojiCategoryDrink;

  /// No description provided for @emojiCategoryActivity.
  ///
  /// In zh, this message translates to:
  /// **'活动'**
  String get emojiCategoryActivity;

  /// No description provided for @emojiCategoryTravel.
  ///
  /// In zh, this message translates to:
  /// **'出行'**
  String get emojiCategoryTravel;

  /// No description provided for @emojiCategoryObjects.
  ///
  /// In zh, this message translates to:
  /// **'物体'**
  String get emojiCategoryObjects;

  /// No description provided for @chatInfoTitle.
  ///
  /// In zh, this message translates to:
  /// **'聊天信息'**
  String get chatInfoTitle;

  /// No description provided for @viewAllMembers.
  ///
  /// In zh, this message translates to:
  /// **'查看全部成员'**
  String get viewAllMembers;

  /// No description provided for @groupName.
  ///
  /// In zh, this message translates to:
  /// **'群聊名称'**
  String get groupName;

  /// No description provided for @qrCode.
  ///
  /// In zh, this message translates to:
  /// **'二维码'**
  String get qrCode;

  /// No description provided for @groupAnnouncement.
  ///
  /// In zh, this message translates to:
  /// **'群公告'**
  String get groupAnnouncement;

  /// No description provided for @muteNotifications.
  ///
  /// In zh, this message translates to:
  /// **'消息免打扰'**
  String get muteNotifications;

  /// No description provided for @pinChat.
  ///
  /// In zh, this message translates to:
  /// **'置顶聊天'**
  String get pinChat;

  /// No description provided for @privacyShield.
  ///
  /// In zh, this message translates to:
  /// **'隐私屏障(禁截屏、禁转发)'**
  String get privacyShield;

  /// No description provided for @setChatBackground.
  ///
  /// In zh, this message translates to:
  /// **'设置当前聊天背景'**
  String get setChatBackground;

  /// No description provided for @clearChatHistory.
  ///
  /// In zh, this message translates to:
  /// **'清空聊天记录'**
  String get clearChatHistory;

  /// No description provided for @exitGroupChat.
  ///
  /// In zh, this message translates to:
  /// **'退出群聊'**
  String get exitGroupChat;

  /// No description provided for @addMember.
  ///
  /// In zh, this message translates to:
  /// **'添加成员'**
  String get addMember;

  /// No description provided for @startGroupChat.
  ///
  /// In zh, this message translates to:
  /// **'发起群聊'**
  String get startGroupChat;

  /// No description provided for @createNewGroupChat.
  ///
  /// In zh, this message translates to:
  /// **'创建新群聊'**
  String get createNewGroupChat;

  /// No description provided for @selectFriendsFromGroupChat.
  ///
  /// In zh, this message translates to:
  /// **'选择群聊中的同好'**
  String get selectFriendsFromGroupChat;

  /// No description provided for @selectFriendsFromCircle.
  ///
  /// In zh, this message translates to:
  /// **'选择圈子中的同好'**
  String get selectFriendsFromCircle;

  /// No description provided for @relatedSameInterest.
  ///
  /// In zh, this message translates to:
  /// **'相关同好'**
  String get relatedSameInterest;

  /// No description provided for @selectGroupChat.
  ///
  /// In zh, this message translates to:
  /// **'选择群聊'**
  String get selectGroupChat;

  /// No description provided for @searchGroupChatHint.
  ///
  /// In zh, this message translates to:
  /// **'搜索群聊'**
  String get searchGroupChatHint;

  /// No description provided for @selectCircle.
  ///
  /// In zh, this message translates to:
  /// **'选择圈子'**
  String get selectCircle;

  /// No description provided for @searchCircleHint.
  ///
  /// In zh, this message translates to:
  /// **'搜索圈子'**
  String get searchCircleHint;

  /// No description provided for @selectAll.
  ///
  /// In zh, this message translates to:
  /// **'全选'**
  String get selectAll;

  /// No description provided for @selectAction.
  ///
  /// In zh, this message translates to:
  /// **'选择'**
  String get selectAction;

  /// No description provided for @friendsCount.
  ///
  /// In zh, this message translates to:
  /// **'个朋友'**
  String get friendsCount;

  /// No description provided for @moreMembers.
  ///
  /// In zh, this message translates to:
  /// **'更多群成员'**
  String get moreMembers;

  /// No description provided for @collapseMembers.
  ///
  /// In zh, this message translates to:
  /// **'收起来'**
  String get collapseMembers;

  /// No description provided for @chatMorePhoto.
  ///
  /// In zh, this message translates to:
  /// **'照片'**
  String get chatMorePhoto;

  /// No description provided for @chatMoreShoot.
  ///
  /// In zh, this message translates to:
  /// **'拍摄'**
  String get chatMoreShoot;

  /// No description provided for @chatMoreBurnAfterRead.
  ///
  /// In zh, this message translates to:
  /// **'阅后即焚'**
  String get chatMoreBurnAfterRead;

  /// No description provided for @chatMoreLocation.
  ///
  /// In zh, this message translates to:
  /// **'位置'**
  String get chatMoreLocation;

  /// No description provided for @chatMoreAudioVideo.
  ///
  /// In zh, this message translates to:
  /// **'音视频'**
  String get chatMoreAudioVideo;

  /// No description provided for @chatMoreRedPacket.
  ///
  /// In zh, this message translates to:
  /// **'红包'**
  String get chatMoreRedPacket;

  /// No description provided for @timeFormatAM.
  ///
  /// In zh, this message translates to:
  /// **'上午'**
  String get timeFormatAM;

  /// No description provided for @timeFormatPM.
  ///
  /// In zh, this message translates to:
  /// **'下午'**
  String get timeFormatPM;

  /// No description provided for @assistantHome.
  ///
  /// In zh, this message translates to:
  /// **'助理主页'**
  String get assistantHome;

  /// No description provided for @assistantUnavailable.
  ///
  /// In zh, this message translates to:
  /// **'助手暂时不可用，请稍后重试。'**
  String get assistantUnavailable;

  /// No description provided for @assistantModelUnavailable.
  ///
  /// In zh, this message translates to:
  /// **'当前未配置可用模型，请先在模型配置中接入远程模型或桥接服务。'**
  String get assistantModelUnavailable;

  /// No description provided for @assistantRunningHint.
  ///
  /// In zh, this message translates to:
  /// **'小趣正在规划与执行中...'**
  String get assistantRunningHint;

  /// No description provided for @assistantFeedbackHelpful.
  ///
  /// In zh, this message translates to:
  /// **'有帮助'**
  String get assistantFeedbackHelpful;

  /// No description provided for @assistantFeedbackUnhelpful.
  ///
  /// In zh, this message translates to:
  /// **'没帮助'**
  String get assistantFeedbackUnhelpful;

  /// No description provided for @assistantFeedbackCorrect.
  ///
  /// In zh, this message translates to:
  /// **'纠正'**
  String get assistantFeedbackCorrect;

  /// No description provided for @assistantFeedbackSubmitted.
  ///
  /// In zh, this message translates to:
  /// **'已记录你的反馈'**
  String get assistantFeedbackSubmitted;

  /// No description provided for @assistantFeedbackReasonTitle.
  ///
  /// In zh, this message translates to:
  /// **'请选择问题原因'**
  String get assistantFeedbackReasonTitle;

  /// No description provided for @assistantFeedbackReasonOffTopic.
  ///
  /// In zh, this message translates to:
  /// **'答非所问'**
  String get assistantFeedbackReasonOffTopic;

  /// No description provided for @assistantFeedbackReasonInsufficient.
  ///
  /// In zh, this message translates to:
  /// **'信息不足'**
  String get assistantFeedbackReasonInsufficient;

  /// No description provided for @assistantFeedbackReasonIncorrect.
  ///
  /// In zh, this message translates to:
  /// **'事实不准'**
  String get assistantFeedbackReasonIncorrect;

  /// No description provided for @assistantFeedbackReasonStyle.
  ///
  /// In zh, this message translates to:
  /// **'表达不清晰'**
  String get assistantFeedbackReasonStyle;

  /// No description provided for @assistantFeedbackReasonPrivacy.
  ///
  /// In zh, this message translates to:
  /// **'隐私顾虑'**
  String get assistantFeedbackReasonPrivacy;

  /// No description provided for @assistantCorrectionTitle.
  ///
  /// In zh, this message translates to:
  /// **'补充纠正'**
  String get assistantCorrectionTitle;

  /// No description provided for @assistantCorrectionHint.
  ///
  /// In zh, this message translates to:
  /// **'告诉我你期望的正确表达'**
  String get assistantCorrectionHint;

  /// No description provided for @assistantActionRegenerate.
  ///
  /// In zh, this message translates to:
  /// **'重新生成'**
  String get assistantActionRegenerate;

  /// No description provided for @assistantActionBrief.
  ///
  /// In zh, this message translates to:
  /// **'更加简洁'**
  String get assistantActionBrief;

  /// No description provided for @assistantActionDetailed.
  ///
  /// In zh, this message translates to:
  /// **'更加详细'**
  String get assistantActionDetailed;

  /// No description provided for @assistantActionSwitchModel.
  ///
  /// In zh, this message translates to:
  /// **'模型切换'**
  String get assistantActionSwitchModel;

  /// No description provided for @assistantTimelineSearchProcess.
  ///
  /// In zh, this message translates to:
  /// **'搜索过程'**
  String get assistantTimelineSearchProcess;

  /// No description provided for @assistantTimelineReferenceCount.
  ///
  /// In zh, this message translates to:
  /// **'可参考 {count} 篇资料'**
  String assistantTimelineReferenceCount(String count);

  /// No description provided for @assistantTimelineThinking.
  ///
  /// In zh, this message translates to:
  /// **'正在思考'**
  String get assistantTimelineThinking;

  /// No description provided for @assistantTimelineKeywordSearch.
  ///
  /// In zh, this message translates to:
  /// **'发起关键词检索'**
  String get assistantTimelineKeywordSearch;

  /// No description provided for @assistantTimelineReferenceIncrement.
  ///
  /// In zh, this message translates to:
  /// **'检索到资料'**
  String get assistantTimelineReferenceIncrement;

  /// No description provided for @assistantTimelineReady.
  ///
  /// In zh, this message translates to:
  /// **'可参考资料已准备'**
  String get assistantTimelineReady;

  /// No description provided for @assistantSearchingReferenceCount.
  ///
  /// In zh, this message translates to:
  /// **'参考 {count} 篇资料'**
  String assistantSearchingReferenceCount(String count);

  /// No description provided for @assistantReferenceCopied.
  ///
  /// In zh, this message translates to:
  /// **'链接已复制'**
  String get assistantReferenceCopied;

  /// No description provided for @assistantReferenceOpenFailed.
  ///
  /// In zh, this message translates to:
  /// **'链接打开失败，已复制到剪贴板'**
  String get assistantReferenceOpenFailed;

  /// No description provided for @assistantReferenceHostBlocked.
  ///
  /// In zh, this message translates to:
  /// **'该链接域名未通过安全白名单，已复制到剪贴板'**
  String get assistantReferenceHostBlocked;

  /// No description provided for @assistantBookmarked.
  ///
  /// In zh, this message translates to:
  /// **'已收藏'**
  String get assistantBookmarked;

  /// No description provided for @assistantDevReplayTitle.
  ///
  /// In zh, this message translates to:
  /// **'助理开发态回放'**
  String get assistantDevReplayTitle;

  /// No description provided for @assistantDevReplayOpen.
  ///
  /// In zh, this message translates to:
  /// **'回放'**
  String get assistantDevReplayOpen;

  /// No description provided for @assistantDevReplayRun.
  ///
  /// In zh, this message translates to:
  /// **'运行记录'**
  String get assistantDevReplayRun;

  /// No description provided for @assistantDevReplayQuery.
  ///
  /// In zh, this message translates to:
  /// **'问题'**
  String get assistantDevReplayQuery;

  /// No description provided for @assistantDevReplayAnswer.
  ///
  /// In zh, this message translates to:
  /// **'回答'**
  String get assistantDevReplayAnswer;

  /// No description provided for @assistantDevReplayPolicy.
  ///
  /// In zh, this message translates to:
  /// **'策略决策'**
  String get assistantDevReplayPolicy;

  /// No description provided for @assistantDevReplayPlan.
  ///
  /// In zh, this message translates to:
  /// **'查询计划'**
  String get assistantDevReplayPlan;

  /// No description provided for @assistantDevReplayRounds.
  ///
  /// In zh, this message translates to:
  /// **'轮次轨迹'**
  String get assistantDevReplayRounds;

  /// No description provided for @assistantDevReplayScore.
  ///
  /// In zh, this message translates to:
  /// **'评分聚合快照'**
  String get assistantDevReplayScore;

  /// No description provided for @assistantNoReplayData.
  ///
  /// In zh, this message translates to:
  /// **'暂无回放数据'**
  String get assistantNoReplayData;

  /// No description provided for @assistantSkillCenterTitle.
  ///
  /// In zh, this message translates to:
  /// **'技能中心'**
  String get assistantSkillCenterTitle;

  /// No description provided for @assistantSkillCenterDefaultAllSubscribedTitle.
  ///
  /// In zh, this message translates to:
  /// **'默认全订阅已开启'**
  String get assistantSkillCenterDefaultAllSubscribedTitle;

  /// No description provided for @assistantSkillCenterDefaultAllSubscribedDesc.
  ///
  /// In zh, this message translates to:
  /// **'开箱即用全部助理能力；执行时仍受风险策略与场景闸门约束。'**
  String get assistantSkillCenterDefaultAllSubscribedDesc;

  /// No description provided for @assistantSkillCenterRestoreDefaultAll.
  ///
  /// In zh, this message translates to:
  /// **'恢复默认全订阅'**
  String get assistantSkillCenterRestoreDefaultAll;

  /// No description provided for @assistantSkillCenterSimpleMode.
  ///
  /// In zh, this message translates to:
  /// **'极简模式'**
  String get assistantSkillCenterSimpleMode;

  /// No description provided for @assistantSkillCenterPackagesTitle.
  ///
  /// In zh, this message translates to:
  /// **'能力包'**
  String get assistantSkillCenterPackagesTitle;

  /// No description provided for @assistantSkillCenterPackageLife.
  ///
  /// In zh, this message translates to:
  /// **'生活助理'**
  String get assistantSkillCenterPackageLife;

  /// No description provided for @assistantSkillCenterPackageWork.
  ///
  /// In zh, this message translates to:
  /// **'工作助理'**
  String get assistantSkillCenterPackageWork;

  /// No description provided for @assistantSkillCenterPackageKnowledge.
  ///
  /// In zh, this message translates to:
  /// **'知识助理'**
  String get assistantSkillCenterPackageKnowledge;

  /// No description provided for @assistantSkillCenterPackageCompanion.
  ///
  /// In zh, this message translates to:
  /// **'陪伴助理'**
  String get assistantSkillCenterPackageCompanion;

  /// No description provided for @assistantSkillCenterNoMappedSkills.
  ///
  /// In zh, this message translates to:
  /// **'暂无对应技能'**
  String get assistantSkillCenterNoMappedSkills;

  /// No description provided for @assistantSkillCenterContainsCount.
  ///
  /// In zh, this message translates to:
  /// **'包含 {count} 项'**
  String assistantSkillCenterContainsCount(int count);

  /// No description provided for @assistantSkillCenterRiskPolicyTitle.
  ///
  /// In zh, this message translates to:
  /// **'风险策略'**
  String get assistantSkillCenterRiskPolicyTitle;

  /// No description provided for @assistantSkillCenterLowRiskAuto.
  ///
  /// In zh, this message translates to:
  /// **'低风险自动执行'**
  String get assistantSkillCenterLowRiskAuto;

  /// No description provided for @assistantSkillCenterLowRiskDesc.
  ///
  /// In zh, this message translates to:
  /// **'检索、总结、问答默认执行'**
  String get assistantSkillCenterLowRiskDesc;

  /// No description provided for @assistantSkillCenterMediumRiskConfirm.
  ///
  /// In zh, this message translates to:
  /// **'中风险轻确认'**
  String get assistantSkillCenterMediumRiskConfirm;

  /// No description provided for @assistantSkillCenterMediumRiskDesc.
  ///
  /// In zh, this message translates to:
  /// **'创建提醒、生成待办需确认'**
  String get assistantSkillCenterMediumRiskDesc;

  /// No description provided for @assistantSkillCenterHighRiskDoubleConfirm.
  ///
  /// In zh, this message translates to:
  /// **'高风险二次确认'**
  String get assistantSkillCenterHighRiskDoubleConfirm;

  /// No description provided for @assistantSkillCenterHighRiskDesc.
  ///
  /// In zh, this message translates to:
  /// **'交易、外部提交等必须二次确认'**
  String get assistantSkillCenterHighRiskDesc;

  /// No description provided for @assistantSkillCenterHighRiskRequired.
  ///
  /// In zh, this message translates to:
  /// **'高风险动作必须保留二次确认'**
  String get assistantSkillCenterHighRiskRequired;

  /// No description provided for @assistantSkillCenterSceneGateTitle.
  ///
  /// In zh, this message translates to:
  /// **'场景闸门'**
  String get assistantSkillCenterSceneGateTitle;

  /// No description provided for @assistantSkillCenterSceneDiscovery.
  ///
  /// In zh, this message translates to:
  /// **'发现页'**
  String get assistantSkillCenterSceneDiscovery;

  /// No description provided for @assistantSkillCenterSceneDiscoveryDesc.
  ///
  /// In zh, this message translates to:
  /// **'浏览时仅轻提示，不主动打断'**
  String get assistantSkillCenterSceneDiscoveryDesc;

  /// No description provided for @assistantSkillCenterSceneCircle.
  ///
  /// In zh, this message translates to:
  /// **'圈子'**
  String get assistantSkillCenterSceneCircle;

  /// No description provided for @assistantSkillCenterSceneCircleDesc.
  ///
  /// In zh, this message translates to:
  /// **'圈内讨论建议按需触发'**
  String get assistantSkillCenterSceneCircleDesc;

  /// No description provided for @assistantSkillCenterSceneChat.
  ///
  /// In zh, this message translates to:
  /// **'趣聊'**
  String get assistantSkillCenterSceneChat;

  /// No description provided for @assistantSkillCenterSceneChatDesc.
  ///
  /// In zh, this message translates to:
  /// **'默认受邀参与（@小趣或手动点击）'**
  String get assistantSkillCenterSceneChatDesc;

  /// No description provided for @assistantSkillCenterSceneSystem.
  ///
  /// In zh, this message translates to:
  /// **'系统外场景'**
  String get assistantSkillCenterSceneSystem;

  /// No description provided for @assistantSkillCenterSceneSystemDesc.
  ///
  /// In zh, this message translates to:
  /// **'剪贴板、图片、外链等跨场景能力'**
  String get assistantSkillCenterSceneSystemDesc;

  /// No description provided for @assistantSkillCenterRecentSessionsTitle.
  ///
  /// In zh, this message translates to:
  /// **'最近会话'**
  String get assistantSkillCenterRecentSessionsTitle;

  /// No description provided for @assistantSkillCenterNoRecentSessions.
  ///
  /// In zh, this message translates to:
  /// **'暂无会话记录'**
  String get assistantSkillCenterNoRecentSessions;

  /// No description provided for @assistantSkillCenterMessagesCount.
  ///
  /// In zh, this message translates to:
  /// **'{count} 条消息'**
  String assistantSkillCenterMessagesCount(int count);

  /// No description provided for @assistantSkillCenterNoLastMessage.
  ///
  /// In zh, this message translates to:
  /// **'暂无最近消息'**
  String get assistantSkillCenterNoLastMessage;

  /// No description provided for @assistantSkillCenterAllSkillsTitle.
  ///
  /// In zh, this message translates to:
  /// **'全部技能'**
  String get assistantSkillCenterAllSkillsTitle;

  /// No description provided for @personaManage.
  ///
  /// In zh, this message translates to:
  /// **'管理分身'**
  String get personaManage;

  /// No description provided for @personaPrimary.
  ///
  /// In zh, this message translates to:
  /// **'主账号'**
  String get personaPrimary;

  /// No description provided for @myResonance.
  ///
  /// In zh, this message translates to:
  /// **'我的交集'**
  String get myResonance;

  /// No description provided for @profileEditLabel.
  ///
  /// In zh, this message translates to:
  /// **'资料编辑'**
  String get profileEditLabel;

  /// No description provided for @profilePersonasLabel.
  ///
  /// In zh, this message translates to:
  /// **'分身管理'**
  String get profilePersonasLabel;

  /// No description provided for @momentPlaceholder.
  ///
  /// In zh, this message translates to:
  /// **'这一刻的想法...'**
  String get momentPlaceholder;

  /// No description provided for @drafts.
  ///
  /// In zh, this message translates to:
  /// **'草稿箱'**
  String get drafts;

  /// No description provided for @postMoment.
  ///
  /// In zh, this message translates to:
  /// **'发微趣'**
  String get postMoment;

  /// No description provided for @postPhoto.
  ///
  /// In zh, this message translates to:
  /// **'发美图'**
  String get postPhoto;

  /// No description provided for @postVideo.
  ///
  /// In zh, this message translates to:
  /// **'发视频'**
  String get postVideo;

  /// No description provided for @postArticle.
  ///
  /// In zh, this message translates to:
  /// **'写文章'**
  String get postArticle;

  /// No description provided for @publish.
  ///
  /// In zh, this message translates to:
  /// **'发表'**
  String get publish;

  /// No description provided for @publishAction.
  ///
  /// In zh, this message translates to:
  /// **'发布'**
  String get publishAction;

  /// No description provided for @locationLabel.
  ///
  /// In zh, this message translates to:
  /// **'所在位置'**
  String get locationLabel;

  /// No description provided for @locationHidden.
  ///
  /// In zh, this message translates to:
  /// **'不显示位置'**
  String get locationHidden;

  /// No description provided for @isPublicLabel.
  ///
  /// In zh, this message translates to:
  /// **'是否公开'**
  String get isPublicLabel;

  /// No description provided for @visibilityPrivate.
  ///
  /// In zh, this message translates to:
  /// **'私密'**
  String get visibilityPrivate;

  /// No description provided for @selectPublishCirclesLabel.
  ///
  /// In zh, this message translates to:
  /// **'发布的圈子'**
  String get selectPublishCirclesLabel;

  /// No description provided for @noCirclesAvailable.
  ///
  /// In zh, this message translates to:
  /// **'加入圈子，发现同好'**
  String get noCirclesAvailable;

  /// No description provided for @circleJoinedSection.
  ///
  /// In zh, this message translates to:
  /// **'已加入'**
  String get circleJoinedSection;

  /// No description provided for @circleRecommendedSection.
  ///
  /// In zh, this message translates to:
  /// **'推荐加入'**
  String get circleRecommendedSection;

  /// No description provided for @circleMemberCountJoined.
  ///
  /// In zh, this message translates to:
  /// **'{count} 人 · 已加入'**
  String circleMemberCountJoined(int count);

  /// No description provided for @circleFollowButton.
  ///
  /// In zh, this message translates to:
  /// **'+ 关注'**
  String get circleFollowButton;

  /// No description provided for @circleRecommendedSubtitle.
  ///
  /// In zh, this message translates to:
  /// **'{reason} · {count} 人'**
  String circleRecommendedSubtitle(String reason, int count);

  /// No description provided for @circleJoinedLabel.
  ///
  /// In zh, this message translates to:
  /// **'已加入'**
  String get circleJoinedLabel;

  /// No description provided for @goToDiscovery.
  ///
  /// In zh, this message translates to:
  /// **'去发现'**
  String get goToDiscovery;

  /// No description provided for @locationNearbyTitle.
  ///
  /// In zh, this message translates to:
  /// **'附近位置'**
  String get locationNearbyTitle;

  /// No description provided for @locationFetchingResult.
  ///
  /// In zh, this message translates to:
  /// **'正在获取结果'**
  String get locationFetchingResult;

  /// No description provided for @locationSearchingNearby.
  ///
  /// In zh, this message translates to:
  /// **'正在搜索附近位置'**
  String get locationSearchingNearby;

  /// No description provided for @locationLoadFailed.
  ///
  /// In zh, this message translates to:
  /// **'暂时无法获取当前位置，请稍后重试'**
  String get locationLoadFailed;

  /// No description provided for @locationPermissionRequired.
  ///
  /// In zh, this message translates to:
  /// **'请开启定位权限后重试'**
  String get locationPermissionRequired;

  /// No description provided for @locationUpstreamTimeout.
  ///
  /// In zh, this message translates to:
  /// **'位置服务响应超时，请稍后重试'**
  String get locationUpstreamTimeout;

  /// No description provided for @locationInternalError.
  ///
  /// In zh, this message translates to:
  /// **'位置服务异常，请稍后重试'**
  String get locationInternalError;

  /// No description provided for @locationAppPermissionRequired.
  ///
  /// In zh, this message translates to:
  /// **'请在设置中为本应用开启定位权限'**
  String get locationAppPermissionRequired;

  /// No description provided for @locationOpenSettings.
  ///
  /// In zh, this message translates to:
  /// **'去设置'**
  String get locationOpenSettings;

  /// No description provided for @locationSearchTitle.
  ///
  /// In zh, this message translates to:
  /// **'搜索位置'**
  String get locationSearchTitle;

  /// No description provided for @locationSearchHint.
  ///
  /// In zh, this message translates to:
  /// **'搜索地点'**
  String get locationSearchHint;

  /// No description provided for @locationSearchEmpty.
  ///
  /// In zh, this message translates to:
  /// **'未找到相关位置'**
  String get locationSearchEmpty;

  /// No description provided for @locationSearchKeywordRequired.
  ///
  /// In zh, this message translates to:
  /// **'搜索关键词不能为空'**
  String get locationSearchKeywordRequired;

  /// No description provided for @remindWhoLabel.
  ///
  /// In zh, this message translates to:
  /// **'提醒谁看'**
  String get remindWhoLabel;

  /// No description provided for @whoCanSeeLabel.
  ///
  /// In zh, this message translates to:
  /// **'谁可以看'**
  String get whoCanSeeLabel;

  /// No description provided for @visibilityPublic.
  ///
  /// In zh, this message translates to:
  /// **'公开'**
  String get visibilityPublic;

  /// No description provided for @addCover.
  ///
  /// In zh, this message translates to:
  /// **'添加封面'**
  String get addCover;

  /// No description provided for @articleCoverOptionNone.
  ///
  /// In zh, this message translates to:
  /// **'无图封面'**
  String get articleCoverOptionNone;

  /// No description provided for @articleCoverOptionNoneDesc.
  ///
  /// In zh, this message translates to:
  /// **'不使用封面图'**
  String get articleCoverOptionNoneDesc;

  /// No description provided for @articleCoverOptionOne.
  ///
  /// In zh, this message translates to:
  /// **'一图封面'**
  String get articleCoverOptionOne;

  /// No description provided for @articleCoverOptionTwo.
  ///
  /// In zh, this message translates to:
  /// **'二图封面'**
  String get articleCoverOptionTwo;

  /// No description provided for @articleCoverOptionThree.
  ///
  /// In zh, this message translates to:
  /// **'三图封面'**
  String get articleCoverOptionThree;

  /// No description provided for @addImage.
  ///
  /// In zh, this message translates to:
  /// **'添加图片'**
  String get addImage;

  /// No description provided for @selectFromGallery.
  ///
  /// In zh, this message translates to:
  /// **'从相册选择'**
  String get selectFromGallery;

  /// No description provided for @editImage.
  ///
  /// In zh, this message translates to:
  /// **'编辑图片'**
  String get editImage;

  /// No description provided for @imageEditDone.
  ///
  /// In zh, this message translates to:
  /// **'完成'**
  String get imageEditDone;

  /// No description provided for @imageEditTools.
  ///
  /// In zh, this message translates to:
  /// **'工具'**
  String get imageEditTools;

  /// No description provided for @imageEditStyles.
  ///
  /// In zh, this message translates to:
  /// **'样式'**
  String get imageEditStyles;

  /// No description provided for @imageEditOriginal.
  ///
  /// In zh, this message translates to:
  /// **'原图'**
  String get imageEditOriginal;

  /// No description provided for @imageEditVivid.
  ///
  /// In zh, this message translates to:
  /// **'鲜艳'**
  String get imageEditVivid;

  /// No description provided for @imageEditWarm.
  ///
  /// In zh, this message translates to:
  /// **'暖色'**
  String get imageEditWarm;

  /// No description provided for @imageEditCool.
  ///
  /// In zh, this message translates to:
  /// **'冷色'**
  String get imageEditCool;

  /// No description provided for @imageEditMono.
  ///
  /// In zh, this message translates to:
  /// **'黑白'**
  String get imageEditMono;

  /// No description provided for @imageEditPortrait.
  ///
  /// In zh, this message translates to:
  /// **'人像'**
  String get imageEditPortrait;

  /// No description provided for @imageEditLandscape.
  ///
  /// In zh, this message translates to:
  /// **'风景'**
  String get imageEditLandscape;

  /// No description provided for @imageEditStillLife.
  ///
  /// In zh, this message translates to:
  /// **'静物'**
  String get imageEditStillLife;

  /// No description provided for @imageEditVintage.
  ///
  /// In zh, this message translates to:
  /// **'复古'**
  String get imageEditVintage;

  /// No description provided for @imageEditDrama.
  ///
  /// In zh, this message translates to:
  /// **'戏剧'**
  String get imageEditDrama;

  /// No description provided for @imageEditFaded.
  ///
  /// In zh, this message translates to:
  /// **'褪色'**
  String get imageEditFaded;

  /// No description provided for @imageEditNostalgic.
  ///
  /// In zh, this message translates to:
  /// **'怀旧'**
  String get imageEditNostalgic;

  /// No description provided for @imageEditCompare.
  ///
  /// In zh, this message translates to:
  /// **'对比'**
  String get imageEditCompare;

  /// No description provided for @imageEditorRotate.
  ///
  /// In zh, this message translates to:
  /// **'旋转'**
  String get imageEditorRotate;

  /// No description provided for @imageEditorCrop.
  ///
  /// In zh, this message translates to:
  /// **'裁剪'**
  String get imageEditorCrop;

  /// No description provided for @imageEditorFilter.
  ///
  /// In zh, this message translates to:
  /// **'滤镜'**
  String get imageEditorFilter;

  /// No description provided for @imageEditorBeauty.
  ///
  /// In zh, this message translates to:
  /// **'美颜'**
  String get imageEditorBeauty;

  /// No description provided for @imageEditorProTools.
  ///
  /// In zh, this message translates to:
  /// **'专业工具'**
  String get imageEditorProTools;

  /// No description provided for @imageEditorFrame.
  ///
  /// In zh, this message translates to:
  /// **'相框'**
  String get imageEditorFrame;

  /// No description provided for @imageEditorText.
  ///
  /// In zh, this message translates to:
  /// **'文字'**
  String get imageEditorText;

  /// No description provided for @imageEditorMosaic.
  ///
  /// In zh, this message translates to:
  /// **'马赛克'**
  String get imageEditorMosaic;

  /// No description provided for @imageEditorHistory.
  ///
  /// In zh, this message translates to:
  /// **'历史'**
  String get imageEditorHistory;

  /// No description provided for @imageEditorRemoveStep.
  ///
  /// In zh, this message translates to:
  /// **'删除步骤'**
  String get imageEditorRemoveStep;

  /// No description provided for @imageEditorRedoStep.
  ///
  /// In zh, this message translates to:
  /// **'重做'**
  String get imageEditorRedoStep;

  /// No description provided for @imageEditorCropFree.
  ///
  /// In zh, this message translates to:
  /// **'自由'**
  String get imageEditorCropFree;

  /// No description provided for @imageEditorCropOriginal.
  ///
  /// In zh, this message translates to:
  /// **'原始'**
  String get imageEditorCropOriginal;

  /// No description provided for @imageEditorCropRatio1x1.
  ///
  /// In zh, this message translates to:
  /// **'1:1'**
  String get imageEditorCropRatio1x1;

  /// No description provided for @imageEditorCropRatio2x3.
  ///
  /// In zh, this message translates to:
  /// **'2:3'**
  String get imageEditorCropRatio2x3;

  /// No description provided for @imageEditorCropRatio3x2.
  ///
  /// In zh, this message translates to:
  /// **'3:2'**
  String get imageEditorCropRatio3x2;

  /// No description provided for @imageEditorCropRatio3x4.
  ///
  /// In zh, this message translates to:
  /// **'3:4'**
  String get imageEditorCropRatio3x4;

  /// No description provided for @imageEditorCropRatio4x3.
  ///
  /// In zh, this message translates to:
  /// **'4:3'**
  String get imageEditorCropRatio4x3;

  /// No description provided for @imageEditorCropRatio9x16.
  ///
  /// In zh, this message translates to:
  /// **'9:16'**
  String get imageEditorCropRatio9x16;

  /// No description provided for @imageEditorCropRatio16x9.
  ///
  /// In zh, this message translates to:
  /// **'16:9'**
  String get imageEditorCropRatio16x9;

  /// No description provided for @imageEditorCropReset.
  ///
  /// In zh, this message translates to:
  /// **'重置'**
  String get imageEditorCropReset;

  /// No description provided for @imageEditorRotateRestore.
  ///
  /// In zh, this message translates to:
  /// **'还原'**
  String get imageEditorRotateRestore;

  /// No description provided for @imageEditorFilterRecommended.
  ///
  /// In zh, this message translates to:
  /// **'推荐'**
  String get imageEditorFilterRecommended;

  /// No description provided for @imageEditorFilterFrequent.
  ///
  /// In zh, this message translates to:
  /// **'常用'**
  String get imageEditorFilterFrequent;

  /// No description provided for @imageEditorFilterRemove.
  ///
  /// In zh, this message translates to:
  /// **'去滤镜'**
  String get imageEditorFilterRemove;

  /// No description provided for @imageEditorFilterQuality.
  ///
  /// In zh, this message translates to:
  /// **'画质'**
  String get imageEditorFilterQuality;

  /// No description provided for @imageEditorFilterSpring.
  ///
  /// In zh, this message translates to:
  /// **'春天'**
  String get imageEditorFilterSpring;

  /// No description provided for @imageEditorFilterVivid.
  ///
  /// In zh, this message translates to:
  /// **'鲜明'**
  String get imageEditorFilterVivid;

  /// No description provided for @imageEditorFilterHighSat.
  ///
  /// In zh, this message translates to:
  /// **'高饱和'**
  String get imageEditorFilterHighSat;

  /// No description provided for @imageEditorFilterDehaze.
  ///
  /// In zh, this message translates to:
  /// **'去灰'**
  String get imageEditorFilterDehaze;

  /// No description provided for @imageEditorProBrightness.
  ///
  /// In zh, this message translates to:
  /// **'亮度'**
  String get imageEditorProBrightness;

  /// No description provided for @imageEditorProLightSense.
  ///
  /// In zh, this message translates to:
  /// **'光感'**
  String get imageEditorProLightSense;

  /// No description provided for @imageEditorProContrast.
  ///
  /// In zh, this message translates to:
  /// **'对比度'**
  String get imageEditorProContrast;

  /// No description provided for @imageEditorProColorTemp.
  ///
  /// In zh, this message translates to:
  /// **'色温'**
  String get imageEditorProColorTemp;

  /// No description provided for @imageEditorProExposure.
  ///
  /// In zh, this message translates to:
  /// **'曝光'**
  String get imageEditorProExposure;

  /// No description provided for @imageEditorProSaturation.
  ///
  /// In zh, this message translates to:
  /// **'饱和度'**
  String get imageEditorProSaturation;

  /// No description provided for @imageEditorProNaturalSaturation.
  ///
  /// In zh, this message translates to:
  /// **'自然饱和度'**
  String get imageEditorProNaturalSaturation;

  /// No description provided for @imageEditorProTexture.
  ///
  /// In zh, this message translates to:
  /// **'纹理'**
  String get imageEditorProTexture;

  /// No description provided for @imageEditorProHighlight.
  ///
  /// In zh, this message translates to:
  /// **'高光'**
  String get imageEditorProHighlight;

  /// No description provided for @imageEditorProShadow.
  ///
  /// In zh, this message translates to:
  /// **'阴影'**
  String get imageEditorProShadow;

  /// No description provided for @imageEditorProAmbiance.
  ///
  /// In zh, this message translates to:
  /// **'氛围'**
  String get imageEditorProAmbiance;

  /// No description provided for @imageEditorProWarmth.
  ///
  /// In zh, this message translates to:
  /// **'暖色调'**
  String get imageEditorProWarmth;

  /// No description provided for @imageEditorProTone.
  ///
  /// In zh, this message translates to:
  /// **'色调'**
  String get imageEditorProTone;

  /// No description provided for @imageEditorProGrain.
  ///
  /// In zh, this message translates to:
  /// **'颗粒'**
  String get imageEditorProGrain;

  /// No description provided for @imageEditorProFade.
  ///
  /// In zh, this message translates to:
  /// **'褪色'**
  String get imageEditorProFade;

  /// No description provided for @imageEditorProDenoise.
  ///
  /// In zh, this message translates to:
  /// **'降噪'**
  String get imageEditorProDenoise;

  /// No description provided for @imageEditorProSharpen.
  ///
  /// In zh, this message translates to:
  /// **'锐化'**
  String get imageEditorProSharpen;

  /// No description provided for @imageEditorProUnsharpen.
  ///
  /// In zh, this message translates to:
  /// **'去锐化'**
  String get imageEditorProUnsharpen;

  /// No description provided for @imageEditorPanelPlaceholder.
  ///
  /// In zh, this message translates to:
  /// **'操作模版或内容'**
  String get imageEditorPanelPlaceholder;

  /// No description provided for @imageEditorBeautyNatural.
  ///
  /// In zh, this message translates to:
  /// **'自然'**
  String get imageEditorBeautyNatural;

  /// No description provided for @imageEditorBeautySoft.
  ///
  /// In zh, this message translates to:
  /// **'柔和'**
  String get imageEditorBeautySoft;

  /// No description provided for @imageEditorBeautyClear.
  ///
  /// In zh, this message translates to:
  /// **'清透'**
  String get imageEditorBeautyClear;

  /// No description provided for @imageEditorTextPlaceholder.
  ///
  /// In zh, this message translates to:
  /// **'点击输入文字'**
  String get imageEditorTextPlaceholder;

  /// No description provided for @imageEditorTextStyle.
  ///
  /// In zh, this message translates to:
  /// **'样式'**
  String get imageEditorTextStyle;

  /// No description provided for @imageEditorTextColor.
  ///
  /// In zh, this message translates to:
  /// **'颜色'**
  String get imageEditorTextColor;

  /// No description provided for @imageEditorMosaicPixel.
  ///
  /// In zh, this message translates to:
  /// **'像素'**
  String get imageEditorMosaicPixel;

  /// No description provided for @imageEditorMosaicBlur.
  ///
  /// In zh, this message translates to:
  /// **'模糊'**
  String get imageEditorMosaicBlur;

  /// No description provided for @imageEditorMosaicBrush.
  ///
  /// In zh, this message translates to:
  /// **'画笔'**
  String get imageEditorMosaicBrush;

  /// No description provided for @imageEditorMosaicSize.
  ///
  /// In zh, this message translates to:
  /// **'大小'**
  String get imageEditorMosaicSize;

  /// No description provided for @imageEditorFrameSimple.
  ///
  /// In zh, this message translates to:
  /// **'简洁'**
  String get imageEditorFrameSimple;

  /// No description provided for @imageEditorFrameFilm.
  ///
  /// In zh, this message translates to:
  /// **'胶片'**
  String get imageEditorFrameFilm;

  /// No description provided for @imageEditorFrameWhite.
  ///
  /// In zh, this message translates to:
  /// **'留白'**
  String get imageEditorFrameWhite;

  /// No description provided for @imageEditorProCurve.
  ///
  /// In zh, this message translates to:
  /// **'曲线'**
  String get imageEditorProCurve;

  /// No description provided for @imageEditorProWhiteBalance.
  ///
  /// In zh, this message translates to:
  /// **'白平衡'**
  String get imageEditorProWhiteBalance;

  /// No description provided for @imageEditorProLocal.
  ///
  /// In zh, this message translates to:
  /// **'局部'**
  String get imageEditorProLocal;

  /// No description provided for @imageEditorProHeal.
  ///
  /// In zh, this message translates to:
  /// **'修复'**
  String get imageEditorProHeal;

  /// No description provided for @imageEditorProGlamourGlow.
  ///
  /// In zh, this message translates to:
  /// **'美丽光晕'**
  String get imageEditorProGlamourGlow;

  /// No description provided for @imageEditorProToneContrast.
  ///
  /// In zh, this message translates to:
  /// **'色调对比度'**
  String get imageEditorProToneContrast;

  /// No description provided for @imageEditorProHsl.
  ///
  /// In zh, this message translates to:
  /// **'HSL'**
  String get imageEditorProHsl;

  /// No description provided for @imageEditorProAdjustImage.
  ///
  /// In zh, this message translates to:
  /// **'调整图片'**
  String get imageEditorProAdjustImage;

  /// No description provided for @imageEditorProPerspective.
  ///
  /// In zh, this message translates to:
  /// **'视角'**
  String get imageEditorProPerspective;

  /// No description provided for @imageEditorProTabOverall.
  ///
  /// In zh, this message translates to:
  /// **'调整图片'**
  String get imageEditorProTabOverall;

  /// No description provided for @imageEditorProTabLocal.
  ///
  /// In zh, this message translates to:
  /// **'局部'**
  String get imageEditorProTabLocal;

  /// No description provided for @imageEditorProTabBase.
  ///
  /// In zh, this message translates to:
  /// **'调整图片'**
  String get imageEditorProTabBase;

  /// No description provided for @imageEditorProTabHsl.
  ///
  /// In zh, this message translates to:
  /// **'HSL'**
  String get imageEditorProTabHsl;

  /// No description provided for @imageEditorProTabCurve.
  ///
  /// In zh, this message translates to:
  /// **'曲线'**
  String get imageEditorProTabCurve;

  /// No description provided for @imageEditorProTabBwLevels.
  ///
  /// In zh, this message translates to:
  /// **'黑白色阶'**
  String get imageEditorProTabBwLevels;

  /// No description provided for @imageEditorProPlaceholderHsl.
  ///
  /// In zh, this message translates to:
  /// **'HSL 即将支持'**
  String get imageEditorProPlaceholderHsl;

  /// No description provided for @imageEditorProPlaceholderLocal.
  ///
  /// In zh, this message translates to:
  /// **'点击添加锚点开始局部调节'**
  String get imageEditorProPlaceholderLocal;

  /// No description provided for @imageEditorProPlaceholderCurve.
  ///
  /// In zh, this message translates to:
  /// **'曲线 即将支持'**
  String get imageEditorProPlaceholderCurve;

  /// No description provided for @imageEditorProPlaceholderBwLevels.
  ///
  /// In zh, this message translates to:
  /// **'黑白色阶 即将支持'**
  String get imageEditorProPlaceholderBwLevels;

  /// No description provided for @imageEditorProHue.
  ///
  /// In zh, this message translates to:
  /// **'色相'**
  String get imageEditorProHue;

  /// No description provided for @imageEditorProLuminance.
  ///
  /// In zh, this message translates to:
  /// **'明度'**
  String get imageEditorProLuminance;

  /// No description provided for @imageEditorProStructure.
  ///
  /// In zh, this message translates to:
  /// **'结构'**
  String get imageEditorProStructure;

  /// No description provided for @imageEditorProWhiteLevel.
  ///
  /// In zh, this message translates to:
  /// **'白色色阶'**
  String get imageEditorProWhiteLevel;

  /// No description provided for @imageEditorProBlackLevel.
  ///
  /// In zh, this message translates to:
  /// **'黑色色阶'**
  String get imageEditorProBlackLevel;

  /// No description provided for @imageEditorProAnchorAdd.
  ///
  /// In zh, this message translates to:
  /// **'添加局部'**
  String get imageEditorProAnchorAdd;

  /// No description provided for @imageEditorProAnchorShowAll.
  ///
  /// In zh, this message translates to:
  /// **'显隐局部'**
  String get imageEditorProAnchorShowAll;

  /// No description provided for @imageEditorProAnchorRange.
  ///
  /// In zh, this message translates to:
  /// **'显隐范围'**
  String get imageEditorProAnchorRange;

  /// No description provided for @imageEditorProAnchorShow.
  ///
  /// In zh, this message translates to:
  /// **'显示局部'**
  String get imageEditorProAnchorShow;

  /// No description provided for @imageEditorProAnchorHide.
  ///
  /// In zh, this message translates to:
  /// **'隐藏局部'**
  String get imageEditorProAnchorHide;

  /// No description provided for @imageEditorProAnchorRangeShow.
  ///
  /// In zh, this message translates to:
  /// **'显示范围'**
  String get imageEditorProAnchorRangeShow;

  /// No description provided for @imageEditorProAnchorRangeHide.
  ///
  /// In zh, this message translates to:
  /// **'隐藏范围'**
  String get imageEditorProAnchorRangeHide;

  /// No description provided for @imageEditorProAnchorCopy.
  ///
  /// In zh, this message translates to:
  /// **'复制'**
  String get imageEditorProAnchorCopy;

  /// No description provided for @imageEditorProAnchorDelete.
  ///
  /// In zh, this message translates to:
  /// **'删除'**
  String get imageEditorProAnchorDelete;

  /// No description provided for @imageEditorProAnchorLimitReached.
  ///
  /// In zh, this message translates to:
  /// **'局部锚点最多可添加10个'**
  String get imageEditorProAnchorLimitReached;

  /// No description provided for @imageEditorProAnchorScaleHint.
  ///
  /// In zh, this message translates to:
  /// **'可缩放局部位置以调节范围大小'**
  String get imageEditorProAnchorScaleHint;

  /// No description provided for @imageEditorProAnchorSelectHint.
  ///
  /// In zh, this message translates to:
  /// **'请先添加或选择局部锚点'**
  String get imageEditorProAnchorSelectHint;

  /// No description provided for @imageEditorProAnchorLetterBrightness.
  ///
  /// In zh, this message translates to:
  /// **'亮'**
  String get imageEditorProAnchorLetterBrightness;

  /// No description provided for @imageEditorProAnchorLetterContrast.
  ///
  /// In zh, this message translates to:
  /// **'对'**
  String get imageEditorProAnchorLetterContrast;

  /// No description provided for @imageEditorProAnchorLetterSaturation.
  ///
  /// In zh, this message translates to:
  /// **'饱'**
  String get imageEditorProAnchorLetterSaturation;

  /// No description provided for @imageEditorProAnchorLetterStructure.
  ///
  /// In zh, this message translates to:
  /// **'结'**
  String get imageEditorProAnchorLetterStructure;

  /// No description provided for @imageEditorProChannelRed.
  ///
  /// In zh, this message translates to:
  /// **'红'**
  String get imageEditorProChannelRed;

  /// No description provided for @imageEditorProChannelOrange.
  ///
  /// In zh, this message translates to:
  /// **'橙'**
  String get imageEditorProChannelOrange;

  /// No description provided for @imageEditorProChannelYellow.
  ///
  /// In zh, this message translates to:
  /// **'黄'**
  String get imageEditorProChannelYellow;

  /// No description provided for @imageEditorProChannelGreen.
  ///
  /// In zh, this message translates to:
  /// **'绿'**
  String get imageEditorProChannelGreen;

  /// No description provided for @imageEditorProChannelCyan.
  ///
  /// In zh, this message translates to:
  /// **'青'**
  String get imageEditorProChannelCyan;

  /// No description provided for @imageEditorProChannelBlue.
  ///
  /// In zh, this message translates to:
  /// **'蓝'**
  String get imageEditorProChannelBlue;

  /// No description provided for @imageEditorProChannelPurple.
  ///
  /// In zh, this message translates to:
  /// **'紫'**
  String get imageEditorProChannelPurple;

  /// No description provided for @imageEditorProChannelMagenta.
  ///
  /// In zh, this message translates to:
  /// **'洋红'**
  String get imageEditorProChannelMagenta;

  /// No description provided for @imageEditorProColorPicker.
  ///
  /// In zh, this message translates to:
  /// **'取色器'**
  String get imageEditorProColorPicker;

  /// No description provided for @imageEditorProBwLevels.
  ///
  /// In zh, this message translates to:
  /// **'黑白色阶'**
  String get imageEditorProBwLevels;

  /// No description provided for @imageEditorRotateLeft90.
  ///
  /// In zh, this message translates to:
  /// **'向左90°'**
  String get imageEditorRotateLeft90;

  /// No description provided for @imageEditorRotateRight90.
  ///
  /// In zh, this message translates to:
  /// **'向右90°'**
  String get imageEditorRotateRight90;

  /// No description provided for @imageEditorFlipHorizontal.
  ///
  /// In zh, this message translates to:
  /// **'水平翻转'**
  String get imageEditorFlipHorizontal;

  /// No description provided for @imageEditorFlipVertical.
  ///
  /// In zh, this message translates to:
  /// **'垂直翻转'**
  String get imageEditorFlipVertical;

  /// No description provided for @imageSavedSuccess.
  ///
  /// In zh, this message translates to:
  /// **'保存图片成功'**
  String get imageSavedSuccess;

  /// No description provided for @momentImageReorderHint.
  ///
  /// In zh, this message translates to:
  /// **'拖动图片可以调整顺序，点击可以编辑图片'**
  String get momentImageReorderHint;

  /// No description provided for @momentPublished.
  ///
  /// In zh, this message translates to:
  /// **'已发表'**
  String get momentPublished;

  /// No description provided for @articleCoverLabel.
  ///
  /// In zh, this message translates to:
  /// **'封面图'**
  String get articleCoverLabel;

  /// No description provided for @noDraft.
  ///
  /// In zh, this message translates to:
  /// **'暂无草稿'**
  String get noDraft;

  /// No description provided for @saveDraftConfirm.
  ///
  /// In zh, this message translates to:
  /// **'保存草稿？'**
  String get saveDraftConfirm;

  /// No description provided for @saveDraftHint.
  ///
  /// In zh, this message translates to:
  /// **'如果不保存，当前编辑的内容将会丢失。'**
  String get saveDraftHint;

  /// No description provided for @discardAndExit.
  ///
  /// In zh, this message translates to:
  /// **'放弃并退出'**
  String get discardAndExit;

  /// No description provided for @saveAndExit.
  ///
  /// In zh, this message translates to:
  /// **'保存并退出'**
  String get saveAndExit;

  /// No description provided for @draftCount.
  ///
  /// In zh, this message translates to:
  /// **'草稿箱'**
  String get draftCount;

  /// No description provided for @draftMoment.
  ///
  /// In zh, this message translates to:
  /// **'微趣草稿'**
  String get draftMoment;

  /// No description provided for @draftPhoto.
  ///
  /// In zh, this message translates to:
  /// **'美图草稿'**
  String get draftPhoto;

  /// No description provided for @draftVideo.
  ///
  /// In zh, this message translates to:
  /// **'视频草稿'**
  String get draftVideo;

  /// No description provided for @draftArticle.
  ///
  /// In zh, this message translates to:
  /// **'文章草稿'**
  String get draftArticle;

  /// No description provided for @unlabeled.
  ///
  /// In zh, this message translates to:
  /// **'[未填写]'**
  String get unlabeled;

  /// No description provided for @createTitleHint.
  ///
  /// In zh, this message translates to:
  /// **'标题'**
  String get createTitleHint;

  /// No description provided for @createDescriptionHint.
  ///
  /// In zh, this message translates to:
  /// **'描述'**
  String get createDescriptionHint;

  /// No description provided for @createVideoTitleHint.
  ///
  /// In zh, this message translates to:
  /// **'视频标题'**
  String get createVideoTitleHint;

  /// No description provided for @createArticleBodyHint.
  ///
  /// In zh, this message translates to:
  /// **'正文...'**
  String get createArticleBodyHint;

  /// No description provided for @photoTitleHint.
  ///
  /// In zh, this message translates to:
  /// **'添加作品标题...'**
  String get photoTitleHint;

  /// No description provided for @photoBodyHint.
  ///
  /// In zh, this message translates to:
  /// **'添加作品配文...'**
  String get photoBodyHint;

  /// No description provided for @photoReorderHint.
  ///
  /// In zh, this message translates to:
  /// **'长按拖动调整顺序'**
  String get photoReorderHint;

  /// No description provided for @photoTapToEdit.
  ///
  /// In zh, this message translates to:
  /// **'点击编辑'**
  String get photoTapToEdit;

  /// No description provided for @photoAddLabel.
  ///
  /// In zh, this message translates to:
  /// **'添加图片作品'**
  String get photoAddLabel;

  /// No description provided for @photoShowMorePictures.
  ///
  /// In zh, this message translates to:
  /// **'显示更多图片'**
  String get photoShowMorePictures;

  /// No description provided for @photoCollapseLabel.
  ///
  /// In zh, this message translates to:
  /// **'收起'**
  String get photoCollapseLabel;

  /// No description provided for @videoShortTypeName.
  ///
  /// In zh, this message translates to:
  /// **'视频'**
  String get videoShortTypeName;

  /// No description provided for @videoTitlePlaceholder.
  ///
  /// In zh, this message translates to:
  /// **'视频标题'**
  String get videoTitlePlaceholder;

  /// No description provided for @videoDescPlaceholder.
  ///
  /// In zh, this message translates to:
  /// **'添加视频描述...'**
  String get videoDescPlaceholder;

  /// No description provided for @videoUploadLabel.
  ///
  /// In zh, this message translates to:
  /// **'上传视频'**
  String get videoUploadLabel;

  /// No description provided for @videoUploadHint.
  ///
  /// In zh, this message translates to:
  /// **''**
  String get videoUploadHint;

  /// No description provided for @videoChangeCover.
  ///
  /// In zh, this message translates to:
  /// **'更换封面'**
  String get videoChangeCover;

  /// No description provided for @videoNoVideo.
  ///
  /// In zh, this message translates to:
  /// **'暂无视频'**
  String get videoNoVideo;

  /// No description provided for @videoDurationTooLong.
  ///
  /// In zh, this message translates to:
  /// **'视频时长超过1小时，请重新选择'**
  String get videoDurationTooLong;

  /// No description provided for @mediaPickerAlbumAll.
  ///
  /// In zh, this message translates to:
  /// **'全部'**
  String get mediaPickerAlbumAll;

  /// No description provided for @mediaPickerCategoryAll.
  ///
  /// In zh, this message translates to:
  /// **'全部'**
  String get mediaPickerCategoryAll;

  /// No description provided for @mediaPickerCategoryVideo.
  ///
  /// In zh, this message translates to:
  /// **'视频'**
  String get mediaPickerCategoryVideo;

  /// No description provided for @mediaPickerCategoryPhoto.
  ///
  /// In zh, this message translates to:
  /// **'照片'**
  String get mediaPickerCategoryPhoto;

  /// No description provided for @mediaPickerCategoryLive.
  ///
  /// In zh, this message translates to:
  /// **'实况图'**
  String get mediaPickerCategoryLive;

  /// No description provided for @mediaPickerCategoryFullscreen.
  ///
  /// In zh, this message translates to:
  /// **'全屏图'**
  String get mediaPickerCategoryFullscreen;

  /// No description provided for @mediaPickerCameraEntry.
  ///
  /// In zh, this message translates to:
  /// **'拍摄'**
  String get mediaPickerCameraEntry;

  /// No description provided for @mediaPickerOneTapMovie.
  ///
  /// In zh, this message translates to:
  /// **'一键成片'**
  String get mediaPickerOneTapMovie;

  /// No description provided for @mediaPickerOneTapMovieQueued.
  ///
  /// In zh, this message translates to:
  /// **'已加入一键成片，请在发视频页继续'**
  String get mediaPickerOneTapMovieQueued;

  /// No description provided for @mediaPickerNextStep.
  ///
  /// In zh, this message translates to:
  /// **'下一步'**
  String get mediaPickerNextStep;

  /// No description provided for @mediaPickerOverLimit.
  ///
  /// In zh, this message translates to:
  /// **'已达到可选数量上限'**
  String get mediaPickerOverLimit;

  /// No description provided for @mediaPickerPermissionDenied.
  ///
  /// In zh, this message translates to:
  /// **'请允许相册访问权限后再选择媒体'**
  String get mediaPickerPermissionDenied;

  /// No description provided for @mediaPickerImageOnly.
  ///
  /// In zh, this message translates to:
  /// **'当前入口仅支持选择图片'**
  String get mediaPickerImageOnly;

  /// No description provided for @cameraUnavailable.
  ///
  /// In zh, this message translates to:
  /// **'相机不可用'**
  String get cameraUnavailable;

  /// No description provided for @cameraCaptureFailed.
  ///
  /// In zh, this message translates to:
  /// **'拍摄失败，请重试'**
  String get cameraCaptureFailed;

  /// No description provided for @cameraPhotoMode.
  ///
  /// In zh, this message translates to:
  /// **'拍照'**
  String get cameraPhotoMode;

  /// No description provided for @cameraVideoMode.
  ///
  /// In zh, this message translates to:
  /// **'录像'**
  String get cameraVideoMode;

  /// No description provided for @articleTitlePlaceholder.
  ///
  /// In zh, this message translates to:
  /// **'请输入标题'**
  String get articleTitlePlaceholder;

  /// No description provided for @reward.
  ///
  /// In zh, this message translates to:
  /// **'打赏'**
  String get reward;

  /// No description provided for @save.
  ///
  /// In zh, this message translates to:
  /// **'保存'**
  String get save;

  /// No description provided for @message.
  ///
  /// In zh, this message translates to:
  /// **'私信'**
  String get message;

  /// No description provided for @viewOriginal.
  ///
  /// In zh, this message translates to:
  /// **'查看原图'**
  String get viewOriginal;

  /// No description provided for @fontSettings.
  ///
  /// In zh, this message translates to:
  /// **'字体设置'**
  String get fontSettings;

  /// No description provided for @darkMode.
  ///
  /// In zh, this message translates to:
  /// **'夜间模式'**
  String get darkMode;

  /// No description provided for @lightMode.
  ///
  /// In zh, this message translates to:
  /// **'日间模式'**
  String get lightMode;

  /// No description provided for @feedback.
  ///
  /// In zh, this message translates to:
  /// **'功能反馈'**
  String get feedback;

  /// No description provided for @notInterested.
  ///
  /// In zh, this message translates to:
  /// **'不感兴趣'**
  String get notInterested;

  /// No description provided for @notInterestedDescription.
  ///
  /// In zh, this message translates to:
  /// **'减少此类内容'**
  String get notInterestedDescription;

  /// No description provided for @blockUser.
  ///
  /// In zh, this message translates to:
  /// **'不喜欢该作者'**
  String get blockUser;

  /// No description provided for @blockUserDescription.
  ///
  /// In zh, this message translates to:
  /// **'消失吧'**
  String get blockUserDescription;

  /// No description provided for @blockWords.
  ///
  /// In zh, this message translates to:
  /// **'屏蔽词'**
  String get blockWords;

  /// No description provided for @blockWordsDescription.
  ///
  /// In zh, this message translates to:
  /// **'过滤内容'**
  String get blockWordsDescription;

  /// No description provided for @menuComplaint.
  ///
  /// In zh, this message translates to:
  /// **'投诉'**
  String get menuComplaint;

  /// No description provided for @reportDescription.
  ///
  /// In zh, this message translates to:
  /// **'内容质量差等'**
  String get reportDescription;

  /// No description provided for @moreActionsTitle.
  ///
  /// In zh, this message translates to:
  /// **'更多功能'**
  String get moreActionsTitle;

  /// No description provided for @imageActionsTitle.
  ///
  /// In zh, this message translates to:
  /// **'图片功能'**
  String get imageActionsTitle;

  /// No description provided for @linkCopied.
  ///
  /// In zh, this message translates to:
  /// **'链接已复制'**
  String get linkCopied;

  /// No description provided for @likes.
  ///
  /// In zh, this message translates to:
  /// **'点赞'**
  String get likes;

  /// No description provided for @viewAllComments.
  ///
  /// In zh, this message translates to:
  /// **'查看全部'**
  String get viewAllComments;

  /// No description provided for @comments.
  ///
  /// In zh, this message translates to:
  /// **'评论'**
  String get comments;

  /// No description provided for @justNow.
  ///
  /// In zh, this message translates to:
  /// **'刚刚'**
  String get justNow;

  /// No description provided for @minutesAgo.
  ///
  /// In zh, this message translates to:
  /// **'分钟前'**
  String get minutesAgo;

  /// No description provided for @hoursAgo.
  ///
  /// In zh, this message translates to:
  /// **'小时前'**
  String get hoursAgo;

  /// No description provided for @daysAgo.
  ///
  /// In zh, this message translates to:
  /// **'天前'**
  String get daysAgo;

  /// No description provided for @monthDay.
  ///
  /// In zh, this message translates to:
  /// **'月'**
  String get monthDay;

  /// No description provided for @tenThousandPlus.
  ///
  /// In zh, this message translates to:
  /// **'10万+'**
  String get tenThousandPlus;

  /// No description provided for @likeSuccess.
  ///
  /// In zh, this message translates to:
  /// **'点赞成功'**
  String get likeSuccess;

  /// No description provided for @unableToLoadImage.
  ///
  /// In zh, this message translates to:
  /// **'无法加载图片'**
  String get unableToLoadImage;

  /// No description provided for @back.
  ///
  /// In zh, this message translates to:
  /// **'返回'**
  String get back;

  /// Comment count label in article detail
  ///
  /// In zh, this message translates to:
  /// **'全部评论 {count}'**
  String allCommentsCount(int count);

  /// Relative time: N hours ago
  ///
  /// In zh, this message translates to:
  /// **'{delta}小时前'**
  String hoursAgoTemplate(int delta);

  /// Relative time: N minutes ago
  ///
  /// In zh, this message translates to:
  /// **'{delta}分钟前'**
  String minutesAgoTemplate(int delta);

  /// Relative time: N days ago
  ///
  /// In zh, this message translates to:
  /// **'{delta}天前'**
  String daysAgoTemplate(int delta);

  /// Date display: month/day
  ///
  /// In zh, this message translates to:
  /// **'{month}月{day}日'**
  String monthDayTemplate(int month, int day);

  /// No description provided for @articleNotFound.
  ///
  /// In zh, this message translates to:
  /// **'未找到该文章'**
  String get articleNotFound;

  /// No description provided for @anonymous.
  ///
  /// In zh, this message translates to:
  /// **'匿名'**
  String get anonymous;

  /// No description provided for @officialAccount.
  ///
  /// In zh, this message translates to:
  /// **'官方账号'**
  String get officialAccount;

  /// No description provided for @seniorCreator.
  ///
  /// In zh, this message translates to:
  /// **'资深创作者'**
  String get seniorCreator;

  /// No description provided for @copyrightNotice.
  ///
  /// In zh, this message translates to:
  /// **'著作权归作者所有'**
  String get copyrightNotice;

  /// No description provided for @commercialReproductionNotice.
  ///
  /// In zh, this message translates to:
  /// **'商业转载请联系作者获得授权'**
  String get commercialReproductionNotice;

  /// No description provided for @sortByHot.
  ///
  /// In zh, this message translates to:
  /// **'最热'**
  String get sortByHot;

  /// No description provided for @sortByNew.
  ///
  /// In zh, this message translates to:
  /// **'最新'**
  String get sortByNew;

  /// No description provided for @unknownError.
  ///
  /// In zh, this message translates to:
  /// **'未知错误'**
  String get unknownError;

  /// No description provided for @circles.
  ///
  /// In zh, this message translates to:
  /// **'圈子'**
  String get circles;

  /// No description provided for @fans.
  ///
  /// In zh, this message translates to:
  /// **'粉丝'**
  String get fans;

  /// No description provided for @blockUserAction.
  ///
  /// In zh, this message translates to:
  /// **'屏蔽用户'**
  String get blockUserAction;

  /// No description provided for @likedTheirPhotoOrArticle.
  ///
  /// In zh, this message translates to:
  /// **'赞了 Ta 的照片/文章'**
  String get likedTheirPhotoOrArticle;

  /// No description provided for @theyLikedOthersArticle.
  ///
  /// In zh, this message translates to:
  /// **'Ta 赞了 他人 的文章'**
  String get theyLikedOthersArticle;

  /// No description provided for @commentedOnTheirPhoto.
  ///
  /// In zh, this message translates to:
  /// **'评论了 Ta 的照片'**
  String get commentedOnTheirPhoto;

  /// No description provided for @theyCommentedOnOthersPhoto.
  ///
  /// In zh, this message translates to:
  /// **'Ta 评论了 他人 的照片'**
  String get theyCommentedOnOthersPhoto;

  /// No description provided for @likedTheirContent.
  ///
  /// In zh, this message translates to:
  /// **'赞了 Ta 的内容'**
  String get likedTheirContent;

  /// No description provided for @commentedOnTheirContent.
  ///
  /// In zh, this message translates to:
  /// **'评论了 Ta 的内容'**
  String get commentedOnTheirContent;

  /// No description provided for @noInteractionContent.
  ///
  /// In zh, this message translates to:
  /// **'暂无互动内容'**
  String get noInteractionContent;

  /// No description provided for @emptyBio.
  ///
  /// In zh, this message translates to:
  /// **'这个人很懒，什么都没有写'**
  String get emptyBio;

  /// No description provided for @resonanceDetail.
  ///
  /// In zh, this message translates to:
  /// **'交集详情'**
  String get resonanceDetail;

  /// No description provided for @youHave.
  ///
  /// In zh, this message translates to:
  /// **'你们有'**
  String get youHave;

  /// No description provided for @resonanceSuffix.
  ///
  /// In zh, this message translates to:
  /// **'个交集点'**
  String get resonanceSuffix;

  /// No description provided for @articleContent.
  ///
  /// In zh, this message translates to:
  /// **'文章内容'**
  String get articleContent;

  /// No description provided for @photoContent.
  ///
  /// In zh, this message translates to:
  /// **'图片内容'**
  String get photoContent;

  /// No description provided for @videoContent.
  ///
  /// In zh, this message translates to:
  /// **'视频内容'**
  String get videoContent;

  /// No description provided for @dynamicContent.
  ///
  /// In zh, this message translates to:
  /// **'动态内容'**
  String get dynamicContent;

  /// No description provided for @interactionContent.
  ///
  /// In zh, this message translates to:
  /// **'互动内容'**
  String get interactionContent;

  /// No description provided for @footprint.
  ///
  /// In zh, this message translates to:
  /// **'足迹'**
  String get footprint;

  /// No description provided for @soulContent.
  ///
  /// In zh, this message translates to:
  /// **'书影音'**
  String get soulContent;

  /// No description provided for @tasteBuds.
  ///
  /// In zh, this message translates to:
  /// **'味蕾'**
  String get tasteBuds;

  /// No description provided for @privateItems.
  ///
  /// In zh, this message translates to:
  /// **'爱物'**
  String get privateItems;

  /// No description provided for @taReceived.
  ///
  /// In zh, this message translates to:
  /// **'Ta收到'**
  String get taReceived;

  /// No description provided for @taSent.
  ///
  /// In zh, this message translates to:
  /// **'Ta发出'**
  String get taSent;

  /// No description provided for @userNotFound.
  ///
  /// In zh, this message translates to:
  /// **'用户不存在'**
  String get userNotFound;

  /// No description provided for @loadUserDataFailed.
  ///
  /// In zh, this message translates to:
  /// **'加载用户数据失败'**
  String get loadUserDataFailed;

  /// No description provided for @userBlocked.
  ///
  /// In zh, this message translates to:
  /// **'已屏蔽用户'**
  String get userBlocked;

  /// No description provided for @featureComingSoon.
  ///
  /// In zh, this message translates to:
  /// **'功能开发中...'**
  String get featureComingSoon;

  /// Like count display in work card
  ///
  /// In zh, this message translates to:
  /// **'{count} 获赞'**
  String likedCountLabel(int count);

  /// Expand N replies button text in comment thread
  ///
  /// In zh, this message translates to:
  /// **'展开 {count} 条回复'**
  String expandRepliesTemplate(int count);

  /// Reply-to prefix between usernames in comment thread (with spaces)
  ///
  /// In zh, this message translates to:
  /// **' 回复 '**
  String get replyToPrefix;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en', 'zh'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return AppLocalizationsEn();
    case 'zh':
      return AppLocalizationsZh();
  }

  throw FlutterError(
    'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
