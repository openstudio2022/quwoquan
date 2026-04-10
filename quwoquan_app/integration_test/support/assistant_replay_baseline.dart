import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/application/transcript/assistant_replay_record_factory.dart';
import 'package:quwoquan_app/assistant/memory/storage/assistant_storage_path.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_paths.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/transcript/replay/assistant_replay_record.dart';

const String assistantReplayM0BaselinePackVersion = 'assistant_replay_m0_v1';

class AssistantReplayBaselineTurn {
  const AssistantReplayBaselineTurn({
    required this.turnId,
    required this.query,
    this.runId = '',
    this.traceId = '',
    this.runLogPath = '',
    this.expectedOutcomeClass = '',
    this.outcomeClass = '',
    this.failureClass = '',
    this.gatePassed = false,
    this.finalAnswerReady = false,
    this.issues = const <String>[],
    this.queryDesignLines = const <String>[],
    this.report = const <String, dynamic>{},
    this.canonicalState = const <String, dynamic>{},
    this.runLogMeta = const <String, dynamic>{},
    this.replayRecord = const <String, dynamic>{},
  });

  final String turnId;
  final String query;
  final String runId;
  final String traceId;
  final String runLogPath;
  final String expectedOutcomeClass;
  final String outcomeClass;
  final String failureClass;
  final bool gatePassed;
  final bool finalAnswerReady;
  final List<String> issues;
  final List<String> queryDesignLines;
  final Map<String, dynamic> report;
  final Map<String, dynamic> canonicalState;
  final Map<String, dynamic> runLogMeta;
  final Map<String, dynamic> replayRecord;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'turnId': turnId,
      'query': query,
      'runId': runId,
      'traceId': traceId,
      'runLogPath': runLogPath,
      'expectedOutcomeClass': expectedOutcomeClass,
      'outcomeClass': outcomeClass,
      'failureClass': failureClass,
      'gatePassed': gatePassed,
      'finalAnswerReady': finalAnswerReady,
      'issues': issues,
      'queryDesignLines': queryDesignLines,
      'report': report,
      'canonicalState': canonicalState,
      'runLogMeta': runLogMeta,
      'replayRecord': replayRecord,
    };
  }
}

class AssistantReplayBaselineAttempt {
  const AssistantReplayBaselineAttempt({
    required this.attemptIndex,
    this.outcomeClass = '',
    this.failureClass = '',
    this.gatePassed = false,
    this.issues = const <String>[],
    this.turns = const <AssistantReplayBaselineTurn>[],
    this.details = const <String, dynamic>{},
  });

  final int attemptIndex;
  final String outcomeClass;
  final String failureClass;
  final bool gatePassed;
  final List<String> issues;
  final List<AssistantReplayBaselineTurn> turns;
  final Map<String, dynamic> details;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'attemptIndex': attemptIndex,
      'outcomeClass': outcomeClass,
      'failureClass': failureClass,
      'gatePassed': gatePassed,
      'issues': issues,
      'turns': turns.map((item) => item.toJson()).toList(growable: false),
      'details': details,
    };
  }
}

class AssistantReplayBaselineStability {
  const AssistantReplayBaselineStability({
    this.stable = false,
    this.repeatCount = 0,
    this.comparedFields = const <String>[],
    this.fieldDiffs = const <Map<String, dynamic>>[],
  });

  final bool stable;
  final int repeatCount;
  final List<String> comparedFields;
  final List<Map<String, dynamic>> fieldDiffs;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'stable': stable,
      'repeatCount': repeatCount,
      'comparedFields': comparedFields,
      'fieldDiffs': fieldDiffs,
    };
  }
}

class AssistantReplayM1EntryAssessment {
  const AssistantReplayM1EntryAssessment({
    this.eligible = false,
    this.satisfiedChecks = const <String>[],
    this.blockingReasons = const <String>[],
  });

  final bool eligible;
  final List<String> satisfiedChecks;
  final List<String> blockingReasons;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'eligible': eligible,
      'satisfiedChecks': satisfiedChecks,
      'blockingReasons': blockingReasons,
    };
  }
}

class AssistantReplayBaselinePack {
  const AssistantReplayBaselinePack({
    required this.caseId,
    required this.turnShape,
    required this.expectedScope,
    required this.expectedTemporalAnchor,
    required this.expectedOutcomeClass,
    required this.repeatCount,
    required this.knownFailureClasses,
    required this.attempts,
    required this.stability,
    required this.m1Entry,
    this.schemaVersion = assistantReplayM0BaselinePackVersion,
    this.generatedAt = '',
    this.softEvidence = const <String, dynamic>{},
  });

