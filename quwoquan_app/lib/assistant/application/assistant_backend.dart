enum AssistantBackend { local, remote }

extension AssistantBackendWire on AssistantBackend {
  String get wireName {
    switch (this) {
      case AssistantBackend.local:
        return 'local';
      case AssistantBackend.remote:
        return 'remote';
    }
  }

  String get sessionPrefix => '${wireName}_assistant_';
}

AssistantBackend parseAssistantBackend(String raw) {
  switch (raw.trim().toLowerCase()) {
    case 'local':
      return AssistantBackend.local;
    case 'remote':
      return AssistantBackend.remote;
    default:
      return AssistantBackend.remote;
  }
}

AssistantBackend assistantBackendForSessionId(String sessionId) {
  final normalized = sessionId.trim();
  if (normalized.startsWith(AssistantBackend.local.sessionPrefix)) {
    return AssistantBackend.local;
  }
  if (normalized.startsWith(AssistantBackend.remote.sessionPrefix)) {
    return AssistantBackend.remote;
  }
  return AssistantBackend.remote;
}

String newAssistantSessionId(AssistantBackend backend) {
  return '${backend.sessionPrefix}${DateTime.now().millisecondsSinceEpoch}';
}

bool isAssistantSessionForBackend(String sessionId, AssistantBackend backend) {
  return sessionId.trim().startsWith(backend.sessionPrefix);
}
