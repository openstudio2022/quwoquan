import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';

enum MainTabDestination { home, featured, create, chat, plaza, profile }

extension MainTabDestinationX on MainTabDestination {
  static const List<MainTabDestination> bottomNavOrdered = <MainTabDestination>[
    MainTabDestination.home,
    MainTabDestination.featured,
    MainTabDestination.create,
    MainTabDestination.chat,
    MainTabDestination.plaza,
    MainTabDestination.profile,
  ];

  int get bottomNavIndex => switch (this) {
    MainTabDestination.home => 0,
    MainTabDestination.featured => 1,
    MainTabDestination.create => 2,
    MainTabDestination.chat => 3,
    MainTabDestination.plaza => 4,
    MainTabDestination.profile => 5,
  };

  String get routePath => switch (this) {
    MainTabDestination.home => AppRoutePaths.home,
    MainTabDestination.featured => AppRoutePaths.home,
    MainTabDestination.create => AppRoutePaths.createEntry,
    MainTabDestination.chat => AppRoutePaths.chat,
    MainTabDestination.plaza => AppRoutePaths.plaza,
    MainTabDestination.profile => AppRoutePaths.profile,
  };

  String get routeName => switch (this) {
    MainTabDestination.home => 'home',
    MainTabDestination.featured => 'featured',
    MainTabDestination.create => 'create',
    MainTabDestination.chat => 'chat',
    MainTabDestination.plaza => 'plaza',
    MainTabDestination.profile => 'profile',
  };
}

MainTabDestination mainTabFromLocation(String location) {
  if (location == AppRoutePaths.home) {
    return MainTabDestination.home;
  }
  if (location == AppRoutePaths.circles) {
    return MainTabDestination.home;
  }
  if (location == AppRoutePaths.createEntry ||
      location.startsWith(AppRoutePaths.createPathTemplate)) {
    return MainTabDestination.create;
  }
  if (location.startsWith(AppRoutePaths.chat)) {
    return MainTabDestination.chat;
  }
  if (location.startsWith(AppRoutePaths.plaza)) {
    return MainTabDestination.plaza;
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
