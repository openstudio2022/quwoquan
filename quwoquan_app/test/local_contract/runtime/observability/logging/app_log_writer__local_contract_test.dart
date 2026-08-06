// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cross-platform-portability/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/observability/app_log_paths.dart';
import 'package:quwoquan_app/runtime/observability/app_log_writer.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/runtime/platform/storage/local_text_file_storage_gateway.dart';

void main() {
  group('AppLogWriter platform boundary', () {
    test('rejects mismatched path and write gateways in release semantics', () {
      final pathStorage = _MemoryLocalTextFileStorageGateway();
      final writeStorage = _MemoryLocalTextFileStorageGateway();

      expect(
        () => AppLogWriter(
          paths: AppLogPaths(storageGateway: pathStorage),
          storageGateway: writeStorage,
        ),
        throwsArgumentError,
      );
    });

    test(
      'support path failure falls back to the system temporary path',
      () async {
        final storage = _MemoryLocalTextFileStorageGateway(
          supportPathError: StateError('support directory unavailable'),
        );

        final root = await AppLogPaths(storageGateway: storage).rootDirectory();

        expect(root.path, '/system-temp/quwoquan_logs');
        expect(storage.applicationSupportLookups, 1);
        expect(storage.systemTemporaryLookups, 1);
      },
    );

    test('appends complete lines in one stable day directory', () async {
      final storage = _MemoryLocalTextFileStorageGateway();
      final writer = AppLogWriter(storageGateway: storage);
      final at = DateTime(2026, 8, 6, 9, 30);

      final firstPath = await writer.appendLogLine(
        subDirectory: 'app',
        fileName: 'event.log',
        line: 'first',
        at: at,
      );
      final secondPath = await writer.appendLogLine(
        subDirectory: 'app',
        fileName: 'event.log',
        line: 'second',
        at: at,
      );

      expect(firstPath, '/support/quwoquan_logs/2026-08-06/app/event.log');
      expect(secondPath, firstPath);
      expect(storage.files[firstPath], 'first\nsecond\n');
    });

    test(
      'JSON writes overwrite with the canonical two-space encoding',
      () async {
        final storage = _MemoryLocalTextFileStorageGateway();
        final writer = AppLogWriter(storageGateway: storage);
        final at = DateTime(2026, 8, 6);

        final path = await writer.writeJsonFile(
          subDirectory: 'diagnostics',
          fileName: 'snapshot.json',
          payload: const <String, dynamic>{'stale': true},
          at: at,
        );
        await writer.writeJsonFile(
          subDirectory: 'diagnostics',
          fileName: 'snapshot.json',
          payload: const <String, dynamic>{
            'status': 'ready',
            'nested': <String, dynamic>{'attempt': 2},
          },
          at: at,
        );

        expect(
          storage.files[path],
          '{\n'
          '  "status": "ready",\n'
          '  "nested": {\n'
          '    "attempt": 2\n'
          '  }\n'
          '}',
        );
      },
    );

    test('prunes only parseable day directories older than keepDays', () async {
      final storage = _MemoryLocalTextFileStorageGateway();
      const root = '/support/quwoquan_logs';
      final today = DateTime.now();
      final midnight = DateTime(today.year, today.month, today.day);
      final staleDay = _dayStamp(midnight.subtract(const Duration(days: 8)));
      final boundaryDay = _dayStamp(midnight.subtract(const Duration(days: 7)));
      storage.directoryEntries[root] = <FileSystemEntry>[
        FileSystemEntry(path: '$root/$staleDay', isDirectory: true),
        FileSystemEntry(path: '$root/$boundaryDay', isDirectory: true),
        const FileSystemEntry(path: '$root/not-a-day', isDirectory: true),
        FileSystemEntry(path: '$root/$staleDay.log', isDirectory: false),
      ];
      final writer = AppLogWriter(storageGateway: storage, keepDays: 7);

      await writer.appendLogLine(
        subDirectory: 'app',
        fileName: 'event.log',
        line: 'trigger prune',
        at: midnight,
      );
      await _waitUntil(() => storage.deletedDirectories.isNotEmpty);

      expect(storage.deletedDirectories, <String>['$root/$staleDay']);
      expect(storage.deleteRecursiveFlags, <bool>[true]);
    });

    test(
      'write errors propagate without poisoning the serialized queue',
      () async {
        final storage = _MemoryLocalTextFileStorageGateway(
          nextAppendError: StateError('disk full'),
        );
        final writer = AppLogWriter(storageGateway: storage);
        final at = DateTime(2026, 8, 6);

        await expectLater(
          writer.appendLogLine(
            subDirectory: 'app',
            fileName: 'event.log',
            line: 'failed',
            at: at,
          ),
          throwsA(isA<StateError>()),
        );
        final path = await writer.appendLogLine(
          subDirectory: 'app',
          fileName: 'event.log',
          line: 'recovered',
          at: at,
        );

        expect(storage.files[path], 'recovered\n');
      },
    );

    test('unsupported platforms retain the web no-op path', () async {
      final storage = _MemoryLocalTextFileStorageGateway(isSupported: false);
      final writer = AppLogWriter(storageGateway: storage);

      final path = await writer.appendLogLine(
        subDirectory: 'app',
        fileName: 'event.log',
        line: 'not persisted',
      );

      expect(path, 'web://app-log/app/event.log');
      expect(storage.operationCount, 0);
    });
  });
}

