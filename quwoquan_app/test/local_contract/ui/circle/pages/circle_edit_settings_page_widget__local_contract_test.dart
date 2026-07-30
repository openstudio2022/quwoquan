import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/components/media/picker/image_pick_gateway.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_edit_settings_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

Widget _app({
  CircleEditSettingsTab initialTab = CircleEditSettingsTab.info,
  bool createMode = false,
  CircleLifecycleCommandWriter? lifecycleWriter,
  ImagePickGateway? mediaPicker,
}) {
  final circle = CircleDto(
    id: 'fixture_circle_photo',
    name: '光影摄影社',
    description: '一群热爱光影的人',
    coverUrl: 'https://example.com/cover.jpg',
    ownerId: 'u1',
    tags: const ['摄影', '城市'],
    visibility: CircleVisibility.public,
    joinPolicy: CircleJoinPolicy.approval,
    autoSyncChat: true,
    sectionConfig: const [
      CircleSectionConfigDto(sectionType: 'works', visible: true, order: 0),
      CircleSectionConfigDto(
        sectionType: 'interaction',
        visible: true,
        order: 1,
      ),
    ],
    createdAt: DateTime(2024, 1, 1),
    updatedAt: DateTime(2024, 1, 2),
  );
  final overrides = [
    if (lifecycleWriter != null)
      circlesListCircleLifecycleCommandWriterProvider.overrideWithValue(
        lifecycleWriter,
      ),
    if (lifecycleWriter != null)
      activePersonaContextProvider.overrideWith(
        (_) async => ActivePersonaContextViewData.fallback(
          personaId: 'user_001',
          ownerUserId: 'user_001',
          displayName: '圈子编辑测试用户',
          avatarUrl: '',
          contextVersion: 1,
        ),
      ),
    if (mediaPicker != null)
      imagePickGatewayProvider.overrideWithValue(mediaPicker),
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

/// 记录创建命令的 typed fake（与 Remote lifecycle facet 同接口）。
class _RecordingCircleLifecycleWriter implements CircleLifecycleCommandWriter {
  CreateCircleCommand? createdCommand;

  @override
  Future<CircleCommandResult> createCircle(CreateCircleCommand command) async {
    createdCommand = command;
    return const CircleCommandResult(
      circleId: 'created_circle_1',
      version: 1,
      status: CircleLifecycleStatus.active,
      idempotentReplay: false,
    );
  }

  @override
  Future<CircleCommandResult> updateCircle(UpdateCircleCommand command) async {
    throw UnsupportedError('update is out of scope for this fake');
  }

  @override
  Future<CircleCommandResult> archiveCircle(
    ArchiveCircleCommand command,
  ) async {
    throw UnsupportedError('archive is out of scope for this fake');
  }
}

class _FakeImagePickGateway implements ImagePickGateway {
  _FakeImagePickGateway(this.pathsBySource);

  final Map<ImagePickSource, String> pathsBySource;

  @override
  Future<String?> pickImage(
    BuildContext context, {
    required ImagePickSource source,
    required String cameraRouteName,
    required String galleryRouteName,
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
        find.text('圈子封面'),
        scrollable,
        const Offset(0, -240),
      );
      await tester.pumpAndSettle();

      expect(find.text('圈子设置'), findsOneWidget);
      expect(find.text('圈子封面'), findsOneWidget);
      await tester.dragUntilVisible(
        find.text('圈子头像'),
        scrollable,
        const Offset(0, -240),
      );
      expect(find.text('圈子头像'), findsOneWidget);
      await tester.dragUntilVisible(
        find.text('圈子名称'),
        scrollable,
        const Offset(0, -240),
      );
      expect(find.text('圈子名称'), findsOneWidget);
      expect(find.text('圈子简介'), findsOneWidget);
      expect(find.text('保存更改'), findsWidgets);
    });

    testWidgets('创建模式提交真实圈子表单', (tester) async {
      final lifecycleWriter = _RecordingCircleLifecycleWriter();
      final mediaPicker = _FakeImagePickGateway(const {
        ImagePickSource.photoLibrary: '/tmp/circle-cover.png',
        ImagePickSource.camera: '/tmp/circle-avatar.png',
      });
      await tester.pumpWidget(
        _app(
          createMode: true,
          lifecycleWriter: lifecycleWriter,
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

      final command = lifecycleWriter.createdCommand;
      expect(command, isNotNull);
      expect(command!.name, '夜跑搭子');
      expect(command.category, isNotNull);
      expect(command.coverUrl, '/tmp/circle-cover.png');
    });

    testWidgets('切换到管理中心后展示访问设置', (tester) async {
      await tester.pumpWidget(_app(initialTab: CircleEditSettingsTab.settings));
      await tester.pump();

      expect(find.text('可见范围'), findsOneWidget);
      expect(find.text('加入方式'), findsOneWidget);
      expect(find.text(CommunityText.visibilityInviteOnly), findsOneWidget);
      expect(find.text(CommunityText.circleJoinInviteOnly), findsOneWidget);
      expect(find.text('同步圈聊'), findsOneWidget);
    });
  });
}
