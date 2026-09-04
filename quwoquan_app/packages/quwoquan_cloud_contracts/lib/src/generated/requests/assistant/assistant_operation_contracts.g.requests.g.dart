// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 692d9cee9361c0808d878fedc1fd14cffbf1309a5abe57519717852663f44024

part of '../../../assistant/assistant_operation_contracts.g.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

List<String> _normalizeGeneratedTextList(
  Iterable<String> values, {
  required bool deduplicate,
}) {
  final result = <String>[];
  final seen = <String>{};
  for (final value in values) {
    final normalized = value.trim();
    if (normalized.isEmpty) continue;
    if (deduplicate && !seen.add(normalized)) continue;
    result.add(normalized);
  }
  return List<String>.unmodifiable(result);
}

Map<String, Object?> _generatedRequestObject(Object? value, String path) {
  if (value is Map<String, Object?>) return value;
  if (value is Map) return Map<String, Object?>.from(value);
  throw FormatException('$path must be an object');
}

void _generatedRequestRejectUnknownFields(
  Map<String, Object?> map,
  Set<String> allowed,
  String path,
) {
  for (final key in map.keys) {
    if (!allowed.contains(key)) {
      throw FormatException('$path contains unknown field $key');
    }
  }
}

String _generatedRequestString(Object? value, String path) {
  if (value is String) return value;
  throw FormatException('$path must be a string');
}

int _generatedRequestInt(Object? value, String path) {
  if (value is int) return value;
  throw FormatException('$path must be an integer');
}

double _generatedRequestDouble(Object? value, String path) {
  if (value is num) return value.toDouble();
  throw FormatException('$path must be a number');
}

bool _generatedRequestBool(Object? value, String path) {
  if (value is bool) return value;
  throw FormatException('$path must be a boolean');
}

DateTime _generatedRequestTimestamp(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a timestamp');
  final parsed = DateTime.tryParse(value);
  if (parsed == null) throw FormatException('$path must be a timestamp');
  return parsed.toUtc();
}

List<Object?> _generatedRequestList(Object? value, String path) {
  if (value is List) return List<Object?>.from(value);
  throw FormatException('$path must be a list');
}

final class AssistantAnswerRunIntent {
  const AssistantAnswerRunIntent({required String text}) : text = text;

  final String text;

  factory AssistantAnswerRunIntent.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantAnswerRunIntent",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"text"}, path);
    return AssistantAnswerRunIntent(
      text: _generatedRequestString(map["text"], '$path.text'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"text": this.text};
}

final class AssistantApproveToolUseRequest {
  const AssistantApproveToolUseRequest({
    required String runId,
    required String toolInvocationId,
    required String decision,
    required String approvalPermit,
    String? installationId,
    String? deviceId,
  }) : runId = runId,
       toolInvocationId = toolInvocationId,
       decision = decision,
       approvalPermit = approvalPermit,
       installationId = installationId,
       deviceId = deviceId;

  final String runId;
  final String toolInvocationId;
  final String decision;
  final String approvalPermit;
  final String? installationId;
  final String? deviceId;

  factory AssistantApproveToolUseRequest.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantApproveToolUseRequest",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "runId",
      "toolInvocationId",
      "decision",
      "approvalPermit",
      "installationId",
      "deviceId",
    }, path);
    return AssistantApproveToolUseRequest(
      runId: _generatedRequestString(map["runId"], '$path.runId'),
      toolInvocationId: _generatedRequestString(
        map["toolInvocationId"],
        '$path.toolInvocationId',
      ),
      decision: _generatedRequestString(map["decision"], '$path.decision'),
      approvalPermit: _generatedRequestString(
        map["approvalPermit"],
        '$path.approvalPermit',
      ),
      installationId: map["installationId"] == null
          ? null
          : _generatedRequestString(
              map["installationId"],
              '$path.installationId',
            ),
      deviceId: map["deviceId"] == null
          ? null
          : _generatedRequestString(map["deviceId"], '$path.deviceId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "runId": this.runId,
    "toolInvocationId": this.toolInvocationId,
    "decision": this.decision,
    "approvalPermit": this.approvalPermit,
    if (this.installationId != null) "installationId": this.installationId!,
    if (this.deviceId != null) "deviceId": this.deviceId!,
  };
}

final class AssistantConsentMatrix {
  const AssistantConsentMatrix({required bool canReadCurrentPage})
    : canReadCurrentPage = canReadCurrentPage;

  final bool canReadCurrentPage;

  factory AssistantConsentMatrix.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantConsentMatrix",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "canReadCurrentPage",
    }, path);
    return AssistantConsentMatrix(
      canReadCurrentPage: _generatedRequestBool(
        map["canReadCurrentPage"],
        '$path.canReadCurrentPage',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "canReadCurrentPage": this.canReadCurrentPage,
  };
}

final class AssistantContextSnapshot {
  AssistantContextSnapshot({
    DateTime? capturedAt,
    AssistantPageContextType? pageType,
    List<AssistantObjectGroundingView>? pageObjects,
    List<AssistantUserActionGroundingView>? userActions,
    List<AssistantIntersectionEvidenceRef>? intersectionEvidenceRefs,
    AssistantConsentMatrix? consentMatrix,
  }) : capturedAt = capturedAt,
       pageType = pageType,
       pageObjects = pageObjects == null
           ? null
           : List.unmodifiable(pageObjects),
       userActions = userActions == null
           ? null
           : List.unmodifiable(userActions),
       intersectionEvidenceRefs = intersectionEvidenceRefs == null
           ? null
           : List.unmodifiable(intersectionEvidenceRefs),
       consentMatrix = consentMatrix {}

  final DateTime? capturedAt;
  final AssistantPageContextType? pageType;
  final List<AssistantObjectGroundingView>? pageObjects;
  final List<AssistantUserActionGroundingView>? userActions;
  final List<AssistantIntersectionEvidenceRef>? intersectionEvidenceRefs;
  final AssistantConsentMatrix? consentMatrix;

  factory AssistantContextSnapshot.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantContextSnapshot",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "capturedAt",
      "pageType",
      "pageObjects",
      "userActions",
      "intersectionEvidenceRefs",
      "consentMatrix",
    }, path);
    return AssistantContextSnapshot(
      capturedAt: map["capturedAt"] == null
          ? null
          : _generatedRequestTimestamp(map["capturedAt"], '$path.capturedAt'),
      pageType: map["pageType"] == null
          ? null
          : switch (map["pageType"]) {
              "unknown" => AssistantPageContextType.unknown,
              "home" => AssistantPageContextType.home,
              "discovery" => AssistantPageContextType.discovery,
              "circles" => AssistantPageContextType.circles,
              "article" => AssistantPageContextType.article,
              "profile" => AssistantPageContextType.profile,
              "chat" => AssistantPageContextType.chat,
              "create" => AssistantPageContextType.create,
              "search" => AssistantPageContextType.search,
              _ => throw FormatException(
                '$path.pageType' + ' has an invalid enum value',
              ),
            },
      pageObjects: map["pageObjects"] == null
          ? null
          : List<AssistantObjectGroundingView>.unmodifiable(
              _generatedRequestList(
                map["pageObjects"],
                '$path.pageObjects',
              ).asMap().entries.map(
                (entry) => AssistantObjectGroundingView.fromWire(
                  _generatedRequestObject(
                    entry.value,
                    '$path.pageObjects' + '[${entry.key}]',
                  ),
                  '$path.pageObjects' + '[${entry.key}]',
                ),
              ),
            ),
      userActions: map["userActions"] == null
          ? null
          : List<AssistantUserActionGroundingView>.unmodifiable(
              _generatedRequestList(
                map["userActions"],
                '$path.userActions',
              ).asMap().entries.map(
                (entry) => AssistantUserActionGroundingView.fromWire(
                  _generatedRequestObject(
                    entry.value,
                    '$path.userActions' + '[${entry.key}]',
                  ),
                  '$path.userActions' + '[${entry.key}]',
                ),
              ),
            ),
      intersectionEvidenceRefs: map["intersectionEvidenceRefs"] == null
          ? null
          : List<AssistantIntersectionEvidenceRef>.unmodifiable(
              _generatedRequestList(
                map["intersectionEvidenceRefs"],
                '$path.intersectionEvidenceRefs',
              ).asMap().entries.map(
                (entry) => AssistantIntersectionEvidenceRef.fromWire(
                  _generatedRequestObject(
                    entry.value,
                    '$path.intersectionEvidenceRefs' + '[${entry.key}]',
                  ),
                  '$path.intersectionEvidenceRefs' + '[${entry.key}]',
                ),
              ),
            ),
      consentMatrix: map["consentMatrix"] == null
          ? null
          : AssistantConsentMatrix.fromWire(
              _generatedRequestObject(
                map["consentMatrix"],
                '$path.consentMatrix',
              ),
              '$path.consentMatrix',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.capturedAt != null)
      "capturedAt": this.capturedAt!.toUtc().toIso8601String(),
    if (this.pageType != null) "pageType": this.pageType!.wireName,
    if (this.pageObjects != null)
      "pageObjects": this.pageObjects!
          .map((value) => value.toWire())
          .toList(growable: false),
    if (this.userActions != null)
      "userActions": this.userActions!
          .map((value) => value.toWire())
          .toList(growable: false),
    if (this.intersectionEvidenceRefs != null)
      "intersectionEvidenceRefs": this.intersectionEvidenceRefs!
          .map((value) => value.toWire())
          .toList(growable: false),
    if (this.consentMatrix != null)
      "consentMatrix": this.consentMatrix!.toWire(),
  };
}

final class AssistantCreateSessionRequest {
  const AssistantCreateSessionRequest({
    String? summary,
    required String clientRequestId,
  }) : summary = summary,
       clientRequestId = clientRequestId;

  final String? summary;
  final String clientRequestId;

  factory AssistantCreateSessionRequest.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantCreateSessionRequest",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "summary",
      "clientRequestId",
    }, path);
    return AssistantCreateSessionRequest(
      summary: map["summary"] == null
          ? null
          : _generatedRequestString(map["summary"], '$path.summary'),
      clientRequestId: _generatedRequestString(
        map["clientRequestId"],
        '$path.clientRequestId',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.summary != null) "summary": this.summary!,
    "clientRequestId": this.clientRequestId,
  };
}

final class AssistantCreationRunIntent {
  AssistantCreationRunIntent({
    String? draftTitle,
    String? draftSummary,
    String? bodyDigest,
    List<String>? boundCircleIds,
    String? primaryHomepageId,
  }) : draftTitle = draftTitle,
       draftSummary = draftSummary,
       bodyDigest = bodyDigest,
       boundCircleIds = boundCircleIds == null
           ? null
           : List.unmodifiable(boundCircleIds),
       primaryHomepageId = primaryHomepageId {}

  final String? draftTitle;
  final String? draftSummary;
  final String? bodyDigest;
  final List<String>? boundCircleIds;
  final String? primaryHomepageId;

