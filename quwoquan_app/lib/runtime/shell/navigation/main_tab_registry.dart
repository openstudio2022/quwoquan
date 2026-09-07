import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';

/// 主壳目的地。
///
/// `videoBook` 是 canonical `/video-book` 内容根入口，占据底栏第 2 位。
enum MainTabDestination { home, videoBook, create, chat, profile }

extension MainTabDestinationX on MainTabDestination {
  static const List<MainTabDestination> bottomNavOrdered = <MainTabDestination>[
    MainTabDestination.home,
    MainTabDestination.videoBook,
    MainTabDestination.create,
    MainTabDestination.chat,
    MainTabDestination.profile,
  ];

  static const List<MainTabDestination> mobileShellStackOrdered =
      <MainTabDestination>[
        MainTabDestination.home,
        MainTabDestination.videoBook,
        MainTabDestination.create,
        MainTabDestination.chat,
        MainTabDestination.profile,
      ];

  int get bottomNavIndex => switch (this) {
    MainTabDestination.home => 0,
    MainTabDestination.videoBook => 1,
    MainTabDestination.create => 2,
    MainTabDestination.chat => 3,
    MainTabDestination.profile => 4,
  };

  int get mobileShellStackIndex => mobileShellStackOrdered.indexOf(this);

  int get primaryNavigationIndex => MainTabDestination.values.indexOf(this);

  bool get isBottomNavDestination => bottomNavIndex >= 0;

  bool get isMobileShellStackDestination => mobileShellStackIndex >= 0;

  String get routePath => switch (this) {
    MainTabDestination.home => AppRoutePaths.home,
    MainTabDestination.videoBook => AppRoutePaths.videoBook,
    MainTabDestination.create => AppRoutePaths.createEntry,
    MainTabDestination.chat => AppRoutePaths.chat,
    MainTabDestination.profile => AppRoutePaths.profile,
  };

  String get routeName => switch (this) {
    MainTabDestination.home => 'home',
    MainTabDestination.videoBook => 'videoBook',
    MainTabDestination.create => 'create',
    MainTabDestination.chat => 'chat',
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
  if (location == AppRoutePaths.videoBook) {
    return MainTabDestination.videoBook;
  }
  if (location == AppRoutePaths.createEntry ||
      location.startsWith(AppRoutePaths.createPathTemplate)) {
    return MainTabDestination.create;
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

MainTabDestination mainTabFromMobileShellStackIndex(int index) {
  return MainTabDestinationX.mobileShellStackOrdered[index];
}
