import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';

void main() {
  test('旧生活/足迹 Tab 已从 user_profile metadata 移除', () {
    // user_profile/ui_config.yaml 已收敛为「记录 + 互动」两栏；
    // 浏览类行为并入互动二级「浏览」，不再单设足迹一级 Tab。
    expect(UserProfileUIConfig.profileTabs.map((tab) => tab.id), <String>[
      'creations',
      'interaction',
    ]);
    expect(
      UserProfileUIConfig.interactionSubTabs.map((tab) => tab.id),
      contains('views'),
    );
    expect(UserProfileUIConfig.lifestyleSubTabs, isEmpty);
  });
}
