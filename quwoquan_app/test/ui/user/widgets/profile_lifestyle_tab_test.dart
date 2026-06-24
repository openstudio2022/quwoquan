import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';

void main() {
  test('user_profile 一级 Tab 收敛为 记录/互动/足迹（V5），足迹隐私门控仅本人可见', () {
    // V5 唯一冻结口径（profile-homepage-redesign/spec.md L8/L19/L60）：
    // 一级 Tab = [记录 | 互动 | 足迹]；圈子降为统计数字，生活不再占一级 Tab；
    // 足迹承载浏览历史，仅本人主页可见（modes: [mine]）。
    expect(UserProfileUIConfig.profileTabs.map((tab) => tab.id), <String>[
      'creations',
      'interaction',
      'footprint',
    ]);

    final footprint = UserProfileUIConfig.profileTabs.firstWhere(
      (tab) => tab.id == 'footprint',
    );
    expect(footprint.visibleInMode('mine'), isTrue);
    expect(footprint.visibleInMode('other'), isFalse);

    // 记录/互动为全模式可见。
    for (final id in <String>['creations', 'interaction']) {
      final tab = UserProfileUIConfig.profileTabs.firstWhere(
        (tab) => tab.id == id,
      );
      expect(tab.visibleInMode('mine'), isTrue);
      expect(tab.visibleInMode('other'), isTrue);
    }

    // 生活一级 Tab 已废止，lifestyle 子 Tab 不再下发。
    expect(UserProfileUIConfig.lifestyleSubTabs, isEmpty);
  });
}
