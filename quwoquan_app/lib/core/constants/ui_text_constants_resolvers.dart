part of 'ui_text_constants.dart';

String _objectIntroSourcePlatform(String sourceKind) =>
    const {
      'wikipedia': 'Wikipedia',
      'baidu_baike': '百度百科',
      'sogou_baike': '搜狗百科',
      'toutiao_baike': '今日头条百科',
    }[sourceKind] ??
    '百科来源';

String _homeChannelMoodCopy(String moodCopyKey) {
  switch (moodCopyKey) {
    case 'home_mood_following':
      return UITextConstants.homeMoodFollowing;
    case 'home_mood_recommend':
      return UITextConstants.homeMoodRecommend;
    case 'home_mood_campus':
      return UITextConstants.homeMoodCampus;
    case 'home_mood_travel':
      return UITextConstants.homeMoodTravel;
    case 'home_mood_photography':
      return UITextConstants.homeMoodPhotography;
    case 'home_mood_tech':
      return UITextConstants.homeMoodTech;
    case 'home_mood_car':
      return UITextConstants.homeMoodCar;
    default:
      return '';
  }
}

String _homeChannelLabel(String labelKey) {
  switch (labelKey) {
    case 'home_tab_following':
      return UITextConstants.homeTabFollowing;
    case 'home_tab_recommend':
      return UITextConstants.homeTabRecommended;
    case 'home_tab_campus':
      return UITextConstants.circleScenarioCampus;
    case 'home_tab_travel':
      return UITextConstants.homeTabTravel;
    case 'home_tab_photography':
      return UITextConstants.homeTabPhotography;
    case 'home_tab_tech':
      return UITextConstants.homeTabTech;
    case 'home_tab_car':
      return UITextConstants.homeTabCarFriends;
    default:
      return UITextConstants.homeTabRecommended;
  }
}

String _homeObjectActionLabel(String actionType) {
  switch (actionType) {
    case 'follow':
      return UITextConstants.homeObjectActionFollow;
    case 'join':
      return UITextConstants.homeObjectActionJoin;
    case 'add_contact':
      return UITextConstants.homeObjectActionAddContact;
    case 'view':
      return UITextConstants.homeObjectActionView;
    default:
      return UITextConstants.homeObjectActionView;
  }
}

String _homeObjectSharedCount(int count) {
  if (count <= 0) return '';
  return '$count${UITextConstants.homeObjectSharedCountSuffix}';
}

String _webPcPrimaryLabel(String routeName) {
  switch (routeName) {
    case 'home':
      return UITextConstants.webPcPrimaryHome;
    case 'featured':
      return UITextConstants.webPcPrimaryFeatured;
    case 'create':
      return UITextConstants.webPcPrimaryCreate;
    case 'chat':
      return ChatText.webPcPrimaryMessages;
    case 'profile':
      return UITextConstants.webPcPrimaryProfile;
    default:
      return UITextConstants.webPcPrimaryHome;
  }
}
