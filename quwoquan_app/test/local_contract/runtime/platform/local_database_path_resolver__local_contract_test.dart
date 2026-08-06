// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cross-platform-portability/spec.md#gwt-001
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/runtime/platform/platform_capability_unavailable.dart';
import 'package:quwoquan_app/runtime/platform/storage/local_database_path_resolver.dart';
import 'package:quwoquan_app/runtime/platform/storage/local_database_path_resolver_web.dart';

void main() {
  group('LocalDatabasePathResolver', () {
    test(
      'preserves an explicit path and ensures only its parent directory',
      () async {
        final storage = _RecordingFileStorageGateway();
        final resolver = createLocalDatabasePathResolver(storage);
        final path =
            '${Platform.pathSeparator}tmp${Platform.pathSeparator}'
            'quwoquan${Platform.pathSeparator}search.db';

        final resolved = await resolver.resolve(
          explicitPath: '  $path  ',
          fileName: 'ignored.db',
          loadDefaultDirectory: () async => throw StateError('must not load'),
        );

        expect(resolved, path);
        expect(storage.ensuredDirectories, <String>[
          '${Platform.pathSeparator}tmp${Platform.pathSeparator}quwoquan',
        ]);
      },
    );

    test(
      'uses the driver directory and platform separator for default path',
      () async {
        final storage = _RecordingFileStorageGateway();
        final resolver = createLocalDatabasePathResolver(storage);
        final basePath =
            '${Platform.pathSeparator}app${Platform.pathSeparator}db';

        final resolved = await resolver.resolve(
          explicitPath: '   ',
          fileName: 'local_search.db',
          loadDefaultDirectory: () async => basePath,
        );

        expect(resolved, '$basePath${Platform.pathSeparator}local_search.db');
        expect(storage.ensuredDirectories, <String>[basePath]);
      },
    );

    test('web fails closed before loading a database directory', () async {
      var directoryLoaderCalled = false;

      await expectLater(
        const WebLocalDatabasePathResolver().resolve(
          fileName: 'local_search.db',
          loadDefaultDirectory: () async {
            directoryLoaderCalled = true;
            return '/must-not-load';
          },
        ),
        throwsA(
          isA<PlatformCapabilityUnavailableException>()
              .having(
                (error) => error.capability,
                'capability',
                'hasLocalFileSystem',
              )
              .having(
                (error) => error.detail,
                'detail',
                'Local SQLite database paths are not available on web',
              ),
        ),
      );
      expect(directoryLoaderCalled, isFalse);
    });
  });
}

final class _RecordingFileStorageGateway implements FileStorageGateway {
  final List<String> ensuredDirectories = <String>[];

  @override
  bool get isSupported => true;

  @override
  Future<void> ensureDirectory(String path) async {
    ensuredDirectories.add(path);
  }

  @override
  Future<String> applicationSupportPath() => _unused();

  @override
  Future<void> delete(String path) => _unused();

  @override
  Future<bool> exists(String path) => _unused();

  @override
  Future<List<FileSystemEntry>> listDirectory(String path) => _unused();

  @override
  Future<List<int>> readAsBytes(String path) => _unused();

  @override
  Future<String> readAsString(String path) => _unused();

  @override
  Future<String> temporaryPath() => _unused();

  @override
  Future<void> writeAsBytes(String path, List<int> bytes) => _unused();

  @override
  Future<void> writeAsString(String path, String contents) => _unused();

  Future<T> _unused<T>() async => throw UnsupportedError('unused in contract');
}
