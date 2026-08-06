import 'package:quwoquan_app/runtime/platform/local_file_stat.dart';

Future<LocalFileStat> readPlatformLocalFileStat(String path) async =>
    const LocalFileStat(exists: false, length: 0);