  factory AssistantCreationRunIntent.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantCreationRunIntent",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "draftTitle",
      "draftSummary",
      "bodyDigest",
      "boundCircleIds",
      "primaryHomepageId",
    }, path);
    return AssistantCreationRunIntent(
      draftTitle: map["draftTitle"] == null
          ? null
          : _generatedRequestString(map["draftTitle"], '$path.draftTitle'),
      draftSummary: map["draftSummary"] == null
          ? null
          : _generatedRequestString(map["draftSummary"], '$path.draftSummary'),
      bodyDigest: map["bodyDigest"] == null
          ? null
          : _generatedRequestString(map["bodyDigest"], '$path.bodyDigest'),
      boundCircleIds: map["boundCircleIds"] == null
          ? null
          : List<String>.unmodifiable(
              _generatedRequestList(
                map["boundCircleIds"],
                '$path.boundCircleIds',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.boundCircleIds' + '[${entry.key}]',
                ),
              ),
            ),
      primaryHomepageId: map["primaryHomepageId"] == null
          ? null
          : _generatedRequestString(
              map["primaryHomepageId"],
              '$path.primaryHomepageId',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.draftTitle != null) "draftTitle": this.draftTitle!,
    if (this.draftSummary != null) "draftSummary": this.draftSummary!,
    if (this.bodyDigest != null) "bodyDigest": this.bodyDigest!,
    if (this.boundCircleIds != null)
      "boundCircleIds": this.boundCircleIds!
          .map((value) => value)
          .toList(growable: false),
    if (this.primaryHomepageId != null)
      "primaryHomepageId": this.primaryHomepageId!,
  };
}

final class AssistantDeviceActionExecutionReceipt {
  const AssistantDeviceActionExecutionReceipt({
    required String installationId,
    required String deviceId,
    required String capability,
    required String inputDigest,
    required String permit,
    required String idempotencyKey,
    required String outcome,
    required DateTime executedAt,
    String? deviceObjectId,
    String? failureCode,
  }) : installationId = installationId,
       deviceId = deviceId,
       capability = capability,
       inputDigest = inputDigest,
       permit = permit,
       idempotencyKey = idempotencyKey,
       outcome = outcome,
       executedAt = executedAt,
       deviceObjectId = deviceObjectId,
       failureCode = failureCode;

  final String installationId;
  final String deviceId;
  final String capability;
  final String inputDigest;
  final String permit;
  final String idempotencyKey;
  final String outcome;
  final DateTime executedAt;
  final String? deviceObjectId;
  final String? failureCode;

  factory AssistantDeviceActionExecutionReceipt.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantDeviceActionExecutionReceipt",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "installationId",
      "deviceId",
      "capability",
      "inputDigest",
      "permit",
      "idempotencyKey",
      "outcome",
      "executedAt",
      "deviceObjectId",
      "failureCode",
    }, path);
    return AssistantDeviceActionExecutionReceipt(
      installationId: _generatedRequestString(
        map["installationId"],
        '$path.installationId',
      ),
      deviceId: _generatedRequestString(map["deviceId"], '$path.deviceId'),
      capability: _generatedRequestString(
        map["capability"],
        '$path.capability',
      ),
      inputDigest: _generatedRequestString(
        map["inputDigest"],
        '$path.inputDigest',
      ),
      permit: _generatedRequestString(map["permit"], '$path.permit'),
      idempotencyKey: _generatedRequestString(
        map["idempotencyKey"],
        '$path.idempotencyKey',
      ),
      outcome: _generatedRequestString(map["outcome"], '$path.outcome'),
      executedAt: _generatedRequestTimestamp(
        map["executedAt"],
        '$path.executedAt',
      ),
      deviceObjectId: map["deviceObjectId"] == null
          ? null
          : _generatedRequestString(
              map["deviceObjectId"],
              '$path.deviceObjectId',
            ),
      failureCode: map["failureCode"] == null
          ? null
          : _generatedRequestString(map["failureCode"], '$path.failureCode'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "installationId": this.installationId,
    "deviceId": this.deviceId,
    "capability": this.capability,
    "inputDigest": this.inputDigest,
    "permit": this.permit,
    "idempotencyKey": this.idempotencyKey,
    "outcome": this.outcome,
    "executedAt": this.executedAt.toUtc().toIso8601String(),
    if (this.deviceObjectId != null) "deviceObjectId": this.deviceObjectId!,
    if (this.failureCode != null) "failureCode": this.failureCode!,
  };
}

final class AssistantEntryQuery {
  const AssistantEntryQuery({String? pageType, String? objectId})
    : pageType = pageType,
      objectId = objectId;

  final String? pageType;
  final String? objectId;

  factory AssistantEntryQuery.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantEntryQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "pageType",
      "objectId",
    }, path);
    return AssistantEntryQuery(
      pageType: map["pageType"] == null
          ? null
          : _generatedRequestString(map["pageType"], '$path.pageType'),
      objectId: map["objectId"] == null
          ? null
          : _generatedRequestString(map["objectId"], '$path.objectId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.pageType != null) "pageType": this.pageType!,
    if (this.objectId != null) "objectId": this.objectId!,
  };
}

final class AssistantIntersectionEvidenceRef {
  const AssistantIntersectionEvidenceRef({
    required String intersectionId,
    required String evidenceId,
    required String sourceRef,
    required String objectTypeRef,
    required String objectId,
  }) : intersectionId = intersectionId,
       evidenceId = evidenceId,
       sourceRef = sourceRef,
       objectTypeRef = objectTypeRef,
       objectId = objectId;

  final String intersectionId;
  final String evidenceId;
  final String sourceRef;
  final String objectTypeRef;
  final String objectId;

  factory AssistantIntersectionEvidenceRef.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantIntersectionEvidenceRef",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "intersectionId",
      "evidenceId",
      "sourceRef",
      "objectTypeRef",
      "objectId",
    }, path);
    return AssistantIntersectionEvidenceRef(
      intersectionId: _generatedRequestString(
        map["intersectionId"],
        '$path.intersectionId',
      ),
      evidenceId: _generatedRequestString(
        map["evidenceId"],
        '$path.evidenceId',
      ),
      sourceRef: _generatedRequestString(map["sourceRef"], '$path.sourceRef'),
      objectTypeRef: _generatedRequestString(
        map["objectTypeRef"],
        '$path.objectTypeRef',
      ),
      objectId: _generatedRequestString(map["objectId"], '$path.objectId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "intersectionId": this.intersectionId,
    "evidenceId": this.evidenceId,
    "sourceRef": this.sourceRef,
    "objectTypeRef": this.objectTypeRef,
    "objectId": this.objectId,
  };
}

final class AssistantLearningFactAppendCommand {
  AssistantLearningFactAppendCommand({
    required String eventId,
    required String factType,
    required String assistantTurnId,
    String? triggerMessageId,
    required String referralSource,
    required String domainId,
    String? eventType,
    String? feedbackType,
    double? feedbackScore,
    List<String> reasonCodes = const <String>[],
    String? actionType,
    String? suggestedActionId,
    int? durationMs,
    String? queryText,
    String? answerText,
    String? feedbackText,
    String? correctionText,
    required bool trainingEligible,
    required DateTime occurredAt,
  }) : eventId = eventId.trim(),
       factType = factType.trim(),
       assistantTurnId = assistantTurnId.trim(),
       triggerMessageId = _normalizeGeneratedOptionalText(triggerMessageId),
       referralSource = referralSource.trim(),
       domainId = domainId.trim(),
       eventType = _normalizeGeneratedOptionalText(eventType),
       feedbackType = _normalizeGeneratedOptionalText(feedbackType),
       feedbackScore = feedbackScore,
       reasonCodes = _normalizeGeneratedTextList(
         reasonCodes,
         deduplicate: true,
       ),
       actionType = _normalizeGeneratedOptionalText(actionType),
       suggestedActionId = _normalizeGeneratedOptionalText(suggestedActionId),
       durationMs = durationMs,
       queryText = _normalizeGeneratedOptionalText(queryText),
       answerText = _normalizeGeneratedOptionalText(answerText),
       feedbackText = _normalizeGeneratedOptionalText(feedbackText),
       correctionText = _normalizeGeneratedOptionalText(correctionText),
       trainingEligible = trainingEligible,
       occurredAt = occurredAt {
    if (this.eventId.isEmpty) {
      throw ArgumentError.value(this.eventId, "eventId", 'must not be blank');
    }
    if (this.factType.isEmpty) {
      throw ArgumentError.value(this.factType, "factType", 'must not be blank');
    }
    if (this.assistantTurnId.isEmpty) {
      throw ArgumentError.value(
        this.assistantTurnId,
        "assistantTurnId",
        'must not be blank',
      );
    }
    if (this.referralSource.isEmpty) {
      throw ArgumentError.value(
        this.referralSource,
        "referralSource",
        'must not be blank',
      );
    }
    if (this.domainId.isEmpty) {
      throw ArgumentError.value(this.domainId, "domainId", 'must not be blank');
    }
  }

  final String eventId;
  final String factType;
  final String assistantTurnId;
  final String? triggerMessageId;
  final String referralSource;
  final String domainId;
  final String? eventType;
  final String? feedbackType;
  final double? feedbackScore;
  final List<String> reasonCodes;
  final String? actionType;
  final String? suggestedActionId;
  final int? durationMs;
  final String? queryText;
  final String? answerText;
  final String? feedbackText;
  final String? correctionText;
  final bool trainingEligible;
  final DateTime occurredAt;

