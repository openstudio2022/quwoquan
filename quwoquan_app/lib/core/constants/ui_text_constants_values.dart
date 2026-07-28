part of 'ui_text_constants.dart';

/// 跨语义域的少量动态文案入口；静态文案由同一 library 的领域类持有。
class UITextConstants {
  static const String permissionContactsPrimerMessage =
      '发现已注册联系人需要访问通讯录。点「继续」后，请在系统弹窗中选择「允许」。';
  static const String cameraPermissionPrimerMessage =
      '拍照或录像需要使用相机。点「继续」后，请在系统弹窗中选择「允许」。';

  static String homeChannelMoodCopy(String moodCopyKey) =>
      _homeChannelMoodCopy(moodCopyKey);
  static String homeChannelLabel(String labelKey) =>
      _homeChannelLabel(labelKey);
  static String homeObjectActionLabel(String actionType) =>
      _homeObjectActionLabel(actionType);
  static String homeObjectSharedCount(int count) =>
      _homeObjectSharedCount(count);
  static String webPcPrimaryLabel(String routeName) =>
      _webPcPrimaryLabel(routeName);
  static String footprintTypeLabel(String type) => _footprintTypeLabel(type);
  static String pageLoadingA11y(String surface) => '正在加载$surface';
  static String searchTabResults(String tabLabel) => '$tabLabel结果';
  static String searchDateMonthDay(int month, int day) => '$month月$day日';
  static String searchCircleInspirationSubtitle(int count, String detail) =>
      '$count人 · $detail';
  static String searchLocationDiscoverySubtitle(
    String location,
    int ratingCount,
  ) => ratingCount > 0 ? '$location · $ratingCount条评价' : location;
  static String searchNoResultsForQuery(String query) => query.trim().isEmpty
      ? SearchText.searchEmptyResult
      : '没有找到“${query.trim()}”的结果';
  static String searchNoIntersectionForQuery(String query) =>
      query.trim().isEmpty
      ? SearchText.searchNoIntersectionResults
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
  static String sectionLoadFailedTitle(String section) => '$section没加载出来';
  static String blockKeywordConfirmLabel(String keyword) => '屏蔽“$keyword”';
  static String blockKeywordConfirmMessage(String keyword) =>
      '确认后将减少包含“$keyword”的内容，可在设置中随时移除。';
  static String shareCircleConfirmTitle(String circleName) =>
      '转发到“$circleName”？';
  static String shareSeedVideoWorkTitle(String displayName) =>
      '$displayName 的视频作品';
  static String shareSeedImageWorkTitle(String displayName) =>
      '$displayName 的图片作品';
  static String shareSeedMomentTitle(String displayName) => '$displayName 的点滴';
  static String entityEstablishedYearLabel(int year) => '$year 年创立';
  static String entityFollowerCountLabel(String formattedCount) =>
      '$formattedCount ${FoundationText.follow}';
  static String videoSeriesProgress(int current, int total) =>
      '视频集 · $current/$total';
  static String workArticlePageProgress(int current, int total) =>
      '$current / $total';
  static String homepageDiscussionSectionTitleFor(String objectName) =>
      '大家在聊$objectName';
  static String homepageRatingScore(String score) => '$score 分';
  static String homepageRatingCount(int count) => '$count 条评分';
  static String objectIntroTitle(String objectName) => '认识$objectName';
  static String objectIntroDiscussionCount(int count) => '$count 人讨论';
  static String objectIntroContinueTitle(String objectName) =>
      '继续了解 $objectName';
  static String objectIntroSourcePlatform(String sourceKind) =>
      _objectIntroSourcePlatform(sourceKind);
  static String settingsPendingSync(String value) => '$value · 待同步';
  static String settingsVersionValue(String value) => value;
  static String circleInviteShareText(String circleName) =>
      '邀请你加入圈子「$circleName」';
  static String circleShareSubject(String circleName) => '圈子「$circleName」';
  static String callConfirmSelected(int count) => '确定 ($count)';
  static String callSelectedCount(int count) => '已选 $count';
  static String callParticipantLimit(int count) => '最多 $count 人';
  static String callAdditionalParticipants(int count) => '+$count';
  static String phoneContactsMatchedCount(int count) => '$count 位联系人已注册趣我圈';
  static String profileQrForwardTitle(String displayName) =>
      '${displayName.trim().isNotEmpty ? displayName.trim() : ProfileText.editProfileQrCardTitle} 的二维码';
  static String profileRecordsTotal(int count) => '共有 $count 条记录';
  static String profileCompletenessPrompt(int percent) => '完善主页（$percent%）';
  static String attachHomepageSuggestWithQuery(String query) =>
      '添加“$query”这个主页';
  static String contentLabelForKey(String labelKey) =>
      _contentLabelForKey(labelKey);
}
