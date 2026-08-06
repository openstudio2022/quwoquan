/// Pure application boundary for checking a local video before editing.
abstract interface class LocalVideoPlayability {
  Future<void> waitUntilPlayable(String path);
}

typedef LocalVideoFileReadyProbe = Future<bool> Function(String path);