  factory AssistantLearningFactAppendCommand.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantLearningFactAppendCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "eventId",
      "factType",
      "assistantTurnId",
      "triggerMessageId",
      "referralSource",
      "domainId",
      "eventType",
      "feedbackType",
      "feedbackScore",
      "reasonCodes",
      "actionType",
      "suggestedActionId",
      "durationMs",
      "queryText",
      "answerText",
      "feedbackText",
      "correctionText",
      "trainingEligible",
      "occurredAt",
    }, path);
    return AssistantLearningFactAppendCommand(
      eventId: _generatedRequestString(map["eventId"], '$path.eventId'),
      factType: _generatedRequestString(map["factType"], '$path.factType'),
      assistantTurnId: _generatedRequestString(
        map["assistantTurnId"],
        '$path.assistantTurnId',
      ),
      triggerMessageId: map["triggerMessageId"] == null
          ? null
          : _generatedRequestString(
              map["triggerMessageId"],
              '$path.triggerMessageId',
            ),
      referralSource: _generatedRequestString(
        map["referralSource"],
        '$path.referralSource',
      ),
      domainId: _generatedRequestString(map["domainId"], '$path.domainId'),
      eventType: map["eventType"] == null
          ? null
          : _generatedRequestString(map["eventType"], '$path.eventType'),
      feedbackType: map["feedbackType"] == null
          ? null
          : _generatedRequestString(map["feedbackType"], '$path.feedbackType'),
      feedbackScore: map["feedbackScore"] == null
          ? null
          : _generatedRequestDouble(
              map["feedbackScore"],
              '$path.feedbackScore',
            ),
      reasonCodes: map.containsKey("reasonCodes")
          ? List<String>.unmodifiable(
              _generatedRequestList(
                map["reasonCodes"],
                '$path.reasonCodes',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.reasonCodes' + '[${entry.key}]',
                ),
              ),
            )
          : const <String>[],
      actionType: map["actionType"] == null
          ? null
          : _generatedRequestString(map["actionType"], '$path.actionType'),
      suggestedActionId: map["suggestedActionId"] == null
          ? null
          : _generatedRequestString(
              map["suggestedActionId"],
              '$path.suggestedActionId',
            ),
      durationMs: map["durationMs"] == null
          ? null
          : _generatedRequestInt(map["durationMs"], '$path.durationMs'),
      queryText: map["queryText"] == null
          ? null
          : _generatedRequestString(map["queryText"], '$path.queryText'),
      answerText: map["answerText"] == null
          ? null
          : _generatedRequestString(map["answerText"], '$path.answerText'),
      feedbackText: map["feedbackText"] == null
          ? null
          : _generatedRequestString(map["feedbackText"], '$path.feedbackText'),
      correctionText: map["correctionText"] == null
          ? null
          : _generatedRequestString(
              map["correctionText"],
              '$path.correctionText',
            ),
      trainingEligible: _generatedRequestBool(
        map["trainingEligible"],
        '$path.trainingEligible',
      ),
      occurredAt: _generatedRequestTimestamp(
        map["occurredAt"],
        '$path.occurredAt',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "eventId": this.eventId,
    "factType": this.factType,
    "assistantTurnId": this.assistantTurnId,
    if (this.triggerMessageId != null)
      "triggerMessageId": this.triggerMessageId!,
    "referralSource": this.referralSource,
    "domainId": this.domainId,
    if (this.eventType != null) "eventType": this.eventType!,
    if (this.feedbackType != null) "feedbackType": this.feedbackType!,
    if (this.feedbackScore != null) "feedbackScore": this.feedbackScore!,
    if (this.reasonCodes.isNotEmpty)
      "reasonCodes": this.reasonCodes
          .map((value) => value)
          .toList(growable: false),
    if (this.actionType != null) "actionType": this.actionType!,
    if (this.suggestedActionId != null)
      "suggestedActionId": this.suggestedActionId!,
    if (this.durationMs != null) "durationMs": this.durationMs!,
    if (this.queryText != null) "queryText": this.queryText!,
    if (this.answerText != null) "answerText": this.answerText!,
    if (this.feedbackText != null) "feedbackText": this.feedbackText!,
    if (this.correctionText != null) "correctionText": this.correctionText!,
    "trainingEligible": this.trainingEligible,
    "occurredAt": this.occurredAt.toUtc().toIso8601String(),
  };
}

final class AssistantObjectGroundingView {
  const AssistantObjectGroundingView({
    required String objectTypeRef,
    required String objectId,
  }) : objectTypeRef = objectTypeRef,
       objectId = objectId;

  final String objectTypeRef;
  final String objectId;

  factory AssistantObjectGroundingView.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantObjectGroundingView",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "objectTypeRef",
      "objectId",
    }, path);
    return AssistantObjectGroundingView(
      objectTypeRef: _generatedRequestString(
        map["objectTypeRef"],
        '$path.objectTypeRef',
      ),
      objectId: _generatedRequestString(map["objectId"], '$path.objectId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectTypeRef": this.objectTypeRef,
    "objectId": this.objectId,
  };
}

final class AssistantPauseRunRequest {
  const AssistantPauseRunRequest({required String runId, String? reason})
    : runId = runId,
      reason = reason;

  final String runId;
  final String? reason;

  factory AssistantPauseRunRequest.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantPauseRunRequest",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "runId",
      "reason",
    }, path);
    return AssistantPauseRunRequest(
      runId: _generatedRequestString(map["runId"], '$path.runId'),
      reason: map["reason"] == null
          ? null
          : _generatedRequestString(map["reason"], '$path.reason'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "runId": this.runId,
    if (this.reason != null) "reason": this.reason!,
  };
}

final class AssistantPreferenceByIdRequest {
  AssistantPreferenceByIdRequest({required String preferenceId})
    : preferenceId = preferenceId {
    if (this.preferenceId.isEmpty) {
      throw ArgumentError.value(
        this.preferenceId,
        "preferenceId",
        'must not be blank',
      );
    }
  }

  final String preferenceId;

  factory AssistantPreferenceByIdRequest.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantPreferenceByIdRequest",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "preferenceId",
    }, path);
    return AssistantPreferenceByIdRequest(
      preferenceId: _generatedRequestString(
        map["preferenceId"],
        '$path.preferenceId',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "preferenceId": this.preferenceId,
  };
}

final class AssistantRunByIdQuery {
  AssistantRunByIdQuery({required String runId}) : runId = runId {
    if (this.runId.isEmpty) {
      throw ArgumentError.value(this.runId, "runId", 'must not be blank');
    }
  }

  final String runId;

  factory AssistantRunByIdQuery.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantRunByIdQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"runId"}, path);
    return AssistantRunByIdQuery(
      runId: _generatedRequestString(map["runId"], '$path.runId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"runId": this.runId};
}

final class AssistantRunCommandRequest {
  const AssistantRunCommandRequest({required String runId}) : runId = runId;

  final String runId;

  factory AssistantRunCommandRequest.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantRunCommandRequest",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"runId"}, path);
    return AssistantRunCommandRequest(
      runId: _generatedRequestString(map["runId"], '$path.runId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"runId": this.runId};
}

final class AssistantRunDefinitionOfDoneInput {
  AssistantRunDefinitionOfDoneInput({
    required String outcome,
    List<String>? constraints,
    List<String>? verificationRequirements,
  }) : outcome = outcome,
       constraints = constraints == null
           ? null
           : List.unmodifiable(constraints),
       verificationRequirements = verificationRequirements == null
           ? null
           : List.unmodifiable(verificationRequirements) {}

  final String outcome;
  final List<String>? constraints;
  final List<String>? verificationRequirements;

  factory AssistantRunDefinitionOfDoneInput.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantRunDefinitionOfDoneInput",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "outcome",
      "constraints",
      "verificationRequirements",
    }, path);
    return AssistantRunDefinitionOfDoneInput(
      outcome: _generatedRequestString(map["outcome"], '$path.outcome'),
      constraints: map["constraints"] == null
          ? null
          : List<String>.unmodifiable(
              _generatedRequestList(
                map["constraints"],
                '$path.constraints',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.constraints' + '[${entry.key}]',
                ),
              ),
            ),
      verificationRequirements: map["verificationRequirements"] == null
          ? null
          : List<String>.unmodifiable(
              _generatedRequestList(
                map["verificationRequirements"],
                '$path.verificationRequirements',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.verificationRequirements' + '[${entry.key}]',
                ),
              ),
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "outcome": this.outcome,
    if (this.constraints != null)
      "constraints": this.constraints!
          .map((value) => value)
          .toList(growable: false),
    if (this.verificationRequirements != null)
      "verificationRequirements": this.verificationRequirements!
          .map((value) => value)
          .toList(growable: false),
  };
}

final class AssistantRunEventStreamQuery {
  AssistantRunEventStreamQuery({required String runId, String? resumeToken})
    : runId = runId,
      resumeToken = resumeToken {
    if (this.runId.isEmpty) {
      throw ArgumentError.value(this.runId, "runId", 'must not be blank');
    }
  }

  final String runId;
  final String? resumeToken;

  factory AssistantRunEventStreamQuery.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantRunEventStreamQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "runId",
      "resumeToken",
    }, path);
    return AssistantRunEventStreamQuery(
      runId: _generatedRequestString(map["runId"], '$path.runId'),
      resumeToken: map["resumeToken"] == null
          ? null
          : _generatedRequestString(map["resumeToken"], '$path.resumeToken'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "runId": this.runId,
    if (this.resumeToken != null) "resumeToken": this.resumeToken!,
  };
}

final class AssistantRunIntent {
  const AssistantRunIntent({
    required AssistantRunIntentKind kind,
    AssistantAnswerRunIntent? answer,
    AssistantSearchRunIntent? search,
    AssistantCreationRunIntent? creationAssistance,
  }) : kind = kind,
       answer = answer,
       search = search,
       creationAssistance = creationAssistance;

  final AssistantRunIntentKind kind;
  final AssistantAnswerRunIntent? answer;
  final AssistantSearchRunIntent? search;
  final AssistantCreationRunIntent? creationAssistance;

  factory AssistantRunIntent.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantRunIntent",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "kind",
      "answer",
      "search",
      "creationAssistance",
    }, path);
    return AssistantRunIntent(
      kind: switch (map["kind"]) {
        "answer" => AssistantRunIntentKind.answer,
        "search" => AssistantRunIntentKind.search,
        "creation_assistance" => AssistantRunIntentKind.creationAssistance,
        _ => throw FormatException('$path.kind' + ' has an invalid enum value'),
      },
      answer: map["answer"] == null
          ? null
          : AssistantAnswerRunIntent.fromWire(
              _generatedRequestObject(map["answer"], '$path.answer'),
              '$path.answer',
            ),
      search: map["search"] == null
          ? null
          : AssistantSearchRunIntent.fromWire(
              _generatedRequestObject(map["search"], '$path.search'),
              '$path.search',
            ),
      creationAssistance: map["creationAssistance"] == null
          ? null
          : AssistantCreationRunIntent.fromWire(
              _generatedRequestObject(
                map["creationAssistance"],
                '$path.creationAssistance',
              ),
              '$path.creationAssistance',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "kind": this.kind.wireName,
    if (this.answer != null) "answer": this.answer!.toWire(),
    if (this.search != null) "search": this.search!.toWire(),
    if (this.creationAssistance != null)
      "creationAssistance": this.creationAssistance!.toWire(),
  };
}

final class AssistantSearchRunIntent {
  const AssistantSearchRunIntent({
    required String query,
    SearchIntensity? searchIntensity,
    String? sourceSurfaceId,
    bool? fromGlobalSearch,
  }) : query = query,
       searchIntensity = searchIntensity,
       sourceSurfaceId = sourceSurfaceId,
       fromGlobalSearch = fromGlobalSearch;

  final String query;
  final SearchIntensity? searchIntensity;
  final String? sourceSurfaceId;
  final bool? fromGlobalSearch;

  factory AssistantSearchRunIntent.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantSearchRunIntent",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "query",
      "searchIntensity",
      "sourceSurfaceId",
      "fromGlobalSearch",
    }, path);
    return AssistantSearchRunIntent(
      query: _generatedRequestString(map["query"], '$path.query'),
      searchIntensity: map["searchIntensity"] == null
          ? null
          : switch (map["searchIntensity"]) {
              "low" => SearchIntensity.low,
              "medium" => SearchIntensity.medium,
              "high" => SearchIntensity.high,
              _ => throw FormatException(
                '$path.searchIntensity' + ' has an invalid enum value',
              ),
            },
      sourceSurfaceId: map["sourceSurfaceId"] == null
          ? null
          : _generatedRequestString(
              map["sourceSurfaceId"],
              '$path.sourceSurfaceId',
            ),
      fromGlobalSearch: map["fromGlobalSearch"] == null
          ? null
          : _generatedRequestBool(
              map["fromGlobalSearch"],
              '$path.fromGlobalSearch',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "query": this.query,
    if (this.searchIntensity != null)
      "searchIntensity": this.searchIntensity!.wireName,
    if (this.sourceSurfaceId != null) "sourceSurfaceId": this.sourceSurfaceId!,
    if (this.fromGlobalSearch != null)
      "fromGlobalSearch": this.fromGlobalSearch!,
  };
}

