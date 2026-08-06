import 'temporary_file_writer_stub.dart'
    if (dart.library.io) 'temporary_file_writer_io.dart';

/// Persists bytes below the App temporary directory and returns the full path.
///
/// [fileName] is a basename, not a path. Platform implementations must reject
/// separators so callers cannot escape the App-owned temporary directory.
Future<String> writeAppTemporaryFileBytes({
  required String fileName,
  required List<int> bytes,
}) => writePlatformTemporaryFileBytes(fileName: fileName, bytes: bytes);
