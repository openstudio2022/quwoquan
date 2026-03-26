import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_edit_settings_page.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_media_picker_provider.dart';

Widget _app({
  CircleEditSettingsTab initialTab = CircleEditSettingsTab.info,
  bool createMode = false,
  CircleRepository? repository,
  CircleMediaPickerController? mediaPicker,
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
  final overrides = [
    if (repository != null) circleRepositoryProvider.overrideWithValue(repository),
    if (mediaPicker != null)
      circleMediaPickerProvider.overrideWithValue(mediaPicker),
  ];
  return ProviderScope(
    overrides: overrides,
    child: CupertinoApp(
      home: createMode
          ? CircleEditSettingsPage.create(initialTab: initialTab)
          : CircleEditSettingsPage(
              circleId: circle.id,
              initialCircle: circle,
              initialTab: initialTab,
            ),
    ),
  );
}

class _RecordingCircleRepository extends MockCircleRepository {
  Map<String, dynamic>? createdPayload;

  @override
  Future<Map<String, dynamic>> createCircle(Map<String, dynamic> data) async {
    createdPayload = Map<String, dynamic>.from(data);
    return super.createCircle(data);
  }
}

class _FakeCircleMediaPickerController implements CircleMediaPickerController {
  _FakeCircleMediaPickerController(this.pathsBySource);

  final Map<CircleMediaPickSource, String> pathsBySource;

  @override
  Future<String?> pickImage(
    BuildContext context, {
    required CircleMediaPickSource source,
  }) async {
    return pathsBySource[source];
  }
}

Future<void> _pressCupertinoButton(WidgetTester tester, Finder finder) async {
  final button = tester.widget<CupertinoButton>(finder);
  button.onPressed?.call();
  await tester.pumpAndSettle();
}

void main() {
  group('CircleEditSettingsPage', () {
    testWidgets('默认渲染基础信息编辑表单', (tester) async {
      await tester.pumpWidget(_app());
      await tester.pump();
      final scrollable = find.byType(Scrollable).first;
      await tester.dragUntilVisible(
        find.text('圈子名称'),
        scrollable,
        const Offset(0, -240),
      );
      await tester.pumpAndSettle();

      expect(find.text('圈子设置'), findsOneWidget);
      expect(find.text('头像与封面'), findsOneWidget);
      expect(find.text('圈子名称'), findsOneWidget);
      expect(find.text('圈子简介'), findsOneWidget);
      expect(find.text('保存更改'), findsWidgets);
    });

    testWidgets('创建模式提交真实圈子表单', (tester) async {
      final repository = _RecordingCircleRepository();
      final mediaPicker = _FakeCircleMediaPickerController(
        const {
          CircleMediaPickSource.photoLibrary: '/tmp/circle-cover.png',
          CircleMediaPickSource.camera: '/tmp/circle-avatar.png',
        },
      );
      await tester.pumpWidget(
        _app(
          createMode: true,
          repository: repository,
          mediaPicker: mediaPicker,
        ),
      );
      await tester.pump();
      final scrollable = find.byType(Scrollable).first;

      await tester.dragUntilVisible(
        find.text('添加封面'),
        scrollable,
        const Offset(0, -240),
      );
      await tester.pumpAndSettle();

      final addCoverButton = find.widgetWithText(CupertinoButton, '添加封面');
      await tester.ensureVisible(addCoverButton);
      await _pressCupertinoButton(tester, addCoverButton);
      await _pressCupertinoButton(
        tester,
        find.widgetWithText(CupertinoButton, '从照片中选择'),
      );

      final addAvatarButton = find.widgetWithText(CupertinoButton, '更换头像');
      await tester.ensureVisible(addAvatarButton);
      await tester.pumpAndSettle();
      await _pressCupertinoButton(tester, addAvatarButton);
      await _pressCupertinoButton(
        tester,
        find.widgetWithText(CupertinoButton, '拍照'),
      );
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(CupertinoTextField).first, '夜跑搭子');
      await _pressCupertinoButton(
        tester,
        find.widgetWithText(CupertinoButton, '创建圈子').last,
      );
      await tester.pump(const Duration(seconds: 4));

      expect(repository.createdPayload?['name'], '夜跑搭子');
      expect(repository.createdPayload?['categoryId'], isNotNull);
      expect(repository.createdPayload?['coverUrl'], '/tmp/circle-cover.png');
      expect(repository.createdPayload?['avatar'], '/tmp/circle-avatar.png');
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
