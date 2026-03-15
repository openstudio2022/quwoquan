enum AssistantSyncMode {
  localMock,
  cloudStub,
}

class AssistantSyncModeParser {
  const AssistantSyncModeParser._();

  static AssistantSyncMode parse(String raw) {
    final normalized = raw.trim().toLowerCase();
    if (normalized == 'cloud_stub') return AssistantSyncMode.cloudStub;
    return AssistantSyncMode.localMock;
  }

  static String toConfigValue(AssistantSyncMode mode) {
    switch (mode) {
      case AssistantSyncMode.localMock:
        return 'local_mock';
      case AssistantSyncMode.cloudStub:
        return 'cloud_stub';
    }
  }
}
