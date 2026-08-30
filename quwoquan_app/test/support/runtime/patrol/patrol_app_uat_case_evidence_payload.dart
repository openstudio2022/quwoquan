library;

import 'release_uat_sample_plan.dart';

final RegExp _typedReasonCode = RegExp(r'^APP\.UAT\.[A-Z0-9_]+\.[A-Z0-9_]+$');

Map<String, String> buildPatrolAppUatPageEvidenceReady({
  required ReleaseUatSlot slot,
  required String route,
  required String terminalKey,
}) => <String, String>{
  'schema': 'quwoquan_app.app_uat_page_evidence_ready.v1',
  'sampleId': slot.sample.sampleId,
  'entrySurface': slot.entrySurface,
  'carrier': slot.sample.carrier,
  'objectId': slot.sample.objectId,
  'runtimeObjectId': slot.sample.runtimeObjectId,
  'specRef': slot.specRef,
  'runnerIdentity': slot.runnerIdentity,
  'route': route,
  'terminalKey': terminalKey,
  'captureId': slot.captureId,
};

Map<String, Object> buildPassedPatrolAppUatCaseEvidence({
  required ReleaseUatSlot slot,
  required String targetKind,
  required String startedAt,
  required String completedAt,
}) => <String, Object>{
  'schema': 'quwoquan_app.app_uat_case_evidence.v1',
  'sampleId': slot.sample.sampleId,
  'entrySurface': slot.entrySurface,
  'carrier': slot.sample.carrier,
  'objectId': slot.sample.objectId,
  'specRef': slot.specRef,
  'runnerIdentity': slot.runnerIdentity,
  'status': 'passed',
  'startedAt': startedAt,
  'completedAt': completedAt,
  'target': <String, String>{
    'kind': targetKind,
    'id': slot.sample.runtimeObjectId,
  },
  'pageEvidence': <String, String>{
    'status': 'host_captured',
    'captureId': slot.captureId,
  },
};

Map<String, Object> buildBlockedPatrolAppUatCaseEvidence({
  required ReleaseUatSlot slot,
  required String reasonCode,
  required String timestamp,
}) {
  if (!_typedReasonCode.hasMatch(reasonCode)) {
    throw ArgumentError.value(reasonCode, 'reasonCode');
  }
  return <String, Object>{
    'schema': 'quwoquan_app.app_uat_case_evidence.v1',
    'sampleId': slot.sample.sampleId,
    'entrySurface': slot.entrySurface,
    'carrier': slot.sample.carrier,
    'objectId': slot.sample.objectId,
    'specRef': slot.specRef,
    'runnerIdentity': slot.runnerIdentity,
    'status': 'blocked',
    'reasonCode': reasonCode,
    'startedAt': timestamp,
    'completedAt': timestamp,
    'target': <String, String>{
      'kind': slot.sample.carrier == 'homepage' ? 'object' : 'page',
      'id': slot.sample.runtimeObjectId,
    },
    'pageEvidence': const <String, String>{'status': 'missing'},
  };
}