final class AssistantSessionByIdQuery {
  AssistantSessionByIdQuery({required String sessionId})
    : sessionId = sessionId.trim() {
    if (this.sessionId.isEmpty) {
      throw ArgumentError.value(
        this.sessionId,
        "sessionId",
        'must not be blank',
      );
    }
  }

  final String sessionId;

  factory AssistantSessionByIdQuery.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantSessionByIdQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "sessionId",
    }, path);
    return AssistantSessionByIdQuery(
      sessionId: _generatedRequestString(map["sessionId"], '$path.sessionId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "sessionId": this.sessionId,
  };
}

final class AssistantSessionListQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 50;

  AssistantSessionListQuery({int limit = 20, String? cursor})
    : limit = limit,
      cursor = _normalizeGeneratedOptionalText(cursor) {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 50) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 50");
    }
  }

  final int limit;
  final String? cursor;

  factory AssistantSessionListQuery.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantSessionListQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "limit",
      "cursor",
    }, path);
    return AssistantSessionListQuery(
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "limit": this.limit,
    if (this.cursor != null) "cursor": this.cursor!,
  };
}

final class AssistantSkillSubscriptionByIdQuery {
  AssistantSkillSubscriptionByIdQuery({required String subscriptionId})
    : subscriptionId = subscriptionId.trim() {
    if (this.subscriptionId.isEmpty) {
      throw ArgumentError.value(
        this.subscriptionId,
        "subscriptionId",
        'must not be blank',
      );
    }
  }

  final String subscriptionId;

  factory AssistantSkillSubscriptionByIdQuery.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantSkillSubscriptionByIdQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "subscriptionId",
    }, path);
    return AssistantSkillSubscriptionByIdQuery(
      subscriptionId: _generatedRequestString(
        map["subscriptionId"],
        '$path.subscriptionId',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "subscriptionId": this.subscriptionId,
  };
}

final class AssistantSkillSubscriptionListQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  AssistantSkillSubscriptionListQuery({int limit = 20, String? status})
    : limit = limit,
      status = _normalizeGeneratedOptionalText(status) {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final int limit;
  final String? status;

  factory AssistantSkillSubscriptionListQuery.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantSkillSubscriptionListQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "limit",
      "status",
    }, path);
    return AssistantSkillSubscriptionListQuery(
      limit: map.containsKey("limit")
          ? _generatedRequestInt(map["limit"], '$path.limit')
          : 20,
      status: map["status"] == null
          ? null
          : _generatedRequestString(map["status"], '$path.status'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "limit": this.limit,
    if (this.status != null) "status": this.status!,
  };
}

final class AssistantStartRunRequest {
  const AssistantStartRunRequest({
    required String sessionId,
    required String clientRequestId,
    required AssistantRunIntent intent,
    AssistantContextSnapshot? contextSnapshot,
    AssistantReasoningProfile? reasoningProfile,
    AssistantRunDefinitionOfDoneInput? definitionOfDone,
    AssistantSurfaceCapabilities? surfaceCapabilities,
  }) : sessionId = sessionId,
       clientRequestId = clientRequestId,
       intent = intent,
       contextSnapshot = contextSnapshot,
       reasoningProfile = reasoningProfile,
       definitionOfDone = definitionOfDone,
       surfaceCapabilities = surfaceCapabilities;

  final String sessionId;
  final String clientRequestId;
  final AssistantRunIntent intent;
  final AssistantContextSnapshot? contextSnapshot;
  final AssistantReasoningProfile? reasoningProfile;
  final AssistantRunDefinitionOfDoneInput? definitionOfDone;
  final AssistantSurfaceCapabilities? surfaceCapabilities;

  factory AssistantStartRunRequest.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantStartRunRequest",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "sessionId",
      "clientRequestId",
      "intent",
      "contextSnapshot",
      "reasoningProfile",
      "definitionOfDone",
      "surfaceCapabilities",
    }, path);
    return AssistantStartRunRequest(
      sessionId: _generatedRequestString(map["sessionId"], '$path.sessionId'),
      clientRequestId: _generatedRequestString(
        map["clientRequestId"],
        '$path.clientRequestId',
      ),
      intent: AssistantRunIntent.fromWire(
        _generatedRequestObject(map["intent"], '$path.intent'),
        '$path.intent',
      ),
      contextSnapshot: map["contextSnapshot"] == null
          ? null
          : AssistantContextSnapshot.fromWire(
              _generatedRequestObject(
                map["contextSnapshot"],
                '$path.contextSnapshot',
              ),
              '$path.contextSnapshot',
            ),
      reasoningProfile: map["reasoningProfile"] == null
          ? null
          : switch (map["reasoningProfile"]) {
              "fast" => AssistantReasoningProfile.fast,
              "balanced" => AssistantReasoningProfile.balanced,
              "deep" => AssistantReasoningProfile.deep,
              "background_long" => AssistantReasoningProfile.backgroundLong,
              _ => throw FormatException(
                '$path.reasoningProfile' + ' has an invalid enum value',
              ),
            },
      definitionOfDone: map["definitionOfDone"] == null
          ? null
          : AssistantRunDefinitionOfDoneInput.fromWire(
              _generatedRequestObject(
                map["definitionOfDone"],
                '$path.definitionOfDone',
              ),
              '$path.definitionOfDone',
            ),
      surfaceCapabilities: map["surfaceCapabilities"] == null
          ? null
          : AssistantSurfaceCapabilities.fromWire(
              _generatedRequestObject(
                map["surfaceCapabilities"],
                '$path.surfaceCapabilities',
              ),
              '$path.surfaceCapabilities',
            ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "sessionId": this.sessionId,
    "clientRequestId": this.clientRequestId,
    "intent": this.intent.toWire(),
    if (this.contextSnapshot != null)
      "contextSnapshot": this.contextSnapshot!.toWire(),
    if (this.reasoningProfile != null)
      "reasoningProfile": this.reasoningProfile!.wireName,
    if (this.definitionOfDone != null)
      "definitionOfDone": this.definitionOfDone!.toWire(),
    if (this.surfaceCapabilities != null)
      "surfaceCapabilities": this.surfaceCapabilities!.toWire(),
  };
}

final class AssistantSteerRunRequest {
  const AssistantSteerRunRequest({
    required String runId,
    required String instruction,
  }) : runId = runId,
       instruction = instruction;

  final String runId;
  final String instruction;

  factory AssistantSteerRunRequest.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantSteerRunRequest",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "runId",
      "instruction",
    }, path);
    return AssistantSteerRunRequest(
      runId: _generatedRequestString(map["runId"], '$path.runId'),
      instruction: _generatedRequestString(
        map["instruction"],
        '$path.instruction',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "runId": this.runId,
    "instruction": this.instruction,
  };
}

final class AssistantSubmitDeviceActionReceiptRequest {
  const AssistantSubmitDeviceActionReceiptRequest({
    required String runId,
    required String toolInvocationId,
    required AssistantDeviceActionExecutionReceipt receipt,
  }) : runId = runId,
       toolInvocationId = toolInvocationId,
       receipt = receipt;

  final String runId;
  final String toolInvocationId;
  final AssistantDeviceActionExecutionReceipt receipt;

  factory AssistantSubmitDeviceActionReceiptRequest.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantSubmitDeviceActionReceiptRequest",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "runId",
      "toolInvocationId",
      "receipt",
    }, path);
    return AssistantSubmitDeviceActionReceiptRequest(
      runId: _generatedRequestString(map["runId"], '$path.runId'),
      toolInvocationId: _generatedRequestString(
        map["toolInvocationId"],
        '$path.toolInvocationId',
      ),
      receipt: AssistantDeviceActionExecutionReceipt.fromWire(
        _generatedRequestObject(map["receipt"], '$path.receipt'),
        '$path.receipt',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "runId": this.runId,
    "toolInvocationId": this.toolInvocationId,
    "receipt": this.receipt.toWire(),
  };
}

final class AssistantSurfaceCapabilities {
  AssistantSurfaceCapabilities({
    required String surfaceId,
    required List<String> supportedNodeKinds,
    required List<String> supportedActionIntents,
    required String viewportClass,
    required String platform,
    required String theme,
    required double textScale,
    required bool reducedMotion,
    required bool offline,
  }) : surfaceId = surfaceId,
       supportedNodeKinds = List.unmodifiable(supportedNodeKinds),
       supportedActionIntents = List.unmodifiable(supportedActionIntents),
       viewportClass = viewportClass,
       platform = platform,
       theme = theme,
       textScale = textScale,
       reducedMotion = reducedMotion,
       offline = offline {}

  final String surfaceId;
  final List<String> supportedNodeKinds;
  final List<String> supportedActionIntents;
  final String viewportClass;
  final String platform;
  final String theme;
  final double textScale;
  final bool reducedMotion;
  final bool offline;

  factory AssistantSurfaceCapabilities.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantSurfaceCapabilities",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "surfaceId",
      "supportedNodeKinds",
      "supportedActionIntents",
      "viewportClass",
      "platform",
      "theme",
      "textScale",
      "reducedMotion",
      "offline",
    }, path);
    return AssistantSurfaceCapabilities(
      surfaceId: _generatedRequestString(map["surfaceId"], '$path.surfaceId'),
      supportedNodeKinds: List<String>.unmodifiable(
        _generatedRequestList(
          map["supportedNodeKinds"],
          '$path.supportedNodeKinds',
        ).asMap().entries.map(
          (entry) => _generatedRequestString(
            entry.value,
            '$path.supportedNodeKinds' + '[${entry.key}]',
          ),
        ),
      ),
      supportedActionIntents: List<String>.unmodifiable(
        _generatedRequestList(
          map["supportedActionIntents"],
          '$path.supportedActionIntents',
        ).asMap().entries.map(
          (entry) => _generatedRequestString(
            entry.value,
            '$path.supportedActionIntents' + '[${entry.key}]',
          ),
        ),
      ),
      viewportClass: _generatedRequestString(
        map["viewportClass"],
        '$path.viewportClass',
      ),
      platform: _generatedRequestString(map["platform"], '$path.platform'),
      theme: _generatedRequestString(map["theme"], '$path.theme'),
      textScale: _generatedRequestDouble(map["textScale"], '$path.textScale'),
      reducedMotion: _generatedRequestBool(
        map["reducedMotion"],
        '$path.reducedMotion',
      ),
      offline: _generatedRequestBool(map["offline"], '$path.offline'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "surfaceId": this.surfaceId,
    "supportedNodeKinds": this.supportedNodeKinds
        .map((value) => value)
        .toList(growable: false),
    "supportedActionIntents": this.supportedActionIntents
        .map((value) => value)
        .toList(growable: false),
    "viewportClass": this.viewportClass,
    "platform": this.platform,
    "theme": this.theme,
    "textScale": this.textScale,
    "reducedMotion": this.reducedMotion,
    "offline": this.offline,
  };
}

final class AssistantTurnListQuery {
  AssistantTurnListQuery({
    required String sessionId,
    int? limit,
    String? cursor,
  }) : sessionId = sessionId,
       limit = limit,
       cursor = cursor {
    if (this.sessionId.isEmpty) {
      throw ArgumentError.value(
        this.sessionId,
        "sessionId",
        'must not be blank',
      );
    }
  }

