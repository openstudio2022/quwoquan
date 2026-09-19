// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_space_binding.dart';
import 'package:quwoquan_app/runtime/config/app_content_source.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';

/// 全部操作只发生在测试私有 Map，不读本机 keychain/用户目录。
class PrivateStorage implements FileStorageGateway, AtomicFileStorageGateway {
  final files = <String, String>{};
  final calls = <String>[];
  @override
  bool get isSupported => true;
  @override
  Future<String> applicationSupportPath() async => '/private-test';
  @override
  Future<void> ensureDirectory(String path) async {
    calls.add('directory:$path');
  }

  @override
  Future<bool> exists(String path) async {
    calls.add('exists:$path');
    return files.containsKey(path);
  }

  @override
  Future<String> readAsString(String path) async {
    calls.add('read:$path');
    return files[path]!;
  }

  @override
  Future<void> writeAsStringAtomically(
    String path,
    String contents, {
    void Function()? beforeCommit,
  }) async {
    beforeCommit?.call();
    calls.add('write:$path');
    files[path] = contents;
  }

  @override
  Future<void> delete(String path) async {
    calls.add('delete:$path');
    files.remove(path);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('Unexpected storage operation');
}

void main() {
  final digest = 'sha256:${List.filled(64, 'a').join()}';
  RehearsalSpaceBinding binding(String id) => RehearsalSpaceBinding.isolated(
    source: AppContentSource.bundledSnapshot,
    snapshotDigest: digest,
    selectedInstanceId: id,
    expectedInstanceId: id,
  );

  test('显式 isolated 缺失错配 default remote 均在 I/O 前拒绝', () {
    for (final selected in <String?>[
      null,
      '',
      'default',
      '../escape',
      ' other',
      'other',
    ]) {
      expect(
        () => RehearsalSpaceBinding.isolated(
          source: AppContentSource.bundledSnapshot,
          snapshotDigest: digest,
          selectedInstanceId: selected,
          expectedInstanceId: 'isolated',
        ),
        throwsA(isA<Object>()),
      );
    }
    expect(
      () => RehearsalSpaceBinding.isolated(
        source: AppContentSource.remote,
        snapshotDigest: digest,
        selectedInstanceId: 'isolated',
        expectedInstanceId: 'isolated',
      ),
      throwsA(isA<Object>()),
    );
    expect(() => binding('default'), throwsA(isA<Object>()));
  });

  test('未验签内部纯构造不得取得公共 auth OTP namespace', () {
    final a = binding('space-a');
    expect(() => a.isolatedAuthNamespace, throwsA(isA<Object>()));
    expect(() => a.isolatedPendingOtpKey, throwsA(isA<Object>()));
    expect(
      () => a.verifyStorage(snapshot: digest, instance: 'default'),
      throwsA(isA<Object>()),
    );
    final standard = RehearsalSpaceBinding.standard(
      source: AppContentSource.bundledSnapshot,
      snapshotDigest: digest,
    );
    expect(standard.instanceId, 'default');
    expect(standard.isIsolated, false);
    expect(() => standard.isolatedAuthNamespace, throwsA(isA<Object>()));
  });

  test('私有文件新空间持久和新 store 恢复，旧空间 read/write/delete 零触达', () async {
    final storage = PrivateStorage();
    final old =
        '/private-test/alpha_rehearsal/${digest.replaceAll(':', '_')}_default.json';
    storage.files[old] = 'old-space-sentinel';
    final first = AlphaRehearsalStore.bound(
      binding: binding('space-a'),
      gateway: storage,
    );
    await first.commit(() {
      first.currentOwnerId = 'local-synthetic-owner';
    });
    final restart = AlphaRehearsalStore.bound(
      binding: binding('space-a'),
      gateway: storage,
    );
    await restart.ensureLoaded();
    expect(restart.currentOwnerId, 'local-synthetic-owner');
    final other = AlphaRehearsalStore.bound(
      binding: binding('space-b'),
      gateway: storage,
    );
    await other.ensureLoaded();
    expect(other.currentOwnerId, isNull);
    await other.resetSpace();
    expect(storage.calls.where((call) => call.endsWith(old)), isEmpty);
    expect(storage.files[old], 'old-space-sentinel');
  });

  test('损坏隔离空间不清旧空间，也不保存伪恢复成功', () async {
    final storage = PrivateStorage();
    final prefix =
        '/private-test/alpha_rehearsal/${digest.replaceAll(':', '_')}';
    storage.files['${prefix}_default.json'] = 'old-space-sentinel';
    storage.files['${prefix}_space-a.json'] = 'corrupt';
    final store = AlphaRehearsalStore.bound(
      binding: binding('space-a'),
      gateway: storage,
    );
    await expectLater(store.ensureLoaded(), throwsA(isA<Object>()));
    expect(
      storage.calls.where(
        (call) =>
            call.startsWith('write:') ||
            call.startsWith('delete:') ||
            call.endsWith('_default.json'),
      ),
      isEmpty,
    );
    expect(storage.files['${prefix}_default.json'], 'old-space-sentinel');
    expect(storage.files['${prefix}_space-a.json'], 'corrupt');
  });
  test('envelope 与文件空间错配必须在旧空间任何 I/O 前拒绝', () async {
    final storage = PrivateStorage();
    final old = '/private-test/alpha_rehearsal/sha256_snapshot_default.json';
    storage.files[old] = 'old-space-sentinel';
    Future<void> openMismatch() async {
      final store = AlphaRehearsalStore(
        snapshotDigest: 'sha256:snapshot',
        instanceId: 'isolated',
        persistence: FileRehearsalPersistence(
          gateway: storage,
          snapshotDigest: 'sha256:snapshot',
        ),
      );
      await store.ensureLoaded();
    }

    await expectLater(openMismatch(), throwsA(isA<Object>()));
    expect(storage.calls, isEmpty, reason: '拒绝必须发生在旧空间存在性/读取/写入/删除之前');
    expect(storage.files[old], 'old-space-sentinel');
  });
}
