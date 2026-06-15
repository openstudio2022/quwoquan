import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';

void main() {
  test('旧生活 Tab 已从 user_profile metadata 移除', () {
    expect(UserProfileUIConfig.profileTabs.map((tab) => tab.id), <String>[
      'creations',
      'circles',
      'interaction',
    ]);
    expect(UserProfileUIConfig.lifestyleSubTabs, isEmpty);
  });
}
