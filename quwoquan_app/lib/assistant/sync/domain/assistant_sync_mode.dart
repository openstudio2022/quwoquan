enum AssistantSyncMode { localMock, remote }

class AssistantSyncModeParser {
  const AssistantSyncModeParser._();

  static AssistantSyncMode parse(String raw) {
    final normalized = raw.trim().toLowerCase();
    if (normalized == 'remote' || normalized == 'cloud_stub') {
      return AssistantSyncMode.remote;
    }
    return AssistantSyncMode.localMock;
  }

  static String toConfigValue(AssistantSyncMode mode) {
    switch (mode) {
      case AssistantSyncMode.localMock:
        return 'local_mock';
      case AssistantSyncMode.remote:
        return 'remote';
    }
  }
}
