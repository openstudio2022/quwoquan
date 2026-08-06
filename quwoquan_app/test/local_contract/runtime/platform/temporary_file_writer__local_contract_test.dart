import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:quwoquan_app/runtime/platform/temporary_file_writer.dart';

final class _TemporaryPathProvider extends PathProviderPlatform {
  _TemporaryPathProvider(this.path);

  final String path;

  @override
  Future<String?> getTemporaryPath() async => path;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late PathProviderPlatform previousPathProvider;
  late Directory temporaryDirectory;

  setUp(() async {
    previousPathProvider = PathProviderPlatform.instance;
    temporaryDirectory = await Directory.systemTemp.createTemp(
      'qwq-temp-writer-',
    );
    PathProviderPlatform.instance = _TemporaryPathProvider(
      temporaryDirectory.path,
    );
  });

  tearDown(() async {
    PathProviderPlatform.instance = previousPathProvider;
    if (await temporaryDirectory.exists()) {
      await temporaryDirectory.delete(recursive: true);
    }
  });

  test(
    'temporary writer persists exact bytes below the App temp root',
    () async {
      final fileName =
          'qwq-temp-writer-${DateTime.now().microsecondsSinceEpoch}.bin';
      final path = await writeAppTemporaryFileBytes(
        fileName: fileName,
        bytes: <int>[7, 8, 9],
      );
      expect(path, endsWith(fileName));
      expect(await File(path).readAsBytes(), <int>[7, 8, 9]);
    },
  );

  test('temporary writer rejects path traversal', () async {
    await expectLater(
      writeAppTemporaryFileBytes(
        fileName: '../outside.bin',
        bytes: const <int>[1],
      ),
      throwsArgumentError,
    );
  });
}