  final String sessionId;
  final int? limit;
  final String? cursor;

  factory AssistantTurnListQuery.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantTurnListQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "sessionId",
      "limit",
      "cursor",
    }, path);
    return AssistantTurnListQuery(
      sessionId: _generatedRequestString(map["sessionId"], '$path.sessionId'),
      limit: map["limit"] == null
          ? null
          : _generatedRequestInt(map["limit"], '$path.limit'),
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "sessionId": this.sessionId,
    if (this.limit != null) "limit": this.limit!,
    if (this.cursor != null) "cursor": this.cursor!,
  };
}

final class AssistantUserActionGroundingView {
  const AssistantUserActionGroundingView({
    required String action,
    String? objectTypeRef,
    String? objectId,
    DateTime? occurredAt,
  }) : action = action,
       objectTypeRef = objectTypeRef,
       objectId = objectId,
       occurredAt = occurredAt;

  final String action;
  final String? objectTypeRef;
  final String? objectId;
  final DateTime? occurredAt;

  factory AssistantUserActionGroundingView.fromWire(
    Map<String, Object?> map, [
    String path = "AssistantUserActionGroundingView",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "action",
      "objectTypeRef",
      "objectId",
      "occurredAt",
    }, path);
    return AssistantUserActionGroundingView(
      action: _generatedRequestString(map["action"], '$path.action'),
      objectTypeRef: map["objectTypeRef"] == null
          ? null
          : _generatedRequestString(
              map["objectTypeRef"],
              '$path.objectTypeRef',
            ),
      objectId: map["objectId"] == null
          ? null
          : _generatedRequestString(map["objectId"], '$path.objectId'),
      occurredAt: map["occurredAt"] == null
          ? null
          : _generatedRequestTimestamp(map["occurredAt"], '$path.occurredAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "action": this.action,
    if (this.objectTypeRef != null) "objectTypeRef": this.objectTypeRef!,
    if (this.objectId != null) "objectId": this.objectId!,
    if (this.occurredAt != null)
      "occurredAt": this.occurredAt!.toUtc().toIso8601String(),
  };
}

final class ConfirmSkillDataControlRequestCommand {
  ConfirmSkillDataControlRequestCommand({
    required String requestId,
    required int expectedRevision,
    required bool confirmed,
  }) : requestId = requestId,
       expectedRevision = expectedRevision,
       confirmed = confirmed {
    if (this.requestId.isEmpty) {
      throw ArgumentError.value(
        this.requestId,
        "requestId",
        'must not be blank',
      );
    }
    if (this.expectedRevision <= 0) {
      throw ArgumentError.value(
        this.expectedRevision,
        "expectedRevision",
        "must be positive",
      );
    }
  }

  final String requestId;
  final int expectedRevision;
  final bool confirmed;

  factory ConfirmSkillDataControlRequestCommand.fromWire(
    Map<String, Object?> map, [
    String path = "ConfirmSkillDataControlRequestCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "requestId",
      "expectedRevision",
      "confirmed",
    }, path);
    return ConfirmSkillDataControlRequestCommand(
      requestId: _generatedRequestString(map["requestId"], '$path.requestId'),
      expectedRevision: _generatedRequestInt(
        map["expectedRevision"],
        '$path.expectedRevision',
      ),
      confirmed: _generatedRequestBool(map["confirmed"], '$path.confirmed'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "requestId": this.requestId,
    "expectedRevision": this.expectedRevision,
    "confirmed": this.confirmed,
  };
}

final class CreateAssistantSkillSubscriptionCommand {
  CreateAssistantSkillSubscriptionCommand({
    required String skillId,
    required String domainId,
    List<String> tagRefs = const <String>[],
    required SkillSubscriptionSearchQueryPlanWire searchQueryPlan,
    required SkillSubscriptionTriggerWire trigger,
    required SkillSubscriptionDestinationWire destination,
    required String clientRequestId,
  }) : skillId = skillId.trim(),
       domainId = domainId.trim(),
       tagRefs = _normalizeGeneratedTextList(tagRefs, deduplicate: true),
       searchQueryPlan = searchQueryPlan,
       trigger = trigger,
       destination = destination,
       clientRequestId = clientRequestId.trim() {
    if (this.skillId.isEmpty) {
      throw ArgumentError.value(this.skillId, "skillId", 'must not be blank');
    }
    if (this.domainId.isEmpty) {
      throw ArgumentError.value(this.domainId, "domainId", 'must not be blank');
    }
    if (this.clientRequestId.isEmpty) {
      throw ArgumentError.value(
        this.clientRequestId,
        "clientRequestId",
        'must not be blank',
      );
    }
  }

  final String skillId;
  final String domainId;
  final List<String> tagRefs;
  final SkillSubscriptionSearchQueryPlanWire searchQueryPlan;
  final SkillSubscriptionTriggerWire trigger;
  final SkillSubscriptionDestinationWire destination;
  final String clientRequestId;

  factory CreateAssistantSkillSubscriptionCommand.fromWire(
    Map<String, Object?> map, [
    String path = "CreateAssistantSkillSubscriptionCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "skillId",
      "domainId",
      "tagRefs",
      "searchQueryPlan",
      "trigger",
      "destination",
      "clientRequestId",
    }, path);
    return CreateAssistantSkillSubscriptionCommand(
      skillId: _generatedRequestString(map["skillId"], '$path.skillId'),
      domainId: _generatedRequestString(map["domainId"], '$path.domainId'),
      tagRefs: map.containsKey("tagRefs")
          ? List<String>.unmodifiable(
              _generatedRequestList(
                map["tagRefs"],
                '$path.tagRefs',
              ).asMap().entries.map(
                (entry) => _generatedRequestString(
                  entry.value,
                  '$path.tagRefs' + '[${entry.key}]',
                ),
              ),
            )
          : const <String>[],
      searchQueryPlan: SkillSubscriptionSearchQueryPlanWire.fromWire(
        _generatedRequestObject(
          map["searchQueryPlan"],
          '$path.searchQueryPlan',
        ),
        '$path.searchQueryPlan',
      ),
      trigger: SkillSubscriptionTriggerWire.fromWire(
        _generatedRequestObject(map["trigger"], '$path.trigger'),
        '$path.trigger',
      ),
      destination: SkillSubscriptionDestinationWire.fromWire(
        _generatedRequestObject(map["destination"], '$path.destination'),
        '$path.destination',
      ),
      clientRequestId: _generatedRequestString(
        map["clientRequestId"],
        '$path.clientRequestId',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "skillId": this.skillId,
    "domainId": this.domainId,
    "tagRefs": this.tagRefs.map((value) => value).toList(growable: false),
    "searchQueryPlan": this.searchQueryPlan.toWire(),
    "trigger": this.trigger.toWire(),
    "destination": this.destination.toWire(),
    "clientRequestId": this.clientRequestId,
  };
}

final class CreateSkillDataControlRequestCommand {
  CreateSkillDataControlRequestCommand({
    required String skillId,
    required List<SkillDataControlAction> requestedActions,
  }) : skillId = skillId,
       requestedActions = List.unmodifiable(requestedActions) {
    if (this.skillId.isEmpty) {
      throw ArgumentError.value(this.skillId, "skillId", 'must not be blank');
    }
  }

  final String skillId;
  final List<SkillDataControlAction> requestedActions;

  factory CreateSkillDataControlRequestCommand.fromWire(
    Map<String, Object?> map, [
    String path = "CreateSkillDataControlRequestCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "skillId",
      "requestedActions",
    }, path);
    return CreateSkillDataControlRequestCommand(
      skillId: _generatedRequestString(map["skillId"], '$path.skillId'),
      requestedActions: List<SkillDataControlAction>.unmodifiable(
        _generatedRequestList(
          map["requestedActions"],
          '$path.requestedActions',
        ).asMap().entries.map(
          (entry) => switch (entry.value) {
            "hide_activity_history" =>
              SkillDataControlAction.hideActivityHistory,
            "revoke_consent" => SkillDataControlAction.revokeConsent,
            "archive_subscriptions" =>
              SkillDataControlAction.archiveSubscriptions,
            _ => throw FormatException(
              '$path.requestedActions' +
                  '[${entry.key}]' +
                  ' has an invalid enum value',
            ),
          },
        ),
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "skillId": this.skillId,
    "requestedActions": this.requestedActions
        .map((value) => value.wireName)
        .toList(growable: false),
  };
}

final class GetSkillCatalogItemQuery {
  const GetSkillCatalogItemQuery({required String skillId}) : skillId = skillId;

  final String skillId;

  factory GetSkillCatalogItemQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetSkillCatalogItemQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"skillId"}, path);
    return GetSkillCatalogItemQuery(
      skillId: _generatedRequestString(map["skillId"], '$path.skillId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"skillId": this.skillId};
}

final class GetSkillDataControlRequestQuery {
  GetSkillDataControlRequestQuery({required String requestId})
    : requestId = requestId {
    if (this.requestId.isEmpty) {
      throw ArgumentError.value(
        this.requestId,
        "requestId",
        'must not be blank',
      );
    }
  }

  final String requestId;

  factory GetSkillDataControlRequestQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetSkillDataControlRequestQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "requestId",
    }, path);
    return GetSkillDataControlRequestQuery(
      requestId: _generatedRequestString(map["requestId"], '$path.requestId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "requestId": this.requestId,
  };
}

final class GetSkillSurfacePlacementQuery {
  GetSkillSurfacePlacementQuery({
    required SkillSurfaceKind surfaceKind,
    required String surfaceId,
  }) : surfaceKind = surfaceKind,
       surfaceId = surfaceId {
    if (this.surfaceId.isEmpty) {
      throw ArgumentError.value(
        this.surfaceId,
        "surfaceId",
        'must not be blank',
      );
    }
  }

  final SkillSurfaceKind surfaceKind;
  final String surfaceId;

  factory GetSkillSurfacePlacementQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetSkillSurfacePlacementQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "surfaceKind",
      "surfaceId",
    }, path);
    return GetSkillSurfacePlacementQuery(
      surfaceKind: switch (map["surfaceKind"]) {
        "conversation" => SkillSurfaceKind.conversation,
        "circle" => SkillSurfaceKind.circle,
        _ => throw FormatException(
          '$path.surfaceKind' + ' has an invalid enum value',
        ),
      },
      surfaceId: _generatedRequestString(map["surfaceId"], '$path.surfaceId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "surfaceKind": this.surfaceKind.wireName,
    "surfaceId": this.surfaceId,
  };
}

final class GetSkillUserSettingQuery {
  GetSkillUserSettingQuery({required String skillId}) : skillId = skillId {
    if (this.skillId.isEmpty) {
      throw ArgumentError.value(this.skillId, "skillId", 'must not be blank');
    }
  }

  final String skillId;

