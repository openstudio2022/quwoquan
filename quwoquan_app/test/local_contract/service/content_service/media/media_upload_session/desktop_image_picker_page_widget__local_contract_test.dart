import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/desktop_image_picker_page.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/desktop_picker_ports.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/desktop_thumbnail_image_provider.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/create_media_models.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_facets.dart'
    show desktopDirectoryPickerProvider, desktopPickerDirectoryMemoryProvider;
import 'package:quwoquan_app/runtime/testing/test_keys.dart';

/// 1x1 透明 PNG，供 Image.memory 安全解码（避免缩略图绘制阶段抛错）。
const List<int> _pngBytes = <int>[
  0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D, //
  0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, //
  0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00, //
  0x0A, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00, //
  0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49, //
  0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82, //
];

class _FakeGateway implements FileStorageGateway {
  _FakeGateway(this._tree, {this.isSupported = true});

  final Map<String, List<FileSystemEntry>> _tree;

  @override
  final bool isSupported;

  @override
  Future<List<FileSystemEntry>> listDirectory(String path) async =>
      _tree[path] ?? const <FileSystemEntry>[];

  @override
  Future<List<int>> readAsBytes(String path) async => _pngBytes;

  @override
  Future<String> applicationSupportPath() => throw UnimplementedError();
  @override
  Future<String> temporaryPath() => throw UnimplementedError();
  @override
  Future<bool> exists(String path) => throw UnimplementedError();
  @override
  Future<String> readAsString(String path) => throw UnimplementedError();
  @override
  Future<void> writeAsString(String path, String contents) =>
      throw UnimplementedError();
  @override
  Future<void> writeAsBytes(String path, List<int> bytes) =>
      throw UnimplementedError();
  @override
  Future<void> delete(String path) => throw UnimplementedError();
  @override
  Future<void> ensureDirectory(String path) => throw UnimplementedError();
}

class _FakeDirectoryPicker implements DesktopDirectoryPicker {
  _FakeDirectoryPicker(this.result);

  final String? result;
  String? lastInitialDirectory;
  int callCount = 0;

  @override
  Future<String?> pickDirectory({String? initialDirectory}) async {
    callCount++;
    lastInitialDirectory = initialDirectory;
    return result;
  }
}

class _FakeDirectoryMemory implements DesktopPickerDirectoryMemory {
  _FakeDirectoryMemory([this._value]);

  String? _value;
  String? remembered;

  @override
  Future<String?> lastDirectory() async => _value;

  @override
  Future<void> rememberDirectory(String path) async {
    remembered = path;
    _value = path;
  }

  @override
  Future<void> clearForTerminalAccountClosure() async {
    _value = null;
  }
}

FileSystemEntry _dir(String path) =>
    FileSystemEntry(path: path, isDirectory: true);
FileSystemEntry _file(String path) =>
    FileSystemEntry(path: path, isDirectory: false);

Map<String, List<FileSystemEntry>> _sampleTree() =>
    <String, List<FileSystemEntry>>{
      '/pics': <FileSystemEntry>[
        _file('/pics/a.jpg'),
        _file('/pics/b.jpg'),
        _dir('/pics/sub'),
      ],
      '/pics/sub': <FileSystemEntry>[_file('/pics/sub/c.jpg')],
    };

