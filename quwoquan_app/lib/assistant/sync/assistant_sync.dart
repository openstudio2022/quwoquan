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

enum AssistantSyncResource {
  policy,
  interactionEvents,
  scorecards,
  memoryRecords,
}

class AssistantSyncResult {
  const AssistantSyncResult({
    required this.success,
    required this.mode,
    required this.resource,
    required this.message,
    this.payload = const <String, dynamic>{},
  });

  final bool success;
  final AssistantSyncMode mode;
  final AssistantSyncResource resource;
  final String message;
  final Map<String, dynamic> payload;
}

abstract class AssistantSyncAdapter {
  Future<AssistantSyncResult> pullPolicy({
    required String policyVersionHint,
  });

  Future<AssistantSyncResult> pushInteractionEvents({
    required List<Map<String, dynamic>> events,
  });

  Future<AssistantSyncResult> pushScorecards({
    required List<Map<String, dynamic>> scorecards,
  });

  Future<AssistantSyncResult> syncMemoryRecords({
    required List<Map<String, dynamic>> memoryRecords,
  });
}

class LocalMockSyncAdapter implements AssistantSyncAdapter {
  LocalMockSyncAdapter({
    this.policySnapshot = const <String, dynamic>{
      'version': 'local_mock_v1',
      'values': <String, dynamic>{},
    },
  });

  Map<String, dynamic> policySnapshot;
  final List<Map<String, dynamic>> interactionEvents = <Map<String, dynamic>>[];
  final List<Map<String, dynamic>> scorecards = <Map<String, dynamic>>[];
  final List<Map<String, dynamic>> memoryRecords = <Map<String, dynamic>>[];

  @override
  Future<AssistantSyncResult> pullPolicy({
    required String policyVersionHint,
  }) async {
    return AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.localMock,
      resource: AssistantSyncResource.policy,
      message: 'Local mock policy loaded.',
      payload: <String, dynamic>{
        'policyVersionHint': policyVersionHint,
        'snapshot': policySnapshot,
      },
    );
  }

  @override
  Future<AssistantSyncResult> pushInteractionEvents({
    required List<Map<String, dynamic>> events,
  }) async {
    interactionEvents.addAll(events);
    return AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.localMock,
      resource: AssistantSyncResource.interactionEvents,
      message: 'Local mock interaction events accepted.',
      payload: <String, dynamic>{
        'count': events.length,
        'total': interactionEvents.length,
      },
    );
  }

  @override
  Future<AssistantSyncResult> pushScorecards({
    required List<Map<String, dynamic>> scorecards,
  }) async {
    this.scorecards.addAll(scorecards);
    return AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.localMock,
      resource: AssistantSyncResource.scorecards,
      message: 'Local mock scorecards accepted.',
      payload: <String, dynamic>{
        'count': scorecards.length,
        'total': this.scorecards.length,
      },
    );
  }

  @override
  Future<AssistantSyncResult> syncMemoryRecords({
    required List<Map<String, dynamic>> memoryRecords,
  }) async {
    this.memoryRecords.addAll(memoryRecords);
    return AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.localMock,
      resource: AssistantSyncResource.memoryRecords,
      message: 'Local mock memory records accepted.',
      payload: <String, dynamic>{
        'count': memoryRecords.length,
        'total': this.memoryRecords.length,
      },
    );
  }
}

class CloudStubSyncAdapter implements AssistantSyncAdapter {
  const CloudStubSyncAdapter();

  @override
  Future<AssistantSyncResult> pullPolicy({
    required String policyVersionHint,
  }) async {
    return AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.cloudStub,
      resource: AssistantSyncResource.policy,
      message: 'Cloud stub policy placeholder returned.',
      payload: <String, dynamic>{
        'policyVersionHint': policyVersionHint,
        'snapshot': <String, dynamic>{
          'version': 'cloud_stub_v1',
          'values': <String, dynamic>{},
        },
      },
    );
  }

  @override
  Future<AssistantSyncResult> pushInteractionEvents({
    required List<Map<String, dynamic>> events,
  }) async {
    return AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.cloudStub,
      resource: AssistantSyncResource.interactionEvents,
      message: 'Cloud stub accepted interaction events placeholder.',
      payload: <String, dynamic>{'count': events.length},
    );
  }

  @override
  Future<AssistantSyncResult> pushScorecards({
    required List<Map<String, dynamic>> scorecards,
  }) async {
    return AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.cloudStub,
      resource: AssistantSyncResource.scorecards,
      message: 'Cloud stub accepted scorecards placeholder.',
      payload: <String, dynamic>{'count': scorecards.length},
    );
  }

  @override
  Future<AssistantSyncResult> syncMemoryRecords({
    required List<Map<String, dynamic>> memoryRecords,
  }) async {
    return AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.cloudStub,
      resource: AssistantSyncResource.memoryRecords,
      message: 'Cloud stub accepted memory records placeholder.',
      payload: <String, dynamic>{'count': memoryRecords.length},
    );
  }
}

class AssistantSyncGateway {
  AssistantSyncGateway(this._adapter, this._mode);

  final AssistantSyncAdapter _adapter;
  final AssistantSyncMode _mode;

  AssistantSyncMode get mode => _mode;

  Future<AssistantSyncResult> pullPolicy({
    required String policyVersionHint,
  }) {
    return _adapter.pullPolicy(policyVersionHint: policyVersionHint);
  }

  Future<AssistantSyncResult> pushInteractionEvents({
    required List<Map<String, dynamic>> events,
  }) {
    return _adapter.pushInteractionEvents(events: events);
  }

  Future<AssistantSyncResult> pushScorecards({
    required List<Map<String, dynamic>> scorecards,
  }) {
    return _adapter.pushScorecards(scorecards: scorecards);
  }

  Future<AssistantSyncResult> syncMemoryRecords({
    required List<Map<String, dynamic>> memoryRecords,
  }) {
    return _adapter.syncMemoryRecords(memoryRecords: memoryRecords);
  }
}
