// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cross-platform-portability/spec.md#gwt-001
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway_io.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway_web.dart';
import 'package:quwoquan_app/runtime/platform/platform_capability_unavailable.dart';
import 'package:quwoquan_app/runtime/platform/storage/local_text_file_storage_gateway.dart';

void main() {
  group('LocalTextFileStorageGateway', () {
    test('runtime factory returns one immutable platform composition', () {
      expect(
        identical(
          requireLocalTextFileStorageGateway(createFileStorageGateway()),
          requireLocalTextFileStorageGateway(createFileStorageGateway()),
        ),
        isTrue,
      );
    });

    test(
      'native implementation preserves append overwrite and delete modes',
      () async {
        final root = await Directory.systemTemp.createTemp(
          'qwq_local_text_storage_',
        );
        addTearDown(() async {
          if (await root.exists()) {
            await root.delete(recursive: true);
          }
        });
        const gateway = IoFileStorageGateway();
        final nested = gateway.joinPath(root.path, 'nested');
        final filePath = gateway.joinPath(nested, 'event.log');

        await gateway.ensureDirectory(nested);
        await gateway.appendAsString(filePath, 'first\n');
        await gateway.appendAsString(filePath, 'second\n');

        expect(await File(filePath).readAsString(), 'first\nsecond\n');
        final entries = await gateway.listDirectory(root.path);
        expect(
          entries,
          contains(
            isA<FileSystemEntry>()
                .having((entry) => entry.path, 'path', nested)
                .having((entry) => entry.isDirectory, 'isDirectory', isTrue),
          ),
        );

        await gateway.writeAsString(filePath, 'replacement');
        expect(await File(filePath).readAsString(), 'replacement');
        expect(gateway.fileExistsSync(filePath), isTrue);
        expect(gateway.fileLengthSync(filePath), 'replacement'.length);

        gateway.deleteFileSync(filePath);
        expect(await File(filePath).exists(), isFalse);
        await gateway.deleteDirectory(nested, recursive: true);
        expect(await Directory(nested).exists(), isFalse);
      },
    );

    test('web implementation fails closed for filesystem operations', () async {
      const gateway = WebFileStorageGateway();
      final unavailable = isA<PlatformCapabilityUnavailableException>().having(
        (error) => error.capability,
        'capability',
        'hasLocalFileSystem',
      );

      expect(gateway.isSupported, isFalse);
      await expectLater(gateway.applicationSupportPath(), throwsA(unavailable));
      await expectLater(
        gateway.appendAsString('/event.log', 'line'),
        throwsA(unavailable),
      );
      await expectLater(gateway.listDirectory('/logs'), throwsA(unavailable));
      await expectLater(
        gateway.deleteDirectory('/logs', recursive: true),
        throwsA(unavailable),
      );
      expect(
        () => gateway.joinPath('/logs', 'event.log'),
        throwsA(unavailable),
      );
    });
  });
}
