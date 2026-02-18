enum AssistentSyncMode {
  localMock,
  cloudStub,
}

class AssistentSyncModeParser {
  const AssistentSyncModeParser._();

  static AssistentSyncMode parse(String raw) {
    final normalized = raw.trim().toLowerCase();
    if (normalized == 'cloud_stub') return AssistentSyncMode.cloudStub;
    return AssistentSyncMode.localMock;
  }

  static String toConfigValue(AssistentSyncMode mode) {
    switch (mode) {
      case AssistentSyncMode.localMock:
        return 'local_mock';
      case AssistentSyncMode.cloudStub:
        return 'cloud_stub';
    }
  }
}

