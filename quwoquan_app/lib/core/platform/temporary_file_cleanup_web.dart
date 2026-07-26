Future<void> deletePlatformTemporaryFile(String path) async {
  if (path.trim().isNotEmpty) {
    throw UnsupportedError('temporary file cleanup is unavailable on web');
  }
}

Future<void> clearPlatformTemporaryDirectoryForTerminalAccountClosure() async {}