void main() {
  Future<CreateMediaPickerResult?> openPicker(
    WidgetTester tester, {
    required FileStorageGateway gateway,
    required DesktopDirectoryPicker directoryPicker,
    required DesktopPickerDirectoryMemory memory,
    int maxSelection = 9,
  }) async {
    CreateMediaPickerResult? result;
    var popped = false;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          fileStorageGatewayProvider.overrideWithValue(gateway),
          desktopDirectoryPickerProvider.overrideWithValue(directoryPicker),
          desktopPickerDirectoryMemoryProvider.overrideWithValue(memory),
        ],
        child: MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: Center(
                child: ElevatedButton(
                  onPressed: () async {
                    result = await Navigator.of(context)
                        .push<CreateMediaPickerResult>(
                          MaterialPageRoute<CreateMediaPickerResult>(
                            builder: (_) => DesktopImagePickerPage(
                              maxSelection: maxSelection,
                            ),
                          ),
                        );
                    popped = true;
                  },
                  child: const Text('open'),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(popped, isFalse);
    return result;
  }

  testWidgets('选目录 -> 扫描 -> 多选 -> 确认返回有序结果，并记忆目录', (tester) async {
    final gateway = _FakeGateway(_sampleTree());
    final picker = _FakeDirectoryPicker('/pics');
    final memory = _FakeDirectoryMemory();

    CreateMediaPickerResult? result;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          fileStorageGatewayProvider.overrideWithValue(gateway),
          desktopDirectoryPickerProvider.overrideWithValue(picker),
          desktopPickerDirectoryMemoryProvider.overrideWithValue(memory),
        ],
        child: MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: Center(
                child: ElevatedButton(
                  onPressed: () async {
                    result = await Navigator.of(context)
                        .push<CreateMediaPickerResult>(
                          MaterialPageRoute<CreateMediaPickerResult>(
                            builder: (_) =>
                                DesktopImagePickerPage(maxSelection: 9),
                          ),
                        );
                  },
                  child: const Text('open'),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    // 初始无记忆目录 -> 选文件夹空态。
    expect(
      find.byKey(TestKeys.desktopPickerChooseFolderButton),
      findsOneWidget,
    );

    await tester.tap(find.byKey(TestKeys.desktopPickerChooseFolderButton));
    await tester.pumpAndSettle();

    // 扫描后出现网格；记忆已写入。
    expect(find.byKey(TestKeys.desktopPickerGrid), findsOneWidget);
    expect(memory.remembered, '/pics');

    // 跨目录聚合相册含 a/b/c 三张；按顺序选 b 再选 a。
    await tester.tap(
      find.byKey(const ValueKey<String>('desktop-picker-tile-/pics/b.jpg')),
    );
    await tester.pump();
    await tester.tap(
      find.byKey(const ValueKey<String>('desktop-picker-tile-/pics/a.jpg')),
    );
    await tester.pump();

    await tester.tap(find.byKey(TestKeys.desktopPickerConfirmButton));
    await tester.pumpAndSettle();

    expect(result, isNotNull);
    final paths = result!.items.map((e) => e.path).toList();
    // 选择顺序即返回顺序：先 b 后 a。
    expect(paths, <String>['/pics/b.jpg', '/pics/a.jpg']);
    expect(result!.items.every((e) => e.type == CreateMediaType.image), isTrue);
    expect(
      result!.items.every((e) => e.source == CreateMediaSource.album),
      isTrue,
    );
  });

  testWidgets('记忆了上次目录时，进入即自动扫描，无需再选文件夹', (tester) async {
    final gateway = _FakeGateway(_sampleTree());
    final picker = _FakeDirectoryPicker(null);
    final memory = _FakeDirectoryMemory('/pics');

    await openPicker(
      tester,
      gateway: gateway,
      directoryPicker: picker,
      memory: memory,
    );

    expect(find.byKey(TestKeys.desktopPickerChooseFolderButton), findsNothing);
    expect(find.byKey(TestKeys.desktopPickerGrid), findsOneWidget);
    // 自动扫描不应再弹目录选择框。
    expect(picker.callCount, 0);
  });

  testWidgets('超过 maxSelection 不再追加选择（确认计数仍为 1）', (tester) async {
    final gateway = _FakeGateway(_sampleTree());
    final picker = _FakeDirectoryPicker(null);
    final memory = _FakeDirectoryMemory('/pics');

    await openPicker(
      tester,
      gateway: gateway,
      directoryPicker: picker,
      memory: memory,
      maxSelection: 1,
    );

    await tester.tap(
      find.byKey(const ValueKey<String>('desktop-picker-tile-/pics/a.jpg')),
    );
    await tester.pump();
    // 第二次点击越过上限 -> 弹 toast 提示但不追加。
    await tester.tap(
      find.byKey(const ValueKey<String>('desktop-picker-tile-/pics/b.jpg')),
    );
    await tester.pump();

    // 确认按钮计数仍为 (1)，证明越限点击未被纳入选择。
    expect(find.text('完成 (1)'), findsOneWidget);
    expect(find.text('完成 (2)'), findsNothing);

    // 让 AppToast 的 3s 自动消失定时器触发，避免 widget 树 dispose 时仍有挂起 Timer。
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('P0：网格缩略图走降采样 ImageProvider（targetPx 按显示像素，防回退全分辨率）', (
    tester,
  ) async {
    final gateway = _FakeGateway(_sampleTree());
    final picker = _FakeDirectoryPicker(null);
    final memory = _FakeDirectoryMemory('/pics');

    await openPicker(
      tester,
      gateway: gateway,
      directoryPicker: picker,
      memory: memory,
    );

    expect(find.byKey(TestKeys.desktopPickerGrid), findsOneWidget);

    final tile = find.byKey(
      const ValueKey<String>('desktop-picker-tile-/pics/a.jpg'),
    );
    expect(tile, findsOneWidget);

    final image = tester.widget<Image>(
      find.descendant(of: tile, matching: find.byType(Image)),
    );
    // 必须是降采样 provider，而非全分辨率 MemoryImage/FileImage。
    expect(image.image, isA<DesktopThumbnailImage>());
    final provider = image.image as DesktopThumbnailImage;
    expect(provider.targetPx, greaterThan(0));
    // 缓存键稳定（同图同尺寸复用全局 imageCache，不重复解码）。
    expect(provider.path, '/pics/a.jpg');
  });

  testWidgets('能力位不支持本地文件系统时结构化降级为空态', (tester) async {
    final gateway = _FakeGateway(
      const <String, List<FileSystemEntry>>{},
      isSupported: false,
    );
    final picker = _FakeDirectoryPicker(null);
    final memory = _FakeDirectoryMemory();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          fileStorageGatewayProvider.overrideWithValue(gateway),
          desktopDirectoryPickerProvider.overrideWithValue(picker),
          desktopPickerDirectoryMemoryProvider.overrideWithValue(memory),
        ],
        child: const MaterialApp(home: DesktopImagePickerPage(maxSelection: 9)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.desktopPickerGrid), findsNothing);
    expect(find.byKey(TestKeys.desktopPickerChooseFolderButton), findsNothing);
  });
}