  factory GetSkillUserSettingQuery.fromWire(
    Map<String, Object?> map, [
    String path = "GetSkillUserSettingQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"skillId"}, path);
    return GetSkillUserSettingQuery(
      skillId: _generatedRequestString(map["skillId"], '$path.skillId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"skillId": this.skillId};
}

final class GrantSkillConsentRequest {
  GrantSkillConsentRequest({
    required String skillId,
    required List<String> grantedScopes,
  }) : skillId = skillId,
       grantedScopes = List.unmodifiable(grantedScopes) {
    if (this.skillId.isEmpty) {
      throw ArgumentError.value(this.skillId, "skillId", 'must not be blank');
    }
  }

  final String skillId;
  final List<String> grantedScopes;

  factory GrantSkillConsentRequest.fromWire(
    Map<String, Object?> map, [
    String path = "GrantSkillConsentRequest",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "skillId",
      "grantedScopes",
    }, path);
    return GrantSkillConsentRequest(
      skillId: _generatedRequestString(map["skillId"], '$path.skillId'),
      grantedScopes: List<String>.unmodifiable(
        _generatedRequestList(
          map["grantedScopes"],
          '$path.grantedScopes',
        ).asMap().entries.map(
          (entry) => _generatedRequestString(
            entry.value,
            '$path.grantedScopes' + '[${entry.key}]',
          ),
        ),
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "skillId": this.skillId,
    "grantedScopes": this.grantedScopes
        .map((value) => value)
        .toList(growable: false),
  };
}

final class ListAssistantPreferencesQuery {
  const ListAssistantPreferencesQuery({
    String? scope,
    String? sessionId,
    String? status,
  }) : scope = scope,
       sessionId = sessionId,
       status = status;

  final String? scope;
  final String? sessionId;
  final String? status;

  factory ListAssistantPreferencesQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ListAssistantPreferencesQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "scope",
      "sessionId",
      "status",
    }, path);
    return ListAssistantPreferencesQuery(
      scope: map["scope"] == null
          ? null
          : _generatedRequestString(map["scope"], '$path.scope'),
      sessionId: map["sessionId"] == null
          ? null
          : _generatedRequestString(map["sessionId"], '$path.sessionId'),
      status: map["status"] == null
          ? null
          : _generatedRequestString(map["status"], '$path.status'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.scope != null) "scope": this.scope!,
    if (this.sessionId != null) "sessionId": this.sessionId!,
    if (this.status != null) "status": this.status!,
  };
}

final class ListAssistantTasksQuery {
  const ListAssistantTasksQuery({int? limit, String? status})
    : limit = limit,
      status = status;

  final int? limit;
  final String? status;

  factory ListAssistantTasksQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ListAssistantTasksQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "limit",
      "status",
    }, path);
    return ListAssistantTasksQuery(
      limit: map["limit"] == null
          ? null
          : _generatedRequestInt(map["limit"], '$path.limit'),
      status: map["status"] == null
          ? null
          : _generatedRequestString(map["status"], '$path.status'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.limit != null) "limit": this.limit!,
    if (this.status != null) "status": this.status!,
  };
}

final class ListSkillActivitiesQuery {
  ListSkillActivitiesQuery({
    required String skillId,
    String? cursor,
    int? limit,
  }) : skillId = skillId,
       cursor = cursor,
       limit = limit {
    if (this.skillId.isEmpty) {
      throw ArgumentError.value(this.skillId, "skillId", 'must not be blank');
    }
    if (this.limit != null && this.limit! <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit != null && this.limit! > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String skillId;
  final String? cursor;
  final int? limit;

  factory ListSkillActivitiesQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ListSkillActivitiesQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "skillId",
      "cursor",
      "limit",
    }, path);
    return ListSkillActivitiesQuery(
      skillId: _generatedRequestString(map["skillId"], '$path.skillId'),
      cursor: map["cursor"] == null
          ? null
          : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map["limit"] == null
          ? null
          : _generatedRequestInt(map["limit"], '$path.limit'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "skillId": this.skillId,
    if (this.cursor != null) "cursor": this.cursor!,
    if (this.limit != null) "limit": this.limit!,
  };
}

final class ListSkillConsentsQuery {
  const ListSkillConsentsQuery();
}

final class ListSkillUserSettingsQuery {
  ListSkillUserSettingsQuery({int? limit}) : limit = limit {
    if (this.limit != null && this.limit! <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit != null && this.limit! > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final int? limit;

  factory ListSkillUserSettingsQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ListSkillUserSettingsQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"limit"}, path);
    return ListSkillUserSettingsQuery(
      limit: map["limit"] == null
          ? null
          : _generatedRequestInt(map["limit"], '$path.limit'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.limit != null) "limit": this.limit!,
  };
}

final class ListSkillsQuery {
  ListSkillsQuery({int? limit}) : limit = limit {
    if (this.limit != null && this.limit! <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit != null && this.limit! > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final int? limit;

  factory ListSkillsQuery.fromWire(
    Map<String, Object?> map, [
    String path = "ListSkillsQuery",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"limit"}, path);
    return ListSkillsQuery(
      limit: map["limit"] == null
          ? null
          : _generatedRequestInt(map["limit"], '$path.limit'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.limit != null) "limit": this.limit!,
  };
}

final class PageContextAction {
  const PageContextAction({
    required String actionType,
    String? objectTypeRef,
    String? objectId,
  }) : actionType = actionType,
       objectTypeRef = objectTypeRef,
       objectId = objectId;

  final String actionType;
  final String? objectTypeRef;
  final String? objectId;

  factory PageContextAction.fromWire(
    Map<String, Object?> map, [
    String path = "PageContextAction",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "actionType",
      "objectTypeRef",
      "objectId",
    }, path);
    return PageContextAction(
      actionType: _generatedRequestString(
        map["actionType"],
        '$path.actionType',
      ),
      objectTypeRef: map["objectTypeRef"] == null
          ? null
          : _generatedRequestString(
              map["objectTypeRef"],
              '$path.objectTypeRef',
            ),
      objectId: map["objectId"] == null
          ? null
          : _generatedRequestString(map["objectId"], '$path.objectId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "actionType": this.actionType,
    if (this.objectTypeRef != null) "objectTypeRef": this.objectTypeRef!,
    if (this.objectId != null) "objectId": this.objectId!,
  };
}

final class PageContextObjectRef {
  const PageContextObjectRef({
    required String objectTypeRef,
    required String objectId,
  }) : objectTypeRef = objectTypeRef,
       objectId = objectId;

  final String objectTypeRef;
  final String objectId;

  factory PageContextObjectRef.fromWire(
    Map<String, Object?> map, [
    String path = "PageContextObjectRef",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "objectTypeRef",
      "objectId",
    }, path);
    return PageContextObjectRef(
      objectTypeRef: _generatedRequestString(
        map["objectTypeRef"],
        '$path.objectTypeRef',
      ),
      objectId: _generatedRequestString(map["objectId"], '$path.objectId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectTypeRef": this.objectTypeRef,
    "objectId": this.objectId,
  };
}

final class PageContextSnapshot {
  PageContextSnapshot({
    required DateTime capturedAt,
    required AssistantPageContextType pageType,
    required List<PageContextObjectRef> pageObjects,
    required List<PageContextAction> userActions,
    required bool consentGranted,
  }) : capturedAt = capturedAt,
       pageType = pageType,
       pageObjects = List.unmodifiable(pageObjects),
       userActions = List.unmodifiable(userActions),
       consentGranted = consentGranted {}

  final DateTime capturedAt;
  final AssistantPageContextType pageType;
  final List<PageContextObjectRef> pageObjects;
  final List<PageContextAction> userActions;
  final bool consentGranted;

  factory PageContextSnapshot.fromWire(
    Map<String, Object?> map, [
    String path = "PageContextSnapshot",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "capturedAt",
      "pageType",
      "pageObjects",
      "userActions",
      "consentGranted",
    }, path);
    return PageContextSnapshot(
      capturedAt: _generatedRequestTimestamp(
        map["capturedAt"],
        '$path.capturedAt',
      ),
      pageType: switch (map["pageType"]) {
        "unknown" => AssistantPageContextType.unknown,
        "home" => AssistantPageContextType.home,
        "discovery" => AssistantPageContextType.discovery,
        "circles" => AssistantPageContextType.circles,
        "article" => AssistantPageContextType.article,
        "profile" => AssistantPageContextType.profile,
        "chat" => AssistantPageContextType.chat,
        "create" => AssistantPageContextType.create,
        "search" => AssistantPageContextType.search,
        _ => throw FormatException(
          '$path.pageType' + ' has an invalid enum value',
        ),
      },
      pageObjects: List<PageContextObjectRef>.unmodifiable(
        _generatedRequestList(
          map["pageObjects"],
          '$path.pageObjects',
        ).asMap().entries.map(
          (entry) => PageContextObjectRef.fromWire(
            _generatedRequestObject(
              entry.value,
              '$path.pageObjects' + '[${entry.key}]',
            ),
            '$path.pageObjects' + '[${entry.key}]',
          ),
        ),
      ),
      userActions: List<PageContextAction>.unmodifiable(
        _generatedRequestList(
          map["userActions"],
          '$path.userActions',
        ).asMap().entries.map(
          (entry) => PageContextAction.fromWire(
            _generatedRequestObject(
              entry.value,
              '$path.userActions' + '[${entry.key}]',
            ),
            '$path.userActions' + '[${entry.key}]',
          ),
        ),
      ),
      consentGranted: _generatedRequestBool(
        map["consentGranted"],
        '$path.consentGranted',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "capturedAt": this.capturedAt.toUtc().toIso8601String(),
    "pageType": this.pageType.wireName,
    "pageObjects": this.pageObjects
        .map((value) => value.toWire())
        .toList(growable: false),
    "userActions": this.userActions
        .map((value) => value.toWire())
        .toList(growable: false),
    "consentGranted": this.consentGranted,
  };
}

final class PutSkillSurfacePlacementRequest {
  PutSkillSurfacePlacementRequest({
    required SkillSurfaceKind surfaceKind,
    required String surfaceId,
    required SkillSurfacePlacementPolicy policy,
    required List<String> disabledSkillIds,
    required SkillSurfacePlacementStatus status,
    required int expectedRevision,
  }) : surfaceKind = surfaceKind,
       surfaceId = surfaceId,
       policy = policy,
       disabledSkillIds = List.unmodifiable(disabledSkillIds),
       status = status,
       expectedRevision = expectedRevision {
    if (this.surfaceId.isEmpty) {
      throw ArgumentError.value(
        this.surfaceId,
        "surfaceId",
        'must not be blank',
      );
    }
  }

  final SkillSurfaceKind surfaceKind;
  final String surfaceId;
  final SkillSurfacePlacementPolicy policy;
  final List<String> disabledSkillIds;
  final SkillSurfacePlacementStatus status;
  final int expectedRevision;

  factory PutSkillSurfacePlacementRequest.fromWire(
    Map<String, Object?> map, [
    String path = "PutSkillSurfacePlacementRequest",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "surfaceKind",
      "surfaceId",
      "policy",
      "disabledSkillIds",
      "status",
      "expectedRevision",
    }, path);
    return PutSkillSurfacePlacementRequest(
      surfaceKind: switch (map["surfaceKind"]) {
        "conversation" => SkillSurfaceKind.conversation,
        "circle" => SkillSurfaceKind.circle,
        _ => throw FormatException(
          '$path.surfaceKind' + ' has an invalid enum value',
        ),
      },
      surfaceId: _generatedRequestString(map["surfaceId"], '$path.surfaceId'),
      policy: switch (map["policy"]) {
        "all_shared_eligible" => SkillSurfacePlacementPolicy.allSharedEligible,
        _ => throw FormatException(
          '$path.policy' + ' has an invalid enum value',
        ),
      },
      disabledSkillIds: List<String>.unmodifiable(
        _generatedRequestList(
          map["disabledSkillIds"],
          '$path.disabledSkillIds',
        ).asMap().entries.map(
          (entry) => _generatedRequestString(
            entry.value,
            '$path.disabledSkillIds' + '[${entry.key}]',
          ),
        ),
      ),
      status: switch (map["status"]) {
        "active" => SkillSurfacePlacementStatus.active,
        "archived" => SkillSurfacePlacementStatus.archived,
        _ => throw FormatException(
          '$path.status' + ' has an invalid enum value',
        ),
      },
      expectedRevision: _generatedRequestInt(
        map["expectedRevision"],
        '$path.expectedRevision',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "surfaceKind": this.surfaceKind.wireName,
    "surfaceId": this.surfaceId,
    "policy": this.policy.wireName,
    "disabledSkillIds": this.disabledSkillIds
        .map((value) => value)
        .toList(growable: false),
    "status": this.status.wireName,
    "expectedRevision": this.expectedRevision,
  };
}

final class PutSkillUserSettingRequest {
  PutSkillUserSettingRequest({
    required String skillId,
    required SkillUserSettingStatus status,
    required Map<String, Object?> configurationData,
    required String configurationSchemaDigest,
    required SkillMemoryPolicy memoryPolicy,
    required List<String> connectorConnectionRefs,
    required int expectedRevision,
  }) : skillId = skillId,
       status = status,
       configurationData = Map.unmodifiable(configurationData),
       configurationSchemaDigest = configurationSchemaDigest,
       memoryPolicy = memoryPolicy,
       connectorConnectionRefs = List.unmodifiable(connectorConnectionRefs),
       expectedRevision = expectedRevision {
    if (this.skillId.isEmpty) {
      throw ArgumentError.value(this.skillId, "skillId", 'must not be blank');
    }
  }

  final String skillId;
  final SkillUserSettingStatus status;
  final Map<String, Object?> configurationData;
  final String configurationSchemaDigest;
  final SkillMemoryPolicy memoryPolicy;
  final List<String> connectorConnectionRefs;
  final int expectedRevision;

  factory PutSkillUserSettingRequest.fromWire(
    Map<String, Object?> map, [
    String path = "PutSkillUserSettingRequest",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "skillId",
      "status",
      "configurationData",
      "configurationSchemaDigest",
      "memoryPolicy",
      "connectorConnectionRefs",
      "expectedRevision",
    }, path);
    return PutSkillUserSettingRequest(
      skillId: _generatedRequestString(map["skillId"], '$path.skillId'),
      status: switch (map["status"]) {
        "enabled" => SkillUserSettingStatus.enabled,
        "disabled" => SkillUserSettingStatus.disabled,
        _ => throw FormatException(
          '$path.status' + ' has an invalid enum value',
        ),
      },
      configurationData: _generatedRequestObject(
        map["configurationData"],
        '$path.configurationData',
      ),
      configurationSchemaDigest: _generatedRequestString(
        map["configurationSchemaDigest"],
        '$path.configurationSchemaDigest',
      ),
      memoryPolicy: switch (map["memoryPolicy"]) {
        "package_default" => SkillMemoryPolicy.packageDefault,
        "confirm_before_save" => SkillMemoryPolicy.confirmBeforeSave,
        "disabled" => SkillMemoryPolicy.disabled,
        _ => throw FormatException(
          '$path.memoryPolicy' + ' has an invalid enum value',
        ),
      },
      connectorConnectionRefs: List<String>.unmodifiable(
        _generatedRequestList(
          map["connectorConnectionRefs"],
          '$path.connectorConnectionRefs',
        ).asMap().entries.map(
          (entry) => _generatedRequestString(
            entry.value,
            '$path.connectorConnectionRefs' + '[${entry.key}]',
          ),
        ),
      ),
      expectedRevision: _generatedRequestInt(
        map["expectedRevision"],
        '$path.expectedRevision',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "skillId": this.skillId,
    "status": this.status.wireName,
    "configurationData": this.configurationData,
    "configurationSchemaDigest": this.configurationSchemaDigest,
    "memoryPolicy": this.memoryPolicy.wireName,
    "connectorConnectionRefs": this.connectorConnectionRefs
        .map((value) => value)
        .toList(growable: false),
    "expectedRevision": this.expectedRevision,
  };
}

final class ReportPageContextCommand {
  const ReportPageContextCommand({required PageContextSnapshot contextSnapshot})
    : contextSnapshot = contextSnapshot;

  final PageContextSnapshot contextSnapshot;

  factory ReportPageContextCommand.fromWire(
    Map<String, Object?> map, [
    String path = "ReportPageContextCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "contextSnapshot",
    }, path);
    return ReportPageContextCommand(
      contextSnapshot: PageContextSnapshot.fromWire(
        _generatedRequestObject(
          map["contextSnapshot"],
          '$path.contextSnapshot',
        ),
        '$path.contextSnapshot',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "contextSnapshot": this.contextSnapshot.toWire(),
  };
}

final class RevokeSkillConsentRequest {
  RevokeSkillConsentRequest({required String skillId}) : skillId = skillId {
    if (this.skillId.isEmpty) {
      throw ArgumentError.value(this.skillId, "skillId", 'must not be blank');
    }
  }

  final String skillId;

  factory RevokeSkillConsentRequest.fromWire(
    Map<String, Object?> map, [
    String path = "RevokeSkillConsentRequest",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"skillId"}, path);
    return RevokeSkillConsentRequest(
      skillId: _generatedRequestString(map["skillId"], '$path.skillId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{"skillId": this.skillId};
}

final class SetAssistantPreferenceRequest {
  const SetAssistantPreferenceRequest({
    required AssistantPreferenceScope scope,
    String? sessionId,
    required AssistantPreferenceKind kind,
    required String value,
    required AssistantPreferenceSourceType sourceType,
    String? sourceSessionId,
    required bool confirmed,
  }) : scope = scope,
       sessionId = sessionId,
       kind = kind,
       value = value,
       sourceType = sourceType,
       sourceSessionId = sourceSessionId,
       confirmed = confirmed;

  final AssistantPreferenceScope scope;
  final String? sessionId;
  final AssistantPreferenceKind kind;
  final String value;
  final AssistantPreferenceSourceType sourceType;
  final String? sourceSessionId;
  final bool confirmed;

  factory SetAssistantPreferenceRequest.fromWire(
    Map<String, Object?> map, [
    String path = "SetAssistantPreferenceRequest",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "scope",
      "sessionId",
      "kind",
      "value",
      "sourceType",
      "sourceSessionId",
      "confirmed",
    }, path);
    return SetAssistantPreferenceRequest(
      scope: switch (map["scope"]) {
        "session" => AssistantPreferenceScope.session,
        "long_term" => AssistantPreferenceScope.longTerm,
        "unknown" => AssistantPreferenceScope.unknown,
        _ => throw FormatException(
          '$path.scope' + ' has an invalid enum value',
        ),
      },
      sessionId: map["sessionId"] == null
          ? null
          : _generatedRequestString(map["sessionId"], '$path.sessionId'),
      kind: switch (map["kind"]) {
        "response_style" => AssistantPreferenceKind.responseStyle,
        "reply_length" => AssistantPreferenceKind.replyLength,
        "tone" => AssistantPreferenceKind.tone,
        "language" => AssistantPreferenceKind.language,
        "frequent_locations" => AssistantPreferenceKind.frequentLocations,
        "family_terms" => AssistantPreferenceKind.familyTerms,
        "dietary_restrictions" => AssistantPreferenceKind.dietaryRestrictions,
        "travel_preferences" => AssistantPreferenceKind.travelPreferences,
        "unknown" => AssistantPreferenceKind.unknown,
        _ => throw FormatException('$path.kind' + ' has an invalid enum value'),
      },
      value: _generatedRequestString(map["value"], '$path.value'),
      sourceType: switch (map["sourceType"]) {
        "explicit_rewrite" => AssistantPreferenceSourceType.explicitRewrite,
        "management" => AssistantPreferenceSourceType.management,
        "session_confirmed" => AssistantPreferenceSourceType.sessionConfirmed,
        "unknown" => AssistantPreferenceSourceType.unknown,
        _ => throw FormatException(
          '$path.sourceType' + ' has an invalid enum value',
        ),
      },
      sourceSessionId: map["sourceSessionId"] == null
          ? null
          : _generatedRequestString(
              map["sourceSessionId"],
              '$path.sourceSessionId',
            ),
      confirmed: _generatedRequestBool(map["confirmed"], '$path.confirmed'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "scope": this.scope.wireName,
    if (this.sessionId != null) "sessionId": this.sessionId!,
    "kind": this.kind.wireName,
    "value": this.value,
    "sourceType": this.sourceType.wireName,
    if (this.sourceSessionId != null) "sourceSessionId": this.sourceSessionId!,
    "confirmed": this.confirmed,
  };
}

final class UpdateAssistantSkillSubscriptionStatusCommand {
  UpdateAssistantSkillSubscriptionStatusCommand({
    required String subscriptionId,
    required String status,
    required String clientRequestId,
  }) : subscriptionId = subscriptionId.trim(),
       status = status.trim(),
       clientRequestId = clientRequestId.trim() {
    if (this.subscriptionId.isEmpty) {
      throw ArgumentError.value(
        this.subscriptionId,
        "subscriptionId",
        'must not be blank',
      );
    }
    if (this.status.isEmpty) {
      throw ArgumentError.value(this.status, "status", 'must not be blank');
    }
    if (this.clientRequestId.isEmpty) {
      throw ArgumentError.value(
        this.clientRequestId,
        "clientRequestId",
        'must not be blank',
      );
    }
  }

  final String subscriptionId;
  final String status;
  final String clientRequestId;

  factory UpdateAssistantSkillSubscriptionStatusCommand.fromWire(
    Map<String, Object?> map, [
    String path = "UpdateAssistantSkillSubscriptionStatusCommand",
  ]) {
    _generatedRequestRejectUnknownFields(map, const <String>{
      "subscriptionId",
      "status",
      "clientRequestId",
    }, path);
    return UpdateAssistantSkillSubscriptionStatusCommand(
      subscriptionId: _generatedRequestString(
        map["subscriptionId"],
        '$path.subscriptionId',
      ),
      status: _generatedRequestString(map["status"], '$path.status'),
      clientRequestId: _generatedRequestString(
        map["clientRequestId"],
        '$path.clientRequestId',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "subscriptionId": this.subscriptionId,
    "status": this.status,
    "clientRequestId": this.clientRequestId,
  };
}

CloudOperationRequestPayload
encodeAssistantAssistantEntryViewGetAssistantEntryGeneratedRequest(
  AssistantEntryQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.pageType != null) "pageType": request.pageType!,
      if (request.objectId != null) "objectId": request.objectId!,
    },
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantLearningFactAppendAssistantLearningFactGeneratedRequest(
  AssistantLearningFactAppendCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "eventId": request.eventId,
      "factType": request.factType,
      "assistantTurnId": request.assistantTurnId,
      if (request.triggerMessageId != null)
        "triggerMessageId": request.triggerMessageId!,
      "referralSource": request.referralSource,
      "domainId": request.domainId,
      if (request.eventType != null) "eventType": request.eventType!,
      if (request.feedbackType != null) "feedbackType": request.feedbackType!,
      if (request.feedbackScore != null)
        "feedbackScore": request.feedbackScore!,
      if (request.reasonCodes.isNotEmpty)
        "reasonCodes": request.reasonCodes
            .map((value) => value)
            .toList(growable: false),
      if (request.actionType != null) "actionType": request.actionType!,
      if (request.suggestedActionId != null)
        "suggestedActionId": request.suggestedActionId!,
      if (request.durationMs != null) "durationMs": request.durationMs!,
      if (request.queryText != null) "queryText": request.queryText!,
      if (request.answerText != null) "answerText": request.answerText!,
      if (request.feedbackText != null) "feedbackText": request.feedbackText!,
      if (request.correctionText != null)
        "correctionText": request.correctionText!,
      "trainingEligible": request.trainingEligible,
      "occurredAt": request.occurredAt.toUtc().toIso8601String(),
    },
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantPreferenceListAssistantPreferencesGeneratedRequest(
  ListAssistantPreferencesQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.scope != null) "scope": request.scope!,
      if (request.sessionId != null) "sessionId": request.sessionId!,
      if (request.status != null) "status": request.status!,
    },
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantPreferenceRestoreAssistantPreferenceGeneratedRequest(
  AssistantPreferenceByIdRequest request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"preferenceId": request.preferenceId},
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantPreferenceRevokeAssistantPreferenceGeneratedRequest(
  AssistantPreferenceByIdRequest request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"preferenceId": request.preferenceId},
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantPreferenceSetAssistantPreferenceGeneratedRequest(
  SetAssistantPreferenceRequest request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "scope": request.scope.wireName,
      if (request.sessionId != null) "sessionId": request.sessionId!,
      "kind": request.kind.wireName,
      "value": request.value,
      "sourceType": request.sourceType.wireName,
      if (request.sourceSessionId != null)
        "sourceSessionId": request.sourceSessionId!,
      "confirmed": request.confirmed,
    },
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantRunApproveAssistantToolUseGeneratedRequest(
  AssistantApproveToolUseRequest request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "runId": request.runId,
      "toolInvocationId": request.toolInvocationId,
    },
    body: <String, Object?>{
      "decision": request.decision,
      "approvalPermit": request.approvalPermit,
      if (request.installationId != null)
        "installationId": request.installationId!,
      if (request.deviceId != null) "deviceId": request.deviceId!,
    },
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantRunCancelAssistantRunGeneratedRequest(
  AssistantRunCommandRequest request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"runId": request.runId},
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantRunGetAssistantRunGeneratedRequest(
  AssistantRunByIdQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"runId": request.runId},
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantRunPauseAssistantRunGeneratedRequest(
  AssistantPauseRunRequest request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"runId": request.runId},
    body: <String, Object?>{
      if (request.reason != null) "reason": request.reason!,
    },
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantRunResumeAssistantRunGeneratedRequest(
  AssistantRunCommandRequest request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"runId": request.runId},
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantRunStartAssistantRunGeneratedRequest(
  AssistantStartRunRequest request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"sessionId": request.sessionId},
    body: <String, Object?>{
      "clientRequestId": request.clientRequestId,
      "intent": request.intent.toWire(),
      if (request.contextSnapshot != null)
        "contextSnapshot": request.contextSnapshot!.toWire(),
      if (request.reasoningProfile != null)
        "reasoningProfile": request.reasoningProfile!.wireName,
      if (request.definitionOfDone != null)
        "definitionOfDone": request.definitionOfDone!.toWire(),
      if (request.surfaceCapabilities != null)
        "surfaceCapabilities": request.surfaceCapabilities!.toWire(),
    },
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantRunSteerAssistantRunGeneratedRequest(
  AssistantSteerRunRequest request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"runId": request.runId},
    body: <String, Object?>{"instruction": request.instruction},
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantRunStreamAssistantRunEventsGeneratedRequest(
  AssistantRunEventStreamQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"runId": request.runId},
    queryParameters: <String, String>{
      if (request.resumeToken != null) "resumeToken": request.resumeToken!,
    },
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantRunSubmitDeviceActionReceiptGeneratedRequest(
  AssistantSubmitDeviceActionReceiptRequest request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "runId": request.runId,
      "toolInvocationId": request.toolInvocationId,
    },
    body: <String, Object?>{"receipt": request.receipt.toWire()},
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantSessionCreateAssistantSessionGeneratedRequest(
  AssistantCreateSessionRequest request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      if (request.summary != null) "summary": request.summary!,
      "clientRequestId": request.clientRequestId,
    },
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantSessionGetAssistantSessionGeneratedRequest(
  AssistantSessionByIdQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"sessionId": request.sessionId},
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantSessionListAssistantSessionsGeneratedRequest(
  AssistantSessionListQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantTaskViewListAssistantTasksGeneratedRequest(
  ListAssistantTasksQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.limit != null) "limit": (request.limit!).toString(),
      if (request.status != null) "status": request.status!,
    },
  );
}

CloudOperationRequestPayload
encodeAssistantAssistantTurnViewListSessionTurnsGeneratedRequest(
  AssistantTurnListQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"sessionId": request.sessionId},
    queryParameters: <String, String>{
      if (request.limit != null) "limit": (request.limit!).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

CloudOperationRequestPayload
encodeAssistantPageContextReportPageContextGeneratedRequest(
  ReportPageContextCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "contextSnapshot": request.contextSnapshot.toWire(),
    },
  );
}

CloudOperationRequestPayload
encodeAssistantSkillActivityViewListSkillActivitiesGeneratedRequest(
  ListSkillActivitiesQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"skillId": request.skillId},
    queryParameters: <String, String>{
      if (request.cursor != null) "cursor": request.cursor!,
      if (request.limit != null) "limit": (request.limit!).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeAssistantSkillCatalogGetSkillCatalogItemGeneratedRequest(
  GetSkillCatalogItemQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"skillId": request.skillId},
  );
}

CloudOperationRequestPayload
encodeAssistantSkillCatalogListSkillsGeneratedRequest(ListSkillsQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.limit != null) "limit": (request.limit!).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeAssistantSkillConsentGrantSkillConsentGeneratedRequest(
  GrantSkillConsentRequest request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"skillId": request.skillId},
    body: <String, Object?>{
      "grantedScopes": request.grantedScopes
          .map((value) => value)
          .toList(growable: false),
    },
  );
}

CloudOperationRequestPayload
encodeAssistantSkillConsentListConsentsGeneratedRequest(
  ListSkillConsentsQuery request,
) {
  return CloudOperationRequestPayload();
}

CloudOperationRequestPayload
encodeAssistantSkillConsentRevokeSkillConsentGeneratedRequest(
  RevokeSkillConsentRequest request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"skillId": request.skillId},
  );
}

CloudOperationRequestPayload
encodeAssistantSkillDataControlRequestConfirmSkillDataControlRequestGeneratedRequest(
  ConfirmSkillDataControlRequestCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"requestId": request.requestId},
    body: <String, Object?>{
      "expectedRevision": request.expectedRevision,
      "confirmed": request.confirmed,
    },
  );
}

CloudOperationRequestPayload
encodeAssistantSkillDataControlRequestCreateSkillDataControlRequestGeneratedRequest(
  CreateSkillDataControlRequestCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"skillId": request.skillId},
    body: <String, Object?>{
      "requestedActions": request.requestedActions
          .map((value) => value.wireName)
          .toList(growable: false),
    },
  );
}

CloudOperationRequestPayload
encodeAssistantSkillDataControlRequestGetSkillDataControlRequestGeneratedRequest(
  GetSkillDataControlRequestQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"requestId": request.requestId},
  );
}

CloudOperationRequestPayload
encodeAssistantSkillSubscriptionCreateSkillSubscriptionGeneratedRequest(
  CreateAssistantSkillSubscriptionCommand request,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "skillId": request.skillId,
      "domainId": request.domainId,
      "tagRefs": request.tagRefs.map((value) => value).toList(growable: false),
      "searchQueryPlan": request.searchQueryPlan.toWire(),
      "trigger": request.trigger.toWire(),
      "destination": request.destination.toWire(),
      "clientRequestId": request.clientRequestId,
    },
  );
}

