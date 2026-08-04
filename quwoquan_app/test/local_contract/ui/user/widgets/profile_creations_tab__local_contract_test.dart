import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/user/account/user_account/domain/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';

import '../../../../support/harness/profile_shell_scroll_utils.dart';
import '../../../../support/cloud_services/repository_mock_reexports.dart';

/// 创作 Tab（V5）：二级子页恰为 全部/图片/视频/长文，全链路无「微趣/moment」概念。
class _NoNetworkHttpOverrides extends HttpOverrides {}

class _ThrowingCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityViewData> getCapability(String targetUserId) {
    return Future.error(StateError('capability unavailable in test'));
  }
}

Widget _scopedApp() {
  return ProviderScope(
    overrides: [
      profileQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      authorImpactQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      contentRuntimeConfigProvider.overrideWithValue(
        buildAlphaContentRuntimeConfigDefaults(),
      ),
      intersectionRepositoryProvider.overrideWithValue(
        AlphaIntersectionRepository(),
      ),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _ThrowingCapabilityRepository(),
      ),
    ],
    child: MaterialApp(
      theme: ThemeData.light(),
      home: const ProfileShell(
        mode: ProfileMode.mine,
        userId: 'nature_photographer',
      ),
    ),
  );
}

void _setPhoneSize(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 3.0;
}

Future<void> _pumpFrames(WidgetTester tester, {int count = 12}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 80));
  }
}

void main() {
  setUp(() {
    HttpOverrides.global = _NoNetworkHttpOverrides();
  });

  test('codegen creationSubTabs 恰为 全部/图片/视频/长文（无 micro/moment）', () {
    final ids = UserProfileUIConfig.creationSubTabs.map((t) => t.id).toList();
    expect(ids, <String>['all', 'image', 'video', 'article']);
    expect(ids.contains('micro'), isFalse);
    expect(ids.contains('moment'), isFalse);
  });

  testWidgets('创作 Tab 二级过滤改为内联横滑二级页签，全部/图片/视频/长文常驻可见', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(_scopedApp());
    await _pumpFrames(tester);
    await revealProfilePrimaryTabs(tester);

    // 二级过滤与互动页同源：四个过滤项以横滑二级页签内联铺开、常驻可见，
    // 不再收敛为漏斗图标 + 浮层菜单。
    final subTabs = find.byKey(
      const ValueKey<String>('profile-works-secondary-tabs'),
    );
    expect(subTabs, findsOneWidget);

    // 旧漏斗入口与浮层菜单不再存在。
    expect(
      find.byKey(const ValueKey<String>('profile-works-filter-button')),
      findsNothing,
    );
    expect(find.byType(CupertinoActionSheet), findsNothing);

    for (final key in const <String>[
      'creation_sub_all',
      'creation_sub_image',
      'creation_sub_video',
      'creation_sub_text',
    ]) {
      expect(
        find.descendant(
          of: subTabs,
          matching: find.text(UITextConstants.contentLabelForKey(key)),
        ),
        findsOneWidget,
      );
    }

    // 数量统计放到二级页签之下，仍可见。
    expect(
      find.descendant(of: subTabs, matching: find.textContaining('条记录')),
      findsOneWidget,
    );

    // 无微趣残留
    expect(find.text('微趣'), findsNothing);
  });
}
