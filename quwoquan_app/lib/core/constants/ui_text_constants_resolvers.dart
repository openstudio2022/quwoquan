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
      return DiscoveryText.homeMoodFollowing;
    case 'home_mood_recommend':
      return DiscoveryText.homeMoodRecommend;
    case 'home_mood_campus':
      return DiscoveryText.homeMoodCampus;
    case 'home_mood_travel':
      return DiscoveryText.homeMoodTravel;
    case 'home_mood_photography':
      return DiscoveryText.homeMoodPhotography;
    case 'home_mood_tech':
      return DiscoveryText.homeMoodTech;
    case 'home_mood_car':
      return DiscoveryText.homeMoodCar;
    default:
      return '';
  }
}

String _homeChannelLabel(String labelKey) {
  switch (labelKey) {
    case 'home_tab_following':
      return DiscoveryText.homeTabFollowing;
    case 'home_tab_recommend':
      return DiscoveryText.homeTabRecommended;
    case 'home_tab_campus':
      return DiscoveryText.circleScenarioCampus;
    case 'home_tab_travel':
      return DiscoveryText.homeTabTravel;
    case 'home_tab_photography':
      return DiscoveryText.homeTabPhotography;
    case 'home_tab_tech':
      return DiscoveryText.homeTabTech;
    case 'home_tab_car':
      return DiscoveryText.homeTabCarFriends;
    default:
      return DiscoveryText.homeTabRecommended;
  }
}

String _homeObjectActionLabel(String actionType) {
  switch (actionType) {
    case 'follow':
      return DiscoveryText.homeObjectActionFollow;
    case 'join':
      return DiscoveryText.homeObjectActionJoin;
    case 'add_contact':
      return DiscoveryText.homeObjectActionAddContact;
    case 'view':
      return DiscoveryText.homeObjectActionView;
    default:
      return DiscoveryText.homeObjectActionView;
  }
}

String _homeObjectSharedCount(int count) {
  if (count <= 0) return '';
  return '$count${DiscoveryText.homeObjectSharedCountSuffix}';
}

String _webPcPrimaryLabel(String routeName) {
  switch (routeName) {
    case 'home':
      return DiscoveryText.webPcPrimaryHome;
    case 'featured':
      return DiscoveryText.webPcPrimaryFeatured;
    case 'create':
      return DiscoveryText.webPcPrimaryCreate;
    case 'chat':
      return ChatText.webPcPrimaryMessages;
    case 'profile':
      return DiscoveryText.webPcPrimaryProfile;
    default:
      return DiscoveryText.webPcPrimaryHome;
  }
}
