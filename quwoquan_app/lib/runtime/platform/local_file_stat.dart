import 'local_file_stat_stub.dart'
    if (dart.library.io) 'local_file_stat_io.dart';

/// Minimal local-file metadata exposed across the platform boundary.
final class LocalFileStat {
  const LocalFileStat({required this.exists, required this.length});

  final bool exists;
  final int length;
}

Future<LocalFileStat> readLocalFileStat(String path) =>
    readPlatformLocalFileStat(path);
