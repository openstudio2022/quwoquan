// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/assistant_api_contract_harness.dart';

void main() {
  AssistantApiContractHarness? harness;

  setUpAll(() async {
    harness = await AssistantApiContractHarness.create('assistant-turn-view');
  });
  tearDownAll(() => harness?.close());

  test('production Remote 完成真实 Run 后回读同一 terminal turn', () async {
    final api = harness!;
    final nonce = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
    final prompt = '请只用一句话回答：一加一等于几？ request=$nonce';
    final session = await api.sessionRun.createAssistantSession(
      summary: 'turn-view-$nonce',
      clientRequestId: 'turn-session-$nonce',
    );
    final started = await api.sessionRun.startAssistantRun(
      sessionId: session.sessionId,
      text: prompt,
      clientRequestId: 'turn-run-$nonce',
    );
    expect(started.runId, isNotEmpty);
    expect(started.sessionId, session.sessionId);

    final terminal = await _pollTerminalRun(api, started.runId);
    expect(terminal.status, 'completed');
    expect(terminal.terminalSnapshot, isNotNull);
    expect(terminal.terminalSnapshot!.answerText.trim(), isNotEmpty);
    expect(terminal.completedAt, isNotEmpty);

    final projected = await _pollTurn(
      api,
      sessionId: session.sessionId,
      prompt: prompt,
    );
    expect(projected.sessionId, session.sessionId);
    expect(projected.status, terminal.status);
    expect(projected.inputText, prompt);
    expect(projected.terminalSnapshot, isNotNull);
    expect(
      projected.terminalSnapshot!.answerText.trim(),
      terminal.terminalSnapshot!.answerText.trim(),
    );
    expect(projected.completedAt, isNotNull);

    final events = await api.telemetry.waitForEvents(minimumCount: 5);
    expect(
      events.map((event) => event.canonicalOperationId),
      containsAll(<String>[
        AppCloudOperationIds.assistantAssistantSessionCreateAssistantSession,
        AppCloudOperationIds.assistantAssistantRunStartAssistantRun,
        AppCloudOperationIds.assistantAssistantRunGetAssistantRun,
        AppCloudOperationIds.assistantAssistantTurnViewListSessionTurns,
      ]),
    );
  });
}

Future<AssistantRunEnvelopeWire> _pollTerminalRun(
  AssistantApiContractHarness harness,
  String runId,
) async {
  final deadline = DateTime.now().add(const Duration(minutes: 3));
  while (true) {
    final run = await harness.sessionRun.getAssistantRun(runId: runId);
    if (run.terminalSnapshot != null) {
      return run;
    }
    if (DateTime.now().isAfter(deadline)) {
      throw StateError('Timed out waiting for terminal AssistantRun $runId');
    }
    await Future<void>.delayed(const Duration(milliseconds: 500));
  }
}

Future<AssistantTurnSummaryView> _pollTurn(
  AssistantApiContractHarness harness, {
  required String sessionId,
  required String prompt,
}) async {
  final deadline = DateTime.now().add(const Duration(seconds: 30));
  while (true) {
    final page = await harness.sessionRun.listSessionTurns(
      sessionId: sessionId,
      limit: 20,
    );
    for (final turn in page.items) {
      if (turn.inputText == prompt && turn.terminalSnapshot != null) {
        return turn;
      }
    }
    if (DateTime.now().isAfter(deadline)) {
      throw StateError('Timed out waiting for AssistantTurn projection');
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
}
