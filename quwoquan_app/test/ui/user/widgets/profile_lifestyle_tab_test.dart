import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';

void main() {
  test('旧生活 Tab 已从 user_profile metadata 移除', () {
    // user_profile/ui_config.yaml 已收敛为「作品 + 互动」两栏（生活、圈子页签均移除，
    // 互动子页签新增 all）。本测试锁定 metadata-driven 频道集与生活页签清空。
    expect(UserProfileUIConfig.profileTabs.map((tab) => tab.id), <String>[
      'creations',
      'interaction',
    ]);
    expect(UserProfileUIConfig.lifestyleSubTabs, isEmpty);
  });
}