CloudOperationRequestPayload
encodeAssistantSkillSubscriptionGetSkillSubscriptionGeneratedRequest(
  AssistantSkillSubscriptionByIdQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"subscriptionId": request.subscriptionId},
  );
}

CloudOperationRequestPayload
encodeAssistantSkillSubscriptionListSkillSubscriptionsGeneratedRequest(
  AssistantSkillSubscriptionListQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.status != null) "status": request.status!,
    },
  );
}

CloudOperationRequestPayload
encodeAssistantSkillSubscriptionUpdateSkillSubscriptionStatusGeneratedRequest(
  UpdateAssistantSkillSubscriptionStatusCommand request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"subscriptionId": request.subscriptionId},
    body: <String, Object?>{
      "status": request.status,
      "clientRequestId": request.clientRequestId,
    },
  );
}

CloudOperationRequestPayload
encodeAssistantSkillSurfacePlacementGetSkillSurfacePlacementGeneratedRequest(
  GetSkillSurfacePlacementQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "surfaceKind": (request.surfaceKind.wireName).toString(),
      "surfaceId": request.surfaceId,
    },
  );
}

CloudOperationRequestPayload
encodeAssistantSkillSurfacePlacementPutSkillSurfacePlacementGeneratedRequest(
  PutSkillSurfacePlacementRequest request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "surfaceKind": (request.surfaceKind.wireName).toString(),
      "surfaceId": request.surfaceId,
    },
    body: <String, Object?>{
      "policy": request.policy.wireName,
      "disabledSkillIds": request.disabledSkillIds
          .map((value) => value)
          .toList(growable: false),
      "status": request.status.wireName,
      "expectedRevision": request.expectedRevision,
    },
  );
}

CloudOperationRequestPayload
encodeAssistantSkillUserSettingGetSkillUserSettingGeneratedRequest(
  GetSkillUserSettingQuery request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"skillId": request.skillId},
  );
}

CloudOperationRequestPayload
encodeAssistantSkillUserSettingListSkillUserSettingsGeneratedRequest(
  ListSkillUserSettingsQuery request,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.limit != null) "limit": (request.limit!).toString(),
    },
  );
}

CloudOperationRequestPayload
encodeAssistantSkillUserSettingPutSkillUserSettingGeneratedRequest(
  PutSkillUserSettingRequest request,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{"skillId": request.skillId},
    body: <String, Object?>{
      "status": request.status.wireName,
      "configurationData": request.configurationData,
      "configurationSchemaDigest": request.configurationSchemaDigest,
      "memoryPolicy": request.memoryPolicy.wireName,
      "connectorConnectionRefs": request.connectorConnectionRefs
          .map((value) => value)
          .toList(growable: false),
      "expectedRevision": request.expectedRevision,
    },
  );
}
