import 'dart:io';

import 'package:quwoquan_app/runtime/platform/local_file_stat.dart';

Future<LocalFileStat> readPlatformLocalFileStat(String path) async {
  final file = File(path);
  if (!await file.exists()) {
    return const LocalFileStat(exists: false, length: 0);
  }
  return LocalFileStat(exists: true, length: await file.length());
}