final class _MemoryLocalTextFileStorageGateway
    implements LocalTextFileStorageGateway {
  _MemoryLocalTextFileStorageGateway({
    this.isSupported = true,
    this.supportPathError,
    this.nextAppendError,
  });

  @override
  final bool isSupported;
  final Object? supportPathError;
  Object? nextAppendError;
  int applicationSupportLookups = 0;
  int systemTemporaryLookups = 0;
  int operationCount = 0;
  final Set<String> directories = <String>{};
  final Map<String, String> files = <String, String>{};
  final Map<String, List<FileSystemEntry>> directoryEntries =
      <String, List<FileSystemEntry>>{};
  final List<String> deletedDirectories = <String>[];
  final List<bool> deleteRecursiveFlags = <bool>[];

  @override
  Future<String> applicationSupportPath() async {
    operationCount += 1;
    applicationSupportLookups += 1;
    final error = supportPathError;
    if (error != null) {
      throw error;
    }
    return '/support';
  }

  @override
  Future<String> systemTemporaryPath() async {
    operationCount += 1;
    systemTemporaryLookups += 1;
    return '/system-temp';
  }

  @override
  String joinPath(String parent, String child) {
    operationCount += 1;
    return '$parent/$child';
  }

  @override
  String basename(String path) {
    operationCount += 1;
    final segments = path
        .split('/')
        .where((segment) => segment.isNotEmpty)
        .toList(growable: false);
    return segments.isEmpty ? '' : segments.last;
  }

  @override
  Future<bool> directoryExists(String path) async {
    operationCount += 1;
    return directories.contains(path) ||
        directories.any((directory) => directory.startsWith('$path/'));
  }

  @override
  Future<void> ensureDirectory(String path) async {
    operationCount += 1;
    directories.add(path);
  }

  @override
  Future<void> appendAsString(String path, String contents) async {
    operationCount += 1;
    final error = nextAppendError;
    nextAppendError = null;
    if (error != null) {
      throw error;
    }
    files[path] = '${files[path] ?? ''}$contents';
  }

  @override
  Future<bool> exists(String path) async => files.containsKey(path);

  @override
  Future<String> readAsString(String path) async =>
      files[path] ?? (throw StateError('missing file: $path'));

  @override
  Future<List<int>> readAsBytes(String path) async =>
      throw UnsupportedError('unused in AppLogWriter contract');

  @override
  Future<void> writeAsBytes(String path, List<int> bytes) async =>
      throw UnsupportedError('unused in AppLogWriter contract');

  @override
  Future<void> delete(String path) async {
    files.remove(path);
  }

  @override
  Future<String> temporaryPath() async => '/temporary';

  @override
  Future<void> writeAsString(String path, String contents) async {
    operationCount += 1;
    files[path] = contents;
  }

  @override
  Future<List<FileSystemEntry>> listDirectory(String path) async {
    operationCount += 1;
    return directoryEntries[path] ?? const <FileSystemEntry>[];
  }

  @override
  Future<void> deleteDirectory(String path, {required bool recursive}) async {
    operationCount += 1;
    deletedDirectories.add(path);
    deleteRecursiveFlags.add(recursive);
    directories.removeWhere(
      (directory) => directory == path || directory.startsWith('$path/'),
    );
  }
}

Future<void> _waitUntil(bool Function() predicate) async {
  for (var attempt = 0; attempt < 100 && !predicate(); attempt += 1) {
    await Future<void>.delayed(Duration.zero);
  }
  expect(predicate(), isTrue, reason: 'asynchronous prune did not complete');
}

String _dayStamp(DateTime time) {
  final year = time.year.toString().padLeft(4, '0');
  final month = time.month.toString().padLeft(2, '0');
  final day = time.day.toString().padLeft(2, '0');
  return '$year-$month-$day';
}
