import 'dart:io';

import 'package:path_provider/path_provider.dart';

Future<String> writePlatformTemporaryFileBytes({
  required String fileName,
  required List<int> bytes,
}) async {
  final normalized = fileName.trim();
  if (normalized.isEmpty ||
      normalized.contains('/') ||
      normalized.contains('\\')) {
    throw ArgumentError.value(fileName, 'fileName', 'must be a basename');
  }
  final directory = await getTemporaryDirectory();
  final file = File('${directory.path}/$normalized');
  await file.writeAsBytes(bytes, flush: true);
  return file.path;
}
