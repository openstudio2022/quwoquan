import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const String rehearsalAssistantScriptVersion = 'rehearsal.xiaoqu.v1';

Stream<Object?> scriptedAssistantEventStream(RehearsalInvocation i) async* {
  i.requireActor();
  final runId = i.path('runId');
  final sessionId = i.path('sessionId');
  final fence = i.store.captureFence(i.actorId);
  Map<String, Object?> check() {
    fence();
    throwIfCloudOperationInterrupted(
      cancellation: i.context.cancellation,
      deadlineAt: i.context.deadlineAt,
      now: i.now,
    );
    final run = i.store.assistantRuns[runId];
    final session = i.store.assistantSessions[sessionId];
    if (run == null ||
        run['sessionId'] != sessionId ||
        run['userId'] != i.actorId ||
        session?['userId'] != i.actorId) {
      rehearsalUnauthorized();
    }
    return run;
  }

  var seq = 0;
  for (final type in ['run_started', 'answer_delta', 'completed']) {
    final run = check();
    if (run['cancelled'] == true) {
      yield _event(i, sessionId, runId, ++seq, 'cancelled');
      return;
    }
    if (run['status'] == 'completed') return;
    if (type == 'completed') {
      final completed = await i.store.commit(
        () {
          final current = check();
          if (current['cancelled'] == true) return false;
          current['status'] = 'completed';
          return true;
        },
        beforeCommit: () {
          check();
        },
      );
      if (!completed) {
        yield _event(i, sessionId, runId, ++seq, 'cancelled');
        return;
      }
    }
    check();
    yield _event(i, sessionId, runId, ++seq, type);
  }
}

Map<String, Object?> _event(
  RehearsalInvocation i,
  String sessionId,
  String runId,
  int seq,
  String type,
) => {
  'schema': 'assistant.stream.event.v1',
  'eventId': '$runId-$seq',
  'sessionId': sessionId,
  'runId': runId,
  'seq': seq,
  'eventType': type,
  'traceId': 'rehearsal',
  'createdAt': i.now().toUtc().toIso8601String(),
  'payload': {
    'text': '$rehearsalAssistantMarker 本地脚本回答，不是真实模型输出。',
    'source': rehearsalAssistantScriptVersion,
  },
};
