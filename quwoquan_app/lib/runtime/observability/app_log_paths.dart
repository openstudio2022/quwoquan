import 'dart:io';

import 'package:path_provider/path_provider.dart';

class AppLogPaths {
  AppLogPaths({this.rootDirName = 'quwoquan_logs'});

  final String rootDirName;

  Future<Directory> rootDirectory() async {
    try {
      final support = await getApplicationSupportDirectory();
      return Directory('${support.path}/$rootDirName');
    } catch (_) {
      return Directory('${Directory.systemTemp.path}/$rootDirName');
    }
  }

  Future<Directory> dayDirectory(DateTime time) async {
    final root = await rootDirectory();
    final day = _dayStamp(time);
    return Directory('${root.path}/$day');
  }

  String _dayStamp(DateTime time) {
    final y = time.year.toString().padLeft(4, '0');
    final m = time.month.toString().padLeft(2, '0');
    final d = time.day.toString().padLeft(2, '0');
    return '$y-$m-$d';
  }
}
