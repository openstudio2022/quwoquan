// 会话/全局图片内存缓存字节上界契约：上界唯一来源于 AppResourceCacheProfile，
// 灌入超预算图片后 LRU 淘汰使实际字节不超过声明上界。
//
// 禁止第二份上限值：本测试全部阈值均从 AppResourceCacheProfile 读取。
//
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-runtime-performance-budget/spec.md#gwt-002.t2
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
// ignore: depend_on_referenced_packages
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:quwoquan_app/runtime/platform/media/app_image_cache_controller.dart';

import '../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';

class _FakePathProviderPlatform extends PathProviderPlatform {
  _FakePathProviderPlatform(this.root);

  final Directory root;

  String _path(String name) {
    final directory = Directory('${root.path}/$name')
      ..createSync(recursive: true);
    return directory.path;
  }

  @override
  Future<String?> getTemporaryPath() async => _path('tmp');

  @override
  Future<String?> getApplicationSupportPath() async => _path('support');

  @override
  Future<String?> getApplicationDocumentsPath() async => _path('documents');

  @override
  Future<String?> getApplicationCachePath() async => _path('cache');
}

Future<ui.Image> _syntheticImage(int dimension) {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  canvas.drawRect(
    Rect.fromLTWH(0, 0, dimension.toDouble(), dimension.toDouble()),
    Paint()..color = const Color(0xFF336699),
  );
  return recorder.endRecording().toImage(dimension, dimension);
}

Future<int> _fillCacheWithImage(ImageCache cache, ui.Image image, int key) async {
  final completer = OneFrameImageStreamCompleter(
    SynchronousFuture<ImageInfo>(ImageInfo(image: image)),
  );
  final stream = cache.putIfAbsent(
    'image-cache-budget-sample-$key',
    () => completer,
  );
  final listener = ImageStreamListener((info, syncCall) {});
  stream!.addListener(listener);
  stream.removeListener(listener);
  return image.height * image.width * 4;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory cacheTestRoot;
  late PathProviderPlatform previousPathProvider;

  setUpAll(() {
    ensureSqfliteFfiInitialized();
    cacheTestRoot = Directory.systemTemp.createTempSync(
      'qwq_image_cache_budget_',
    );
    previousPathProvider = PathProviderPlatform.instance;
    PathProviderPlatform.instance = _FakePathProviderPlatform(cacheTestRoot);
  });

  tearDownAll(() {
    PathProviderPlatform.instance = previousPathProvider;
    if (cacheTestRoot.existsSync()) {
      cacheTestRoot.deleteSync(recursive: true);
    }
  });

  tearDown(() {
    final cache = PaintingBinding.instance.imageCache;
    cache.clear();
    cache.clearLiveImages();
  });

  test('applyResourceProfile 把 profile 声明安装为唯一内存缓存上界', () {
    for (final profile in <AppResourceCacheProfile>[
      AppResourceCacheProfile.compact,
      AppResourceCacheProfile.regular,
      AppResourceCacheProfile.expanded,
    ]) {
      AppImageCacheController.applyResourceProfile(profile);
      final cache = PaintingBinding.instance.imageCache;
      expect(
        cache.maximumSizeBytes,
        profile.maxImageCacheBytes,
        reason: '${profile.name} 档位的字节上界必须与 profile 声明一致',
      );
      expect(
        cache.maximumSize,
        profile.maxImageCacheObjects,
        reason: '${profile.name} 档位的对象数上界必须与 profile 声明一致',
      );
    }
  });

  test('灌入超预算图片后实际缓存字节经 LRU 淘汰不超过声明上界', () async {
    const profile = AppResourceCacheProfile.compact;
    AppImageCacheController.applyResourceProfile(profile);
    final cache = PaintingBinding.instance.imageCache;
    cache.clear();

    // 每张 2048x2048 RGBA 约 16MiB；灌入总量超过 compact 上界（64MiB）。
    const dimension = 2048;
    const imageCount = 6;
    final image = await _syntheticImage(dimension);
    var injectedBytes = 0;
    for (var index = 0; index < imageCount; index++) {
      injectedBytes += await _fillCacheWithImage(cache, image, index);
    }

    expect(
      injectedBytes,
      greaterThan(profile.maxImageCacheBytes),
      reason: '样本必须真实超过声明上界，否则淘汰断言无意义',
    );
    expect(
      cache.currentSizeBytes,
      lessThanOrEqualTo(profile.maxImageCacheBytes),
      reason: '超预算灌入后 LRU 淘汰必须使实际字节回到声明上界内',
    );
    expect(
      cache.currentSize,
      lessThanOrEqualTo(profile.maxImageCacheObjects),
      reason: '缓存对象数同样不得超过 profile 声明',
    );
  });
}
