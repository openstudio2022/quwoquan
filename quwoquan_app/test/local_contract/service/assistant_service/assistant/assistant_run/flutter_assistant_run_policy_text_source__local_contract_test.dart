import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/adapters/flutter_assistant_run_policy_text_source.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';

void main() {
  test('asset policy wins without touching the file gateway', () async {
    final assets = _PolicyAssetBundle(value: '{"source":"asset"}');
    final files = _PolicyFileStorageGateway(
      supported: true,
      existsResult: true,
      value: '{"source":"file"}',
    );
    final source = FlutterAssistantRunPolicyTextSource(
      assetBundle: assets,
      fileStorageGateway: files,
    );

    expect(await source.read('policy.json'), '{"source":"asset"}');
    expect(assets.loadCount, 1);
    expect(files.existsCount, 0);
    expect(files.readCount, 0);
  });

  test(
    'file gateway is the explicit fallback when the asset is absent',
    () async {
      final assets = _PolicyAssetBundle(error: StateError('asset missing'));
      final files = _PolicyFileStorageGateway(
        supported: true,
        existsResult: true,
        value: '{"source":"file"}',
      );
      final source = FlutterAssistantRunPolicyTextSource(
        assetBundle: assets,
        fileStorageGateway: files,
      );

      expect(await source.read('policy.json'), '{"source":"file"}');
      expect(files.existsCount, 1);
      expect(files.readCount, 1);
    },
  );

  test('unsupported file fallback preserves the asset failure', () async {
    final failure = StateError('asset missing');
    final source = FlutterAssistantRunPolicyTextSource(
      assetBundle: _PolicyAssetBundle(error: failure),
      fileStorageGateway: _PolicyFileStorageGateway(
        supported: false,
        existsResult: false,
        value: '',
      ),
    );

    await expectLater(source.read('policy.json'), throwsA(same(failure)));
  });
}

final class _PolicyAssetBundle extends CachingAssetBundle {
  _PolicyAssetBundle({this.value, this.error});

  final String? value;
  final Object? error;
  int loadCount = 0;

  @override
  Future<ByteData> load(String key) async {
    loadCount += 1;
    final failure = error;
    if (failure != null) {
      throw failure;
    }
    return ByteData.sublistView(Uint8List.fromList(utf8.encode(value ?? '')));
  }
}

final class _PolicyFileStorageGateway implements FileStorageGateway {
  _PolicyFileStorageGateway({
    required this.supported,
    required this.existsResult,
    required this.value,
  });

  final bool supported;
  final bool existsResult;
  final String value;
  int existsCount = 0;
  int readCount = 0;

  @override
  bool get isSupported => supported;

  @override
  Future<bool> exists(String path) async {
    existsCount += 1;
    return existsResult;
  }

  @override
  Future<String> readAsString(String path) async {
    readCount += 1;
    return value;
  }

  @override
  Future<String> applicationSupportPath() async => '';

  @override
  Future<void> delete(String path) async {}

  @override
  Future<void> ensureDirectory(String path) async {}

  @override
  Future<List<FileSystemEntry>> listDirectory(String path) async =>
      const <FileSystemEntry>[];

  @override
  Future<List<int>> readAsBytes(String path) async => const <int>[];

  @override
  Future<String> temporaryPath() async => '';

  @override
  Future<void> writeAsBytes(String path, List<int> bytes) async {}

  @override
  Future<void> writeAsString(String path, String contents) async {}
}
