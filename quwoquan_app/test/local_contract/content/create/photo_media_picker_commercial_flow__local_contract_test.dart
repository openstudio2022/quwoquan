import 'package:flutter/cupertino.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_manager/photo_manager.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_page.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_presentation.dart';
import 'package:quwoquan_app/components/media/reorderable/media_reorderable_view.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';
import 'package:quwoquan_app/core/services/media_picker_service.dart';
import 'package:quwoquan_app/core/test_keys.dart';

void main() {
  group('photo media picker commercial flow', () {
    test('图片模式隐藏视频分类与一键成片，只显示编辑图片和完成', () {
      final categories = mediaPickerCategoriesForEntryMode(
        MediaPickerEntryMode.image,
      );
      expect(categories, isEmpty);

      final actions = mediaPickerBottomActionsForEntryMode(
        mode: MediaPickerEntryMode.image,
        selectionCount: 4,
      );

      expect(actions.map((action) => action.label), <String>[
        UITextConstants.mediaPickerEditImage,
        '完成(4)',
      ]);
      expect(
        actions.map((action) => action.action),
        <CreateMediaPickerBottomAction>[
          CreateMediaPickerBottomAction.editImage,
          CreateMediaPickerBottomAction.completeImage,
        ],
      );
      expect(
        actions.map((action) => action.label),
        isNot(contains(UITextConstants.mediaPickerOneTapMovie)),
      );
    });

    test('无选择时图片模式底部操作保留但不可点击', () {
      final actions = mediaPickerBottomActionsForEntryMode(
        mode: MediaPickerEntryMode.image,
        selectionCount: 0,
      );

      expect(actions, hasLength(2));
      expect(actions.every((action) => !action.enabled), isTrue);
      expect(actions.last.label, '完成(0)');
    });

    test('视频模式不复用图片完成与编辑图片语义', () {
      final categories = mediaPickerCategoriesForEntryMode(
        MediaPickerEntryMode.video,
      );
      expect(categories, isEmpty);

      final actions = mediaPickerBottomActionsForEntryMode(
        mode: MediaPickerEntryMode.video,
        selectionCount: 1,
      );

      expect(actions, hasLength(1));
      expect(actions.single.action, CreateMediaPickerBottomAction.nextStep);
      expect(actions.single.label, '下一步(1)');
      expect(actions.single.label, isNot(contains('完成')));
      expect(actions.single.label, isNot(UITextConstants.mediaPickerEditImage));
    });

    testWidgets('相册下拉展示目录并切换当前图片集合，图片模式过滤视频', (tester) async {
      final service = _FakeMediaPickerService(
        albums: <AssetPathEntity>[
          _album('recent', '最近项目'),
          _album('travel', '旅行'),
        ],
        assetsByAlbumId: <String, List<AssetEntity>>{
          'recent': <AssetEntity>[_image('a1'), _video('v1')],
          'travel': <AssetEntity>[_image('b1')],
        },
      );

      await tester.pumpWidget(_pickerApp(service: service));
      await tester.pumpAndSettle();

      expect(find.text(UITextConstants.mediaPickerCategoryAll), findsNothing);
      expect(find.text(UITextConstants.mediaPickerCategoryPhoto), findsNothing);
      expect(find.text(UITextConstants.mediaPickerCategoryLive), findsNothing);
      expect(
        find.text(UITextConstants.mediaPickerCategoryFullscreen),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey<String>('media-picker-asset-a1')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('media-picker-asset-v1')),
        findsNothing,
      );

      await tester.tap(find.text(UITextConstants.mediaPickerPhotoTitle));
      await tester.pumpAndSettle();

      // 相册改为顶部锚定下滑浮层（替代贴底 modal sheet），不再展示「选择相册」标题。
      expect(
        find.byKey(TestKeys.mediaPickerAlbumDropdownPanel),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.mediaPickerAlbumSelectionTitle),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey<String>('media-picker-album-travel')),
        findsOneWidget,
      );
      expect(find.text('旅行 (1)'), findsOneWidget);

      await tester.tap(
        find.byKey(const ValueKey<String>('media-picker-album-travel')),
      );
      await tester.pumpAndSettle();

      expect(
        find.byKey(const ValueKey<String>('media-picker-asset-a1')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey<String>('media-picker-asset-b1')),
        findsOneWidget,
      );
    });

    testWidgets('图片相册列表相机置顶、排除视频目录并按图片数降序', (tester) async {
      final service = _FakeMediaPickerService(
        albums: <AssetPathEntity>[
          _album('recent', 'Recents'),
          _album('videos', 'All Videos'),
          _album('travel', '旅行'),
          _album('camera', 'Camera'),
          _album('empty', '空相册'),
        ],
        assetsByAlbumId: <String, List<AssetEntity>>{
          'recent': <AssetEntity>[_image('r1'), _image('r2')],
          'videos': <AssetEntity>[_video('v1'), _video('v2'), _video('v3')],
          'travel': <AssetEntity>[_image('t1'), _image('t2'), _image('t3')],
          'camera': <AssetEntity>[_image('c1')],
          'empty': const <AssetEntity>[],
        },
      );

      await tester.pumpWidget(_pickerApp(service: service));
      await tester.pumpAndSettle();

      expect(
        find.byKey(const ValueKey<String>('media-picker-asset-c1')),
        findsOneWidget,
      );

      await tester.tap(find.text(UITextConstants.mediaPickerPhotoTitle));
      await tester.pumpAndSettle();

      expect(find.text('相机 (1)'), findsOneWidget);
      expect(find.text('最近项目 (2)'), findsOneWidget);
      expect(find.text('旅行 (3)'), findsOneWidget);
      expect(find.text('All Videos'), findsNothing);
      expect(find.text('空相册'), findsNothing);

      final cameraTop = tester.getTopLeft(find.text('相机 (1)')).dy;
      final travelTop = tester.getTopLeft(find.text('旅行 (3)')).dy;
      final recentsTop = tester.getTopLeft(find.text('最近项目 (2)')).dy;

      expect(cameraTop, lessThan(travelTop));
      expect(travelTop, lessThan(recentsTop));
    });

    testWidgets('系统聚合相册(isAll)置顶且显示为全部照片', (tester) async {
      final service = _FakeMediaPickerService(
        albums: <AssetPathEntity>[
          _album('travel', '旅行'),
          _album('camera', 'Camera'),
          _album('recent', 'Recents', isAll: true),
        ],
        assetsByAlbumId: <String, List<AssetEntity>>{
          'travel': <AssetEntity>[
            _image('t1'),
            _image('t2'),
            _image('t3'),
            _image('t4'),
          ],
          'camera': <AssetEntity>[_image('c1')],
          'recent': <AssetEntity>[_image('r1'), _image('r2')],
        },
      );

      await tester.pumpWidget(_pickerApp(service: service));
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.mediaPickerPhotoTitle));
      await tester.pumpAndSettle();

      final allLabel = '${UITextConstants.mediaPickerAlbumAllPhotos} (2)';
      // isAll 相册统一显示为「全部照片」，且即使图片数最少也置顶。
      expect(find.text(allLabel), findsOneWidget);
      final allTop = tester.getTopLeft(find.text(allLabel)).dy;
      final cameraTop = tester.getTopLeft(find.text('相机 (1)')).dy;
      final travelTop = tester.getTopLeft(find.text('旅行 (4)')).dy;
      expect(allTop, lessThan(cameraTop));
      expect(allTop, lessThan(travelTop));
    });

    testWidgets('较宽手机图片宫格保持三列，不因机型变宽升级为四列', (tester) async {
      tester.view.physicalSize = const Size(430, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });
      final service = _FakeMediaPickerService(
        albums: <AssetPathEntity>[_album('recent', '最近项目')],
        assetsByAlbumId: <String, List<AssetEntity>>{
          'recent': <AssetEntity>[
            _image('a1'),
            _image('a2'),
            _image('a3'),
            _image('a4'),
          ],
        },
      );

      await tester.pumpWidget(_pickerApp(service: service));
      await tester.pumpAndSettle();

      final cameraTop = tester
          .getTopLeft(
            find.byKey(const ValueKey<String>('media-picker-camera-tile')),
          )
          .dy;
      final a2Top = tester
          .getTopLeft(
            find.byKey(const ValueKey<String>('media-picker-asset-a2')),
          )
          .dy;
      final a3Top = tester
          .getTopLeft(
            find.byKey(const ValueKey<String>('media-picker-asset-a3')),
          )
          .dy;
      final a4Top = tester
          .getTopLeft(
            find.byKey(const ValueKey<String>('media-picker-asset-a4')),
          )
          .dy;

      expect(a2Top, cameraTop);
      expect(a3Top, greaterThan(cameraTop));
      expect(a4Top, a3Top);
    });

    testWidgets('平板宽度下图片宫格会自适应增加为四列', (tester) async {
      tester.view.physicalSize = const Size(700, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });
      final service = _FakeMediaPickerService(
        albums: <AssetPathEntity>[_album('recent', '最近项目')],
        assetsByAlbumId: <String, List<AssetEntity>>{
          'recent': <AssetEntity>[
            _image('a1'),
            _image('a2'),
            _image('a3'),
            _image('a4'),
          ],
        },
      );

      await tester.pumpWidget(_pickerApp(service: service));
      await tester.pumpAndSettle();

      final cameraTop = tester
          .getTopLeft(
            find.byKey(const ValueKey<String>('media-picker-camera-tile')),
          )
          .dy;
      final a3Top = tester
          .getTopLeft(
            find.byKey(const ValueKey<String>('media-picker-asset-a3')),
          )
          .dy;
      final a4Top = tester
          .getTopLeft(
            find.byKey(const ValueKey<String>('media-picker-asset-a4')),
          )
          .dy;

      expect(a3Top, cameraTop);
      expect(a4Top, greaterThan(cameraTop));
    });

    testWidgets('图片选择器在浅色系统下仍强制深色 chrome，空选择时底部按钮不可点击', (tester) async {
      final service = _FakeMediaPickerService(
        albums: <AssetPathEntity>[_album('recent', '最近项目')],
        assetsByAlbumId: const <String, List<AssetEntity>>{
          'recent': <AssetEntity>[],
        },
      );

      await tester.pumpWidget(
        CupertinoApp(
          theme: const CupertinoThemeData(brightness: Brightness.light),
          home: CreateMediaPickerPage(
            entryMode: MediaPickerEntryMode.image,
            maxSelection: 9,
            mediaPickerService: service,
          ),
        ),
      );
      await tester.pumpAndSettle();

      final title = tester.widget<Text>(
        find.text(UITextConstants.mediaPickerPhotoTitle),
      );
      expect(
        title.style?.color,
        AppColorsFunctional.getColor(true, ColorType.foregroundPrimary),
      );
      final editButton = tester.widget<CupertinoButton>(
        find.widgetWithText(
          CupertinoButton,
          UITextConstants.mediaPickerEditImage,
        ),
      );
      expect(editButton.onPressed, isNull);
      final editButtonSurface = tester.widget<Container>(
        find.byKey(
          const ValueKey<String>('media-picker-bottom-action-editImage'),
        ),
      );
      final editDecoration = editButtonSurface.decoration as BoxDecoration?;
      expect(editDecoration?.color, isNot(AppColors.primaryColor));
      expect(editDecoration?.border, isNull);
      expect(find.text('完成(0)'), findsOneWidget);
    });

    testWidgets('相册弹层在浅色系统下仍强制深色，且最高不越过顶部工具栏', (tester) async {
      final albums = <AssetPathEntity>[
        for (var i = 0; i < 18; i++) _album('album-$i', '相册$i'),
      ];
      final assetsByAlbumId = <String, List<AssetEntity>>{
        for (var i = 0; i < 18; i++) 'album-$i': <AssetEntity>[_image('a$i')],
      };
      final service = _FakeMediaPickerService(
        albums: albums,
        assetsByAlbumId: assetsByAlbumId,
      );

      await tester.pumpWidget(
        CupertinoApp(
          theme: const CupertinoThemeData(brightness: Brightness.light),
          home: CreateMediaPickerPage(
            entryMode: MediaPickerEntryMode.image,
            maxSelection: 9,
            mediaPickerService: service,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.mediaPickerPhotoTitle));
      await tester.pumpAndSettle();

      // 浮层强制深色：相册行文案颜色取深色前景。
      final rowLabel = tester.widget<Text>(find.text('相册0 (1)'));
      expect(
        rowLabel.style?.color,
        AppColorsFunctional.getColor(true, ColorType.foregroundPrimary),
      );

      // 顶部锚定：浮层顶端落在顶栏底边以下（不越过顶栏），底部不超出屏幕（封顶到内容区）。
      final panel = find.byKey(TestKeys.mediaPickerAlbumDropdownPanel);
      expect(panel, findsOneWidget);
      final panelRect = tester.getRect(panel);
      expect(panelRect.top, greaterThanOrEqualTo(AppSpacing.toolbarHeight));
      final screenHeight = tester
          .getSize(find.byType(CreateMediaPickerPage))
          .height;
      expect(panelRect.bottom, lessThanOrEqualTo(screenHeight + 0.5));
    });

    testWidgets('图片模式每次进入都重新选择，不沿用外部 initialSelection', (tester) async {
      final service = _FakeMediaPickerService(
        albums: <AssetPathEntity>[_album('recent', '最近项目')],
        assetsByAlbumId: <String, List<AssetEntity>>{
          'recent': <AssetEntity>[_image('a1')],
        },
      );

      await tester.pumpWidget(
        CupertinoApp(
          home: CreateMediaPickerPage(
            entryMode: MediaPickerEntryMode.image,
            maxSelection: 9,
            mediaPickerService: service,
            initialSelection: const <CreateMediaItem>[
              CreateMediaItem(
                id: 'a1',
                path: '/tmp/a1.jpg',
                type: CreateMediaType.image,
                source: CreateMediaSource.album,
              ),
            ],
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('完成(0)'), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('media-picker-selected-thumb-a1')),
        findsNothing,
      );
    });

    testWidgets('已选缩略条左对齐，拖拽悬停时会先让位再在完成时提交顺序', (tester) async {
      CreateMediaPickerResult? picked;
      final service = _FakeMediaPickerService(
        albums: <AssetPathEntity>[_album('recent', '最近项目')],
        assetsByAlbumId: <String, List<AssetEntity>>{
          'recent': <AssetEntity>[
            _image('a1'),
            _image('a2'),
            _image('a3'),
            _image('a4'),
          ],
        },
      );

      await tester.pumpWidget(
        CupertinoApp(
          home: Builder(
            builder: (context) => CupertinoButton(
              child: const Text('open'),
              onPressed: () async {
                picked = await Navigator.of(context)
                    .push<CreateMediaPickerResult>(
                      CupertinoPageRoute<CreateMediaPickerResult>(
                        builder: (_) => CreateMediaPickerPage(
                          entryMode: MediaPickerEntryMode.image,
                          maxSelection: 9,
                          mediaPickerService: service,
                        ),
                      ),
                    );
              },
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      for (final id in <String>['a1', 'a2', 'a3', 'a4']) {
        await tester.tap(
          find.byKey(ValueKey<String>('media-picker-asset-$id')),
        );
        await tester.pumpAndSettle();
      }

      final stripRect = tester.getRect(find.byType(MediaReorderableView));
      final positionsBefore = <String, Rect>{
        for (final id in <String>['a1', 'a2', 'a3', 'a4'])
          id: tester.getRect(
            find.byKey(ValueKey<String>('media-picker-selected-thumb-$id')),
          ),
      };
      final orderedIds = positionsBefore.keys.toList(growable: false)
        ..sort(
          (a, b) =>
              positionsBefore[a]!.left.compareTo(positionsBefore[b]!.left),
        );
      expect(
        positionsBefore.values
            .map((rect) => rect.left)
            .reduce((min, value) => value < min ? value : min),
        closeTo(stripRect.left, 0.5),
      );

      final start = tester.getCenter(
        find.byKey(
          ValueKey<String>('media-picker-selected-thumb-${orderedIds.first}'),
        ),
      );
      final target = tester.getCenter(
        find.byKey(
          ValueKey<String>('media-picker-selected-thumb-${orderedIds.last}'),
        ),
      );
      final gesture = await tester.startGesture(start);
      await tester.pump(kLongPressTimeout + const Duration(milliseconds: 80));
      await gesture.moveBy((target - start) + const Offset(30, 0));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 220));

      final secondRect = tester.getRect(
        find.byKey(
          ValueKey<String>('media-picker-selected-thumb-${orderedIds[1]}'),
        ),
      );
      final thirdRect = tester.getRect(
        find.byKey(
          ValueKey<String>('media-picker-selected-thumb-${orderedIds[2]}'),
        ),
      );
      final fourthRect = tester.getRect(
        find.byKey(
          ValueKey<String>('media-picker-selected-thumb-${orderedIds[3]}'),
        ),
      );
      expect(secondRect.left, closeTo(positionsBefore[orderedIds[0]]!.left, 1));
      expect(thirdRect.left, closeTo(positionsBefore[orderedIds[1]]!.left, 1));
      expect(fourthRect.left, closeTo(positionsBefore[orderedIds[2]]!.left, 1));

      await gesture.up();
      await tester.pumpAndSettle();
      await tester.tap(find.text('完成(4)'));
      await tester.pumpAndSettle();

      expect(picked?.items.map((item) => item.id).toList(), <String>[
        orderedIds[1],
        orderedIds[2],
        orderedIds[3],
        orderedIds[0],
      ]);
    });

    testWidgets('宫格选择、底部删除与完成回填保持当前顺序', (tester) async {
      CreateMediaPickerResult? picked;
      final service = _FakeMediaPickerService(
        albums: <AssetPathEntity>[_album('recent', '最近项目')],
        assetsByAlbumId: <String, List<AssetEntity>>{
          'recent': <AssetEntity>[_image('a1'), _image('a2')],
        },
      );

      await tester.pumpWidget(
        CupertinoApp(
          home: Builder(
            builder: (context) => CupertinoButton(
              child: const Text('open'),
              onPressed: () async {
                picked = await Navigator.of(context)
                    .push<CreateMediaPickerResult>(
                      CupertinoPageRoute<CreateMediaPickerResult>(
                        builder: (_) => CreateMediaPickerPage(
                          entryMode: MediaPickerEntryMode.image,
                          maxSelection: 9,
                          mediaPickerService: service,
                        ),
                      ),
                    );
              },
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      await tester.tap(
        find.byKey(const ValueKey<String>('media-picker-asset-a1')),
      );
      await tester.pumpAndSettle();
      expect(find.text('完成(1)'), findsOneWidget);
      expect(find.text('1'), findsWidgets);

      await tester.tap(
        find.byKey(const ValueKey<String>('media-picker-selected-delete-a1')),
      );
      await tester.pumpAndSettle();
      expect(find.text('完成(0)'), findsOneWidget);

      await tester.tap(
        find.byKey(const ValueKey<String>('media-picker-asset-a2')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('完成(1)'));
      await tester.pumpAndSettle();

      expect(picked?.items.map((item) => item.id).toList(), <String>['a2']);
      expect(picked?.items.single.path, '/tmp/a2.jpg');
    });

    testWidgets('点击已选图片进入编辑器并按编辑器返回的多图 index 回填路径', (tester) async {
      CreateMediaPickerResult? picked;
      CreateMediaPickerImageEditorRequest? editorRequest;
      final service = _FakeMediaPickerService(
        albums: <AssetPathEntity>[_album('recent', '最近项目')],
        assetsByAlbumId: <String, List<AssetEntity>>{
          'recent': <AssetEntity>[_image('a1'), _image('a2')],
        },
      );

      await tester.pumpWidget(
        CupertinoApp(
          home: Builder(
            builder: (context) => CupertinoButton(
              child: const Text('open'),
              onPressed: () async {
                picked = await Navigator.of(context)
                    .push<CreateMediaPickerResult>(
                      CupertinoPageRoute<CreateMediaPickerResult>(
                        builder: (_) => CreateMediaPickerPage(
                          entryMode: MediaPickerEntryMode.image,
                          maxSelection: 9,
                          mediaPickerService: service,
                          imageEditorBuilder: (context, request) {
                            editorRequest = request;
                            return const _FakeImageEditorPage(
                              result: <String, Object>{
                                'index': 1,
                                'path': '/tmp/a2-edited.jpg',
                              },
                            );
                          },
                        ),
                      ),
                    );
              },
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      await tester.tap(
        find.byKey(const ValueKey<String>('media-picker-asset-a1')),
      );
      await tester.pumpAndSettle();
      await tester.tap(
        find.byKey(const ValueKey<String>('media-picker-asset-a2')),
      );
      await tester.pumpAndSettle();

      await tester.tap(
        find.byKey(const ValueKey<String>('media-picker-asset-a1')),
      );
      await tester.pumpAndSettle();

      expect(editorRequest?.initialPath, '/tmp/a1.jpg');
      expect(editorRequest?.imagePaths, <String>['/tmp/a1.jpg', '/tmp/a2.jpg']);

      await tester.tap(find.text('save edit'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('完成(2)'));
      await tester.pumpAndSettle();

      expect(picked?.items.map((item) => item.path).toList(), <String>[
        '/tmp/a1.jpg',
        '/tmp/a2-edited.jpg',
      ]);
    });
  });
}

Widget _pickerApp({
  required MediaPickerService service,
  CreateMediaPickerImageEditorBuilder? imageEditorBuilder,
}) {
  return CupertinoApp(
    home: CreateMediaPickerPage(
      entryMode: MediaPickerEntryMode.image,
      maxSelection: 9,
      mediaPickerService: service,
      imageEditorBuilder: imageEditorBuilder,
    ),
  );
}

AssetPathEntity _album(String id, String name, {bool isAll = false}) {
  return AssetPathEntity(
    id: id,
    name: name,
    type: RequestType.image,
    isAll: isAll,
  );
}

AssetEntity _image(String id) {
  return AssetEntity(
    id: id,
    typeInt: AssetType.image.index,
    width: 1200,
    height: 1600,
    createDateSecond: 1760000000,
  );
}

AssetEntity _video(String id) {
  return AssetEntity(
    id: id,
    typeInt: AssetType.video.index,
    width: 1200,
    height: 1600,
    duration: 8,
    createDateSecond: 1760000000,
  );
}

class _FakeMediaPickerService extends MediaPickerService {
  _FakeMediaPickerService({
    required this.albums,
    required this.assetsByAlbumId,
  });

  final List<AssetPathEntity> albums;
  final Map<String, List<AssetEntity>> assetsByAlbumId;

  @override
  Future<bool> ensurePhotoPermission() async {
    return true;
  }

  @override
  Future<List<AssetPathEntity>> loadAlbums({required RequestType type}) async {
    return albums;
  }

  @override
  Future<List<AssetEntity>> loadAssets({
    required AssetPathEntity album,
    required int page,
    required int pageSize,
  }) async {
    if (page > 0) {
      return const <AssetEntity>[];
    }
    return assetsByAlbumId[album.id] ?? const <AssetEntity>[];
  }

  @override
  Future<int> loadAlbumAssetCount(AssetPathEntity album) async {
    return assetsByAlbumId[album.id]?.length ?? 0;
  }

  @override
  Future<CreateMediaItem?> assetToMediaItem(
    AssetEntity entity, {
    CreateMediaSource source = CreateMediaSource.album,
  }) async {
    return CreateMediaItem(
      id: entity.id,
      path: '/tmp/${entity.id}.jpg',
      type: entity.type == AssetType.video
          ? CreateMediaType.video
          : CreateMediaType.image,
      source: source,
      width: entity.width,
      height: entity.height,
      durationMs: entity.duration * 1000,
      createdAtMs: (entity.createDateSecond ?? 0) * 1000,
    );
  }
}

class _FakeImageEditorPage extends StatelessWidget {
  const _FakeImageEditorPage({required this.result});

  final Object result;

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      child: Center(
        child: CupertinoButton(
          onPressed: () => Navigator.of(context).pop(result),
          child: const Text('save edit'),
        ),
      ),
    );
  }
}
