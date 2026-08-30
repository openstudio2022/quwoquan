library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';

import 'patrol_app_uat_case_evidence_payload.dart';
import 'release_uat_sample_plan.dart';

const String appUatPageEvidenceReadyPrefix = 'QWQ_APP_UAT_PAGE_EVIDENCE_READY ';
const String appUatCaseEvidencePrefix = 'QWQ_APP_UAT_CASE_EVIDENCE ';
const Duration _hostCaptureWindow = Duration(seconds: 2);

Future<void> emitPassedPatrolAppUatCaseEvidence(
  PatrolIntegrationTester $, {
  required ReleaseUatSlot slot,
  required String route,
  required String terminalKey,
  required Finder terminalFinder,
  required String targetKind,
}) async {
  expect(
    terminalFinder.evaluate(),
    isNotEmpty,
    reason: '${slot.captureId} terminal must be mounted before page capture',
  );
  final startedAt = DateTime.now().toUtc().toIso8601String();
  final pageMarker = buildPatrolAppUatPageEvidenceReady(
    slot: slot,
    route: route,
    terminalKey: terminalKey,
  );
  // ignore: avoid_print
  print('$appUatPageEvidenceReadyPrefix${jsonEncode(pageMarker)}');
  await $.pump(_hostCaptureWindow);
  expect(
    terminalFinder.evaluate(),
    isNotEmpty,
    reason:
        '${slot.captureId} terminal must remain mounted during host capture',
  );
  // Host 同步消费 ready marker 并在该 capture window 内抓取当前帧；随后
  // case marker 仅声明 captureId。最终 passed receipt 必须由 host resolver 找到该
  // captureId 的独立 exact ref/digest，否则 fail closed，不能凭 suite 状态补证据。
  final completedAt = DateTime.now().toUtc().toIso8601String();
  final marker = buildPassedPatrolAppUatCaseEvidence(
    slot: slot,
    targetKind: targetKind,
    startedAt: startedAt,
    completedAt: completedAt,
  );
  // ignore: avoid_print
  print('$appUatCaseEvidencePrefix${jsonEncode(marker)}');
}

void emitBlockedPatrolAppUatCaseEvidence({
  required ReleaseUatSlot slot,
  required String reasonCode,
}) {
  final timestamp = DateTime.now().toUtc().toIso8601String();
  final marker = buildBlockedPatrolAppUatCaseEvidence(
    slot: slot,
    reasonCode: reasonCode,
    timestamp: timestamp,
  );
  // ignore: avoid_print
  print('$appUatCaseEvidencePrefix${jsonEncode(marker)}');
}
