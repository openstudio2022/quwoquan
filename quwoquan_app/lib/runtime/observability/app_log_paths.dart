import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/runtime/platform/storage/local_text_file_storage_gateway.dart';

final class AppLogDirectoryPath {
  const AppLogDirectoryPath(this.path);

  final String path;
}

class AppLogPaths {
  AppLogPaths({
    LocalTextFileStorageGateway? storageGateway,
    this.rootDirName = 'quwoquan_logs',
  }) : storageGateway =
           storageGateway ??
           requireLocalTextFileStorageGateway(createFileStorageGateway());

  final String rootDirName;
  final LocalTextFileStorageGateway storageGateway;

  Future<AppLogDirectoryPath> rootDirectory() async {
    try {
      final supportPath = await storageGateway.applicationSupportPath();
      return AppLogDirectoryPath(
        storageGateway.joinPath(supportPath, rootDirName),
      );
    } catch (_) {
      final temporaryPath = await storageGateway.systemTemporaryPath();
      return AppLogDirectoryPath(
        storageGateway.joinPath(temporaryPath, rootDirName),
      );
    }
  }

  Future<AppLogDirectoryPath> dayDirectory(DateTime time) async {
    final root = await rootDirectory();
    final day = _dayStamp(time);
    return AppLogDirectoryPath(storageGateway.joinPath(root.path, day));
  }

  String _dayStamp(DateTime time) {
    final y = time.year.toString().padLeft(4, '0');
    final m = time.month.toString().padLeft(2, '0');
    final d = time.day.toString().padLeft(2, '0');
    return '$y-$m-$d';
  }
}
