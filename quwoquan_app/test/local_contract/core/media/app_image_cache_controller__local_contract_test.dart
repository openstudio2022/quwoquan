import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
// ignore: depend_on_referenced_packages
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:quwoquan_app/cloud/media/cdn_image_url_builder.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/media/app_image_cache_controller.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';

import '../../../support/sqflite_ffi_test_support.dart';

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

final Uint8List _transparentImage = Uint8List.fromList(<int>[
  0x89,
  0x50,
  0x4E,
  0x47,
  0x0D,
  0x0A,
  0x1A,
  0x0A,
  0x00,
  0x00,
  0x00,
  0x0D,
  0x49,
  0x48,
  0x44,
  0x52,
  0x00,
  0x00,
  0x00,
  0x01,
  0x00,
  0x00,
  0x00,
  0x01,
  0x08,
  0x06,
  0x00,
  0x00,
  0x00,
  0x1F,
  0x15,
  0xC4,
  0x89,
  0x00,
  0x00,
  0x00,
  0x0A,
  0x49,
  0x44,
  0x41,
  0x54,
  0x78,
  0x9C,
  0x62,
  0x00,
  0x00,
  0x00,
  0x02,
  0x00,
  0x01,
  0xE5,
  0x27,
  0xDE,
  0xFC,
  0x00,
  0x00,
  0x00,
  0x00,
  0x49,
  0x45,
  0x4E,
  0x44,
  0xAE,
  0x42,
  0x60,
  0x82,
]);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory cacheTestRoot;
  late PathProviderPlatform previousPathProvider;

  setUpAll(() {
    ensureSqfliteFfiInitialized();
    previousPathProvider = PathProviderPlatform.instance;
    cacheTestRoot = Directory.systemTemp.createTempSync(
      'qwq-avatar-cache-controller-test-',
    );
    PathProviderPlatform.instance = _FakePathProviderPlatform(cacheTestRoot);
  });

  tearDownAll(() {
    PathProviderPlatform.instance = previousPathProvider;
    try {
      if (cacheTestRoot.existsSync()) {
        cacheTestRoot.deleteSync(recursive: true);
      }
    } on FileSystemException catch (error) {
      if (error.osError?.errorCode != 2) {
        rethrow;
      }
    }
  });

  test('evictAvatar 只驱逐原 URL 的登录头像缓存', () async {
    const target = 'media/avatar/s/mock/user/current/v1/avatar.png';
    const untouched = 'media/avatar/s/mock/user/other/v1/avatar.png';
    final targetCacheKeys = resolveAvatarImageUrlCandidates(target)
        .map(
          (candidate) => CdnImageUrlBuilder.avatar(
            candidate,
            size: AppSpacing.loginAvatarSize.toInt(),
          ),
        )
        .toSet();
    final untouchedCacheKeys = resolveAvatarImageUrlCandidates(untouched)
        .map(
          (candidate) => CdnImageUrlBuilder.avatar(
            candidate,
            size: AppSpacing.loginAvatarSize.toInt(),
          ),
        )
        .toSet();
    expect(targetCacheKeys, isNotEmpty);
    expect(untouchedCacheKeys, isNotEmpty);
    final manager = AppImageCacheController.cacheManagerForPreset(
      CdnImagePreset.avatar,
    );
    for (final cacheKey in targetCacheKeys) {
      await manager.putFile(cacheKey, _transparentImage);
    }
    for (final cacheKey in untouchedCacheKeys) {
      await manager.putFile(cacheKey, _transparentImage);
    }

    await AppImageCacheController.evictAvatar(
      target,
      size: AppSpacing.loginAvatarSize,
    );

    for (final cacheKey in targetCacheKeys) {
      expect(await manager.getFileFromCache(cacheKey), isNull);
    }
    for (final cacheKey in untouchedCacheKeys) {
      expect(await manager.getFileFromCache(cacheKey), isNotNull);
      await manager.removeFile(cacheKey);
    }
  });
}
