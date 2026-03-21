import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_edit_settings_page.dart';

Widget _app({
  CircleEditSettingsTab initialTab = CircleEditSettingsTab.info,
}) {
  final circle = CircleDto(
    id: 'circle_photo_01',
    name: '光影摄影社',
    description: '一群热爱光影的人',
    coverUrl: 'https://example.com/cover.jpg',
    ownerId: 'u1',
    tags: const ['摄影', '城市'],
    visibility: 'public',
    joinPolicy: 'approval',
    autoSyncChat: true,
    sectionConfig: const [
      CircleSectionConfigDto(sectionType: 'works', visible: true, order: 0),
      CircleSectionConfigDto(sectionType: 'interaction', visible: true, order: 1),
    ],
    createdAt: DateTime(2024, 1, 1),
    updatedAt: DateTime(2024, 1, 2),
  );
  return ProviderScope(
    child: CupertinoApp(
      home: CircleEditSettingsPage(
        circleId: circle.id,
        initialCircle: circle,
        initialTab: initialTab,
      ),
    ),
  );
}

void main() {
  group('CircleEditSettingsPage', () {
    testWidgets('默认渲染基础信息编辑表单', (tester) async {
      await tester.pumpWidget(_app());
      await tester.pump();

      expect(find.text('圈子设置'), findsOneWidget);
      expect(find.text('圈子名称'), findsOneWidget);
      expect(find.text('圈子简介'), findsOneWidget);
      expect(find.text('保存更改'), findsWidgets);
    });

    testWidgets('切换到管理中心后展示访问设置', (tester) async {
      await tester.pumpWidget(
        _app(initialTab: CircleEditSettingsTab.settings),
      );
      await tester.pump();

      expect(find.text('可见范围'), findsOneWidget);
      expect(find.text('加入方式'), findsOneWidget);
      expect(find.text('同步圈聊'), findsOneWidget);
    });
  });
}
