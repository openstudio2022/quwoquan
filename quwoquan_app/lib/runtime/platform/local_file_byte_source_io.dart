import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/core/platform/local_file_byte_source.dart';

/// Native implementation that hashes once, then reopens the file for upload.
Future<LocalFileByteSource> preparePlatformLocalFileByteSource(
  String localPath,
) async {
  final path = localPath.trim();
  if (path.isEmpty) {
    throw StateError('media source path is empty');
  }
  final file = File(path);
  if (!await file.exists()) {
    throw StateError('media source does not exist');
  }
  final fileSize = await file.length();
  if (fileSize <= 0) {
    throw StateError('media source is empty');
  }
  final digest = await sha256.bind(file.openRead()).first;
  return LocalFileByteSource(
    fileSize: fileSize,
    sha256Digest: digest.toString(),
    openRead: file.openRead,
  );
}
