import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/content/media/media_upload_session/presentation/desktop_thumbnail_image_provider.dart';
import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';

class _BytesGateway implements FileStorageGateway {
  _BytesGateway(this._bytes);
  final List<int> _bytes;
  @override
  bool get isSupported => true;
  @override
  Future<List<int>> readAsBytes(String path) async => _bytes;
  @override
  Future<List<FileSystemEntry>> listDirectory(String path) =>
      throw UnimplementedError();
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

class _ThrowingGateway extends _BytesGateway {
  _ThrowingGateway() : super(const <int>[]);
  @override
  Future<List<int>> readAsBytes(String path) async =>
      throw const FileSystemAccessFailure();
}

class FileSystemAccessFailure implements Exception {
  const FileSystemAccessFailure();
}

/// 用引擎生成一张纯色 PNG（边长 [size]）。
Future<List<int>> _solidPng(int size) async {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(
    recorder,
    Rect.fromLTWH(0, 0, size.toDouble(), size.toDouble()),
  );
  canvas.drawRect(
    Rect.fromLTWH(0, 0, size.toDouble(), size.toDouble()),
    Paint()..color = const Color(0xFF3366AA),
  );
  final picture = recorder.endRecording();
  final image = await picture.toImage(size, size);
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  return data!.buffer.asUint8List();
}

Future<ui.Image> _resolve(ImageProvider provider) {
  final completer = Completer<ui.Image>();
  final stream = provider.resolve(ImageConfiguration.empty);
  late ImageStreamListener listener;
  listener = ImageStreamListener(
    (info, _) {
      if (!completer.isCompleted) completer.complete(info.image);
      stream.removeListener(listener);
    },
    onError: (error, stack) {
      if (!completer.isCompleted) completer.completeError(error);
      stream.removeListener(listener);
    },
  );
  stream.addListener(listener);
  return completer.future;
}

void main() {
  setUp(() {
    PaintingBinding.instance.imageCache.clear();
    PaintingBinding.instance.imageCache.clearLiveImages();
  });

  testWidgets('降采样：8×8 原图 targetPx=4 解码为短边 4（位图按显示尺寸缩小）',
      (tester) async {
    await tester.runAsync(() async {
      final gateway = _BytesGateway(await _solidPng(8));
      final provider = DesktopThumbnailImage(
        'a',
        gateway: gateway,
        targetPx: 4,
      );
      final image = await _resolve(provider);
      expect(image.width, 4);
      expect(image.height, 4);
    });
  });

  testWidgets('不放大：原图短边 ≤ targetPx 时保持原尺寸', (tester) async {
    await tester.runAsync(() async {
      final gateway = _BytesGateway(await _solidPng(8));
      final provider = DesktopThumbnailImage(
        'b',
        gateway: gateway,
        targetPx: 64,
      );
      final image = await _resolve(provider);
      expect(image.width, 8);
      expect(image.height, 8);
    });
  });

  testWidgets('读字节失败经 error 通道上报（由 Image.errorBuilder 降级占位）',
      (tester) async {
    await tester.runAsync(() async {
      final provider = DesktopThumbnailImage(
        'c',
        gateway: _ThrowingGateway(),
        targetPx: 4,
      );
      await expectLater(_resolve(provider), throwsA(isA<FileSystemAccessFailure>()));
    });
  });

  test('缓存键：path/targetPx/scale 相同则相等', () {
    const a = DesktopThumbnailKey('p', 100, 1.0);
    const b = DesktopThumbnailKey('p', 100, 1.0);
    const c = DesktopThumbnailKey('p', 200, 1.0);
    expect(a, b);
    expect(a.hashCode, b.hashCode);
    expect(a == c, isFalse);
  });
}
