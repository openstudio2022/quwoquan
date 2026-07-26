import 'dart:io';

import 'package:path_provider/path_provider.dart';

Future<void> deletePlatformTemporaryFile(String path) async {
  final normalized = path.trim();
  if (normalized.isEmpty) {
    return;
  }
  final file = File(normalized);
  if (!await file.exists()) {
    return;
  }
  final temporaryDirectory = await getTemporaryDirectory();
  final resolvedRoot = await temporaryDirectory.resolveSymbolicLinks();
  final resolvedFile = await file.resolveSymbolicLinks();
  final rootPrefix = resolvedRoot.endsWith(Platform.pathSeparator)
      ? resolvedRoot
      : '$resolvedRoot${Platform.pathSeparator}';
  if (!resolvedFile.startsWith(rootPrefix)) {
    throw StateError(
      'refusing to delete a file outside the temporary directory',
    );
  }
  await file.delete();
  if (await file.exists()) {
    throw StateError('temporary file cleanup verification failed');
  }
}

Future<void> clearPlatformTemporaryDirectoryForTerminalAccountClosure() async {
  final directory = await getTemporaryDirectory();
  if (!await directory.exists()) {
    return;
  }
  await for (final entry in directory.list(followLinks: false)) {
    await entry.delete(recursive: true);
  }
  final residual = await directory.list(followLinks: false).take(1).toList();
  if (residual.isNotEmpty) {
    throw StateError('temporary directory cleanup verification failed');
  }
}
