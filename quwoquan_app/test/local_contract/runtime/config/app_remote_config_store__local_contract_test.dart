// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-002
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-004
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/runtime/config/app_remote_config_snapshot.dart';
import 'package:quwoquan_app/runtime/platform/storage/hive_app_remote_config_store.dart';
import 'package:quwoquan_app/runtime/platform/storage/hive_runtime.dart';

import '../../../support/service/content_service/content/post/test_content_app_config.dart';

void main() {
  late Directory tempDirectory;
  late HiveAppRemoteConfigStore store;

  setUp(() async {
    tempDirectory = await Directory.systemTemp.createTemp(
      'app_remote_config_store_test_',
    );
    Hive.init(tempDirectory.path);
    HiveRuntime.debugEnsureInitializedHook = () async => true;
    store = const HiveAppRemoteConfigStore();
  });

  tearDown(() async {
    HiveRuntime.resetForTest();
    await Hive.deleteFromDisk();
    if (await tempDirectory.exists()) {
      await tempDirectory.delete(recursive: true);
    }
  });

  test(
    'stable Hive keys rotate active snapshot without a second envelope',
    () async {
      final first = AppRemoteConfigSnapshot.fromRoot(
        testSignedAppConfigRoot(
          content: const <String, Object?>{
            'feature_flags': <String, Object?>{
              'enable_article_book_reader': true,
            },
          },
          fetchedAt: DateTime.now().toUtc(),
          maxAgeSec: 3600,
        ),
      );
      final second = AppRemoteConfigSnapshot.fromRoot(
        testSignedAppConfigRoot(
          content: const <String, Object?>{
            'feature_flags': <String, Object?>{
              'enable_article_book_reader': false,
            },
          },
          fetchedAt: DateTime.now().toUtc(),
          maxAgeSec: 3600,
        ),
      );

      await store.writeActiveSnapshot(first);
      await store.writeActiveSnapshot(second);

      final box = Hive.box<String>(HiveAppRemoteConfigStore.boxName);
      expect(box.keys.toSet(), <String>{
        HiveAppRemoteConfigStore.activeSnapshotKey,
        HiveAppRemoteConfigStore.previousSnapshotKey,
      });
      expect(
        jsonDecode(box.get(HiveAppRemoteConfigStore.previousSnapshotKey)!),
        first.toPersistedMap(),
      );
      expect(
        jsonDecode(box.get(HiveAppRemoteConfigStore.activeSnapshotKey)!),
        second.toPersistedMap(),
      );

      final hydrated = await store.readActiveSnapshot();
      expect(hydrated?.configHash, second.configHash);
      expect(hydrated?.source, AppRemoteConfigSource.diskCache);
    },
  );

  test('expired active snapshot is classified as stale disk cache', () async {
    final expired = AppRemoteConfigSnapshot.fromRoot(
      testSignedAppConfigRoot(fetchedAt: DateTime.utc(2020), maxAgeSec: 1),
    );

    await store.writeActiveSnapshot(expired);

    expect(
      (await store.readActiveSnapshot())?.source,
      AppRemoteConfigSource.staleDiskCache,
    );
  });

  test(
    'malformed active payload is ignored without a compatibility read',
    () async {
      final box = await Hive.openBox<String>(HiveAppRemoteConfigStore.boxName);
      await box.put(HiveAppRemoteConfigStore.activeSnapshotKey, '{malformed');

      expect(await store.readActiveSnapshot(), isNull);
    },
  );
}