  final String schemaVersion;
  final String caseId;
  final String turnShape;
  final String expectedScope;
  final String expectedTemporalAnchor;
  final String expectedOutcomeClass;
  final int repeatCount;
  final List<String> knownFailureClasses;
  final List<AssistantReplayBaselineAttempt> attempts;
  final AssistantReplayBaselineStability stability;
  final AssistantReplayM1EntryAssessment m1Entry;
  final String generatedAt;
  final Map<String, dynamic> softEvidence;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'schemaVersion': schemaVersion,
      'caseId': caseId,
      'turnShape': turnShape,
      'expectedScope': expectedScope,
      'expectedTemporalAnchor': expectedTemporalAnchor,
      'expectedOutcomeClass': expectedOutcomeClass,
      'repeatCount': repeatCount,
      'knownFailureClasses': knownFailureClasses,
      'attempts': attempts.map((item) => item.toJson()).toList(growable: false),
      'stability': stability.toJson(),
      'm1Entry': m1Entry.toJson(),
      'generatedAt': generatedAt,
      'softEvidence': softEvidence,
    };
  }
}

Future<String> writeAssistantReplayBaselinePack(
  AssistantReplayBaselinePack pack,
) async {
  return _writeAssistantReplayArtifact(
    relativePath: 'replay/m0/${pack.caseId}.json',
    payload: pack.toJson(),
  );
}

Future<String> writeAssistantReplayBaselineIndex({
  required String fileName,
  required Map<String, dynamic> payload,
}) async {
  return _writeAssistantReplayArtifact(
    relativePath: 'replay/m0/$fileName',
    payload: payload,
  );
}

Future<String?> resolveAssistantRunLogPath(String runId) async {
  final normalizedRunId = runId.trim();
  if (normalizedRunId.isEmpty) {
    return null;
  }
  final root = await AppLogPaths().rootDirectory();
  if (!await root.exists()) {
    return null;
  }
  final expectedFileName = 'run_${_sanitizeRunId(normalizedRunId)}.json';
  await for (final entity in root.list(recursive: true, followLinks: false)) {
    if (entity is! File) {
      continue;
    }
    if (entity.path.endsWith('/$expectedFileName')) {
      return entity.path;
    }
  }
  return null;
}

Future<Map<String, dynamic>> loadAssistantRunLog(String? path) async {
  final normalizedPath = (path ?? '').trim();
  if (normalizedPath.isEmpty) {
    return const <String, dynamic>{};
  }
  final file = File(normalizedPath);
  if (!await file.exists()) {
    return const <String, dynamic>{};
  }
  try {
    final decoded = jsonDecode(await file.readAsString());
    if (decoded is Map) {
      return decoded.cast<String, dynamic>();
    }
  } on FileSystemException {
    return const <String, dynamic>{};
  } on FormatException {
    return const <String, dynamic>{};
  }
  return const <String, dynamic>{};
}

Future<AssistantReplayRecord?> buildAssistantReplayRecordFromRunLog({
  required String messageId,
  required String query,
  required String answerText,
  required String displayPlainText,
  required String runLogPath,
}) async {
  final payload = await loadAssistantRunLog(runLogPath);
  final responseJson = (payload['response'] as Map?)?.cast<String, dynamic>();
  if (responseJson == null || responseJson.isEmpty) {
    return null;
  }
  final response = AssistantRunResponse.fromJson(responseJson);
  final runArtifacts = response.runArtifacts;
  return AssistantReplayRecordFactory.build(
    messageId: messageId,
    query: query,
    response: response,
    replayPayload: buildAssistantReplayPayloadFromTraces(response.traces),
    runArtifactsMap:
        runArtifacts?.toJson() ??
        (response.structuredResponse['runArtifacts'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{},
    answerText: answerText,
    displayPlainText: displayPlainText,
  );
}

Future<String> _writeAssistantReplayArtifact({
  required String relativePath,
  required Map<String, dynamic> payload,
}) async {
  final path = await getPersonalAssistantStoragePath(relativePath);
  final file = File(path);
  await file.parent.create(recursive: true);
  await file.writeAsString(const JsonEncoder.withIndent('  ').convert(payload));
  return path;
}

String _sanitizeRunId(String runId) {
  return runId.replaceAll(RegExp(r'[^a-zA-Z0-9_\-]'), '_');
}
