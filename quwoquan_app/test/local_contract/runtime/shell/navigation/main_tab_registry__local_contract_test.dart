// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/premium-stream-recommendation/spec.md#gwt-001.t2

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/main_tab_registry.dart';

void main() {
  test('五栏顺序与 canonical 路由固定为首页视频书加号联系我', () {
    expect(MainTabDestinationX.bottomNavOrdered, <MainTabDestination>[
      MainTabDestination.home,
      MainTabDestination.videoBook,
      MainTabDestination.create,
      MainTabDestination.chat,
      MainTabDestination.profile,
    ]);
    expect(MainTabDestination.videoBook.routePath, AppRoutePaths.videoBook);
    expect(
      mainTabFromLocation(AppRoutePaths.videoBook),
      MainTabDestination.videoBook,
    );
    expect(bottomNavIndexFromLocation(AppRoutePaths.videoBook), 1);
  });

  test('首页频道和历史交集 launcher 不会伪装成视频书底栏状态', () {
    expect(mainTabFromLocation(AppRoutePaths.home), MainTabDestination.home);
    expect(
      mainTabFromLocation(AppRoutePaths.interestMatch),
      MainTabDestination.home,
    );
  });
}
