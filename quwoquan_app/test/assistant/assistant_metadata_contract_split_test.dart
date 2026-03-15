import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('assistant 开放结构已拆为对象级 metadata 子合同', () {
    final assistantTurn = _readMetadata('assistant/assistant_turn/schema.yaml');
    final intentGraph = _readMetadata('assistant/intent_graph/schema.yaml');
    final runArtifacts = _readMetadata('assistant/run_artifacts/schema.yaml');

    expect(assistantTurn, contains('subcontracts:'));
    expect(assistantTurn, contains('decision:'));
    expect(assistantTurn, contains('result:'));
    expect(assistantTurn, contains('ask_user:'));
    expect(assistantTurn, contains('tool_call:'));
    expect(assistantTurn, contains('evidence_item:'));
    expect(assistantTurn, contains('reasoning_basis_item:'));
    expect(assistantTurn, contains('diagnostics:'));

    expect(intentGraph, contains('query_normalization:'));
    expect(intentGraph, contains('queryTasks'));

    expect(runArtifacts, contains('slot_value:'));
    expect(runArtifacts, contains('slot_state:'));
    expect(runArtifacts, contains('policy_bundle:'));
  });
}

String _readMetadata(String relativePath) {
  final file = File('../quwoquan_service/contracts/metadata/$relativePath');
  expect(file.existsSync(), isTrue, reason: 'metadata 文件不存在: $relativePath');
  return file.readAsStringSync();
}
