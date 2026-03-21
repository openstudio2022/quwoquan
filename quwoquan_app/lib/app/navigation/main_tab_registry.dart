import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';

enum MainTabDestination { home, circles, assistant, chat, profile }

extension MainTabDestinationX on MainTabDestination {
  static const List<MainTabDestination> bottomNavOrdered = <MainTabDestination>[
    MainTabDestination.home,
    MainTabDestination.assistant,
    MainTabDestination.chat,
    MainTabDestination.profile,
  ];

  int get bottomNavIndex => switch (this) {
    MainTabDestination.home || MainTabDestination.circles => 0,
    MainTabDestination.assistant => 1,
    MainTabDestination.chat => 2,
    MainTabDestination.profile => 3,
  };

  String get routePath => switch (this) {
    MainTabDestination.home => AppRoutePaths.home,
    MainTabDestination.circles => AppRoutePaths.circles,
    MainTabDestination.assistant => AppRoutePaths.assistant,
    MainTabDestination.chat => AppRoutePaths.chat,
    MainTabDestination.profile => AppRoutePaths.profile,
  };

  String get routeName => switch (this) {
    MainTabDestination.home => 'home',
    MainTabDestination.circles => 'circles',
    MainTabDestination.assistant => 'assistant',
    MainTabDestination.chat => 'chat',
    MainTabDestination.profile => 'profile',
  };
}

MainTabDestination mainTabFromLocation(String location) {
  if (location == AppRoutePaths.home) {
    return MainTabDestination.home;
  }
  if (location == AppRoutePaths.circles) {
    return MainTabDestination.circles;
  }
  if (location == AppRoutePaths.assistant) {
    return MainTabDestination.assistant;
  }
  if (location.startsWith(AppRoutePaths.chat)) {
    return MainTabDestination.chat;
  }
  if (location == AppRoutePaths.profile) {
    return MainTabDestination.profile;
  }
  return MainTabDestination.home;
}

int bottomNavIndexFromLocation(String location) {
  return mainTabFromLocation(location).bottomNavIndex;
}

MainTabDestination mainTabFromBottomNavIndex(int index) {
  return MainTabDestinationX.bottomNavOrdered[index];
}
