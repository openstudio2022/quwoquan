import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('planner contracts 通过 generated enums 提供当前 process canonical code', () {
    final plannerWrapper = File(
      'lib/assistant/contracts/planner_contracts.dart',
    ).readAsStringSync();
    final generatedEnums = File(
      'lib/assistant/generated/enums/assistant_runtime_enums.g.dart',
    ).readAsStringSync();

    expect(plannerWrapper, contains('Runtime-only protocol boundary:'));
    expect(
      plannerWrapper,
      contains(
          "export 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';",
      ),
    );
    expect(generatedEnums, contains('enum PlannerActionCode'));
    expect(generatedEnums, contains('case PlannerActionCode.startRetrieval'));
    expect(generatedEnums, contains('case PlannerActionCode.reviewSources'));
    expect(generatedEnums, contains('case PlannerActionCode.recoverRetrieval'));
    expect(generatedEnums, contains('case PlannerActionCode.parallelProbe'));
    expect(generatedEnums, contains('case PlannerActionCode.mergeParallelResult'));
    expect(
      generatedEnums,
      contains('case PlannerActionCode.fallbackWithExistingEvidence'),
    );
    expect(generatedEnums, contains('case PlannerActionCode.setStage'));
    expect(generatedEnums, contains('enum PlannerReasonCode'));
    expect(generatedEnums, contains('case PlannerReasonCode.confirmRealtimeScope'));
    expect(generatedEnums, contains('case PlannerReasonCode.needMoreEvidence'));
    expect(generatedEnums, contains('case PlannerReasonCode.sourceUnstable'));
    expect(generatedEnums, contains('case PlannerReasonCode.reduceWaitTime'));
    expect(generatedEnums, contains('case PlannerReasonCode.parallelBranchFailed'));
    expect(generatedEnums, contains('case PlannerReasonCode.assessmentUpdate'));
  });

  test('process protocol 明确标注 runtime-only boundary', () {
    final content = File(
      'lib/assistant/contracts/process_protocol.dart',
    ).readAsStringSync();

    expect(content, contains('Runtime-only protocol boundary:'));
    expect(content, contains('metadata-owned contract'));
  });
}
