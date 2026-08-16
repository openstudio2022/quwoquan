// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 2a80fd8995b437f8bf98acb9e3f369212a5edf05d488c5b22f54c343a0db9cad

part of '../../../ops/ops_operation_contracts.g.dart';

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

// Derived from product_ops/event_record/event_catalog.yaml; source SHA256: c9f4f405b855fb7cd9d8fd76e4ebbf1fba38e98a4432d43a8b852f1549fa3471.
final class EventRecord {
  EventRecord({
    required String logType,
    required String eventType,
    required String sessionId,
    required String pageName,
    required DateTime occurredAt,
    required String deviceManufacturer,
    required String deviceModel,
    required String appVersion,
    required String networkClass,
    String? action,
    int? attemptIndex,
    int? audioUnderrunCount,
    String? backgroundRetryTerminal,
    String? cacheAgeBucket,
    String? cacheClass,
    int? cacheSizeBytes,
    String? cacheSource,
    List<String>? callStack,
    String? callType,
    String? catalogSource,
    String? channelId,
    String? chatAction,
    String? chatOutcome,
    String? chatSource,
    int? connectTimeMs,
    String? consentState,
    String? contentType,
    String? copyKey,
    String? correlationHash,
    String? countdownBucket,
    int? currentValue,
    int? declaredDurationMs,
    bool? decoderFallbackEnabled,
    String? decoderQueueMode,
    String? detectionSource,
    String? devicePlatform,
    bool? digestMatch,
    String? disconnectReason,
    String? dismissPolicy,
    int? droppedFrames,
    bool? durationMismatch,
    int? durationMs,
    int? effectivePlaybackMs,
    String? entryMode,
    String? environment,
    String? errorCode,
    String? failReasonCode,
    String? failureKind,
    String? feedbackSurface,
    String? flowId,
    String? fromStep,
    String? governanceAction,
    bool? hasCache,
    bool? hasError,
    int? httpStatus,
    int? inflightValue,
    int? jankThresholdMs,
    int? jankyFrames,
    String? journey,
    int? limitValue,
    bool? mediaConnected,
    String? memberCountBucket,
    String? mentionScope,
    bool? motionReduced,
    String? networkQuality,
    String? objectId,
    String? objectState,
    String? objectType,
    int? observedDurationMs,
    String? operationId,
    String? otpPurpose,
    int? participantCount,
    String? playbackMode,
    int? processedVideoFrames,
    String? provider,
    String? publicationStage,
    int? queuedValue,
    int? rankPosition,
    int? readyMs,
    String? reasonId,
    int? rebufferCount,
    int? rebufferMs,
    int? reconnectCount,
    String? recoveryAction,
    String? releaseIdHash,
    String? rendererMode,
    String? requestId,
    String? resourceKind,
    String? resourceProfile,
    String? result,
    int? resultCount,
    int? sampledFrames,
    int? seekCommandMaxMs,
    int? seekCount,
    String? seekEvidenceSource,
    int? seekFailureCount,
    int? seekSettleMaxMs,
    String? step,
    String? surfaceId,
    int? tClickToContentMs,
    int? tClickToFirstFrameMs,
    int? tFirstFrameToShellMs,
    int? tShellToContentMs,
    String? targetId,
    String? targetType,
    String? terminalState,
    String? toStep,
    String? traceId,
    String? transport,
    int? ttffMs,
    String? turnAction,
    String? unreadCountBucket,
    String? watermarkResult,
    int? worstBuildFrameMs,
    int? worstFrameMs,
    int? worstRasterFrameMs,
  }) : logType = logType,
       eventType = eventType,
       sessionId = sessionId,
       pageName = pageName,
       occurredAt = occurredAt,
       deviceManufacturer = deviceManufacturer,
       deviceModel = deviceModel,
       appVersion = appVersion,
       networkClass = networkClass,
       action = action,
       attemptIndex = attemptIndex,
       audioUnderrunCount = audioUnderrunCount,
       backgroundRetryTerminal = backgroundRetryTerminal,
       cacheAgeBucket = cacheAgeBucket,
       cacheClass = cacheClass,
       cacheSizeBytes = cacheSizeBytes,
       cacheSource = cacheSource,
       callStack = callStack == null ? null : List.unmodifiable(callStack),
       callType = callType,
       catalogSource = catalogSource,
       channelId = channelId,
       chatAction = chatAction,
       chatOutcome = chatOutcome,
       chatSource = chatSource,
       connectTimeMs = connectTimeMs,
       consentState = consentState,
       contentType = contentType,
       copyKey = copyKey,
       correlationHash = correlationHash,
       countdownBucket = countdownBucket,
       currentValue = currentValue,
       declaredDurationMs = declaredDurationMs,
       decoderFallbackEnabled = decoderFallbackEnabled,
       decoderQueueMode = decoderQueueMode,
       detectionSource = detectionSource,
       devicePlatform = devicePlatform,
       digestMatch = digestMatch,
       disconnectReason = disconnectReason,
       dismissPolicy = dismissPolicy,
       droppedFrames = droppedFrames,
       durationMismatch = durationMismatch,
       durationMs = durationMs,
       effectivePlaybackMs = effectivePlaybackMs,
       entryMode = entryMode,
       environment = environment,
       errorCode = errorCode,
       failReasonCode = failReasonCode,
       failureKind = failureKind,
       feedbackSurface = feedbackSurface,
       flowId = flowId,
       fromStep = fromStep,
       governanceAction = governanceAction,
       hasCache = hasCache,
       hasError = hasError,
       httpStatus = httpStatus,
       inflightValue = inflightValue,
       jankThresholdMs = jankThresholdMs,
       jankyFrames = jankyFrames,
       journey = journey,
       limitValue = limitValue,
       mediaConnected = mediaConnected,
       memberCountBucket = memberCountBucket,
       mentionScope = mentionScope,
       motionReduced = motionReduced,
       networkQuality = networkQuality,
       objectId = objectId,
       objectState = objectState,
       objectType = objectType,
       observedDurationMs = observedDurationMs,
       operationId = operationId,
       otpPurpose = otpPurpose,
       participantCount = participantCount,
       playbackMode = playbackMode,
       processedVideoFrames = processedVideoFrames,
       provider = provider,
       publicationStage = publicationStage,
       queuedValue = queuedValue,
       rankPosition = rankPosition,
       readyMs = readyMs,
       reasonId = reasonId,
       rebufferCount = rebufferCount,
       rebufferMs = rebufferMs,
       reconnectCount = reconnectCount,
       recoveryAction = recoveryAction,
       releaseIdHash = releaseIdHash,
       rendererMode = rendererMode,
       requestId = requestId,
       resourceKind = resourceKind,
       resourceProfile = resourceProfile,
       result = result,
       resultCount = resultCount,
       sampledFrames = sampledFrames,
       seekCommandMaxMs = seekCommandMaxMs,
       seekCount = seekCount,
       seekEvidenceSource = seekEvidenceSource,
       seekFailureCount = seekFailureCount,
       seekSettleMaxMs = seekSettleMaxMs,
       step = step,
       surfaceId = surfaceId,
       tClickToContentMs = tClickToContentMs,
       tClickToFirstFrameMs = tClickToFirstFrameMs,
       tFirstFrameToShellMs = tFirstFrameToShellMs,
       tShellToContentMs = tShellToContentMs,
       targetId = targetId,
       targetType = targetType,
       terminalState = terminalState,
       toStep = toStep,
       traceId = traceId,
       transport = transport,
       ttffMs = ttffMs,
       turnAction = turnAction,
       unreadCountBucket = unreadCountBucket,
       watermarkResult = watermarkResult,
       worstBuildFrameMs = worstBuildFrameMs,
       worstFrameMs = worstFrameMs,
       worstRasterFrameMs = worstRasterFrameMs {
    if (this.action != null && this.action!.length > 128) {
      throw ArgumentError.value(this.action, "action", "length exceeds 128");
    }
    if (this.attemptIndex != null && this.attemptIndex! < 0) {
      throw ArgumentError.value(this.attemptIndex, "attemptIndex", "must be at least 0");
    }
    if (this.audioUnderrunCount != null && this.audioUnderrunCount! < 0) {
      throw ArgumentError.value(this.audioUnderrunCount, "audioUnderrunCount", "must be at least 0");
    }
    if (this.cacheClass != null && this.cacheClass!.length > 32) {
      throw ArgumentError.value(this.cacheClass, "cacheClass", "length exceeds 32");
    }
    if (this.cacheSizeBytes != null && this.cacheSizeBytes! < 0) {
      throw ArgumentError.value(this.cacheSizeBytes, "cacheSizeBytes", "must be at least 0");
    }
    if (this.callStack != null && this.callStack!.length > 10) {
      throw ArgumentError.value(this.callStack, "callStack", "item count exceeds 10");
    }
    if (this.channelId != null && this.channelId!.length > 64) {
      throw ArgumentError.value(this.channelId, "channelId", "length exceeds 64");
    }
    if (this.connectTimeMs != null && this.connectTimeMs! < 0) {
      throw ArgumentError.value(this.connectTimeMs, "connectTimeMs", "must be at least 0");
    }
    if (this.consentState != null && this.consentState!.length > 32) {
      throw ArgumentError.value(this.consentState, "consentState", "length exceeds 32");
    }
    if (this.copyKey != null && this.copyKey!.length > 128) {
      throw ArgumentError.value(this.copyKey, "copyKey", "length exceeds 128");
    }
    if (this.correlationHash != null && this.correlationHash!.length > 64) {
      throw ArgumentError.value(this.correlationHash, "correlationHash", "length exceeds 64");
    }
    if (this.countdownBucket != null && this.countdownBucket!.length > 32) {
      throw ArgumentError.value(this.countdownBucket, "countdownBucket", "length exceeds 32");
    }
    if (this.currentValue != null && this.currentValue! < 0) {
      throw ArgumentError.value(this.currentValue, "currentValue", "must be at least 0");
    }
    if (this.declaredDurationMs != null && this.declaredDurationMs! < 0) {
      throw ArgumentError.value(this.declaredDurationMs, "declaredDurationMs", "must be at least 0");
    }
    if (this.disconnectReason != null && this.disconnectReason!.length > 128) {
      throw ArgumentError.value(this.disconnectReason, "disconnectReason", "length exceeds 128");
    }
    if (this.dismissPolicy != null && this.dismissPolicy!.length > 64) {
      throw ArgumentError.value(this.dismissPolicy, "dismissPolicy", "length exceeds 64");
    }
    if (this.droppedFrames != null && this.droppedFrames! < 0) {
      throw ArgumentError.value(this.droppedFrames, "droppedFrames", "must be at least 0");
    }
    if (this.durationMs != null && this.durationMs! < 0) {
      throw ArgumentError.value(this.durationMs, "durationMs", "must be at least 0");
    }
    if (this.effectivePlaybackMs != null && this.effectivePlaybackMs! < 0) {
      throw ArgumentError.value(this.effectivePlaybackMs, "effectivePlaybackMs", "must be at least 0");
    }
    if (this.entryMode != null && this.entryMode!.length > 64) {
      throw ArgumentError.value(this.entryMode, "entryMode", "length exceeds 64");
    }
    if (this.errorCode != null && this.errorCode!.length > 128) {
      throw ArgumentError.value(this.errorCode, "errorCode", "length exceeds 128");
    }
    if (this.failReasonCode != null && this.failReasonCode!.length > 128) {
      throw ArgumentError.value(this.failReasonCode, "failReasonCode", "length exceeds 128");
    }
    if (this.failureKind != null && this.failureKind!.length > 64) {
      throw ArgumentError.value(this.failureKind, "failureKind", "length exceeds 64");
    }
    if (this.feedbackSurface != null && this.feedbackSurface!.length > 32) {
      throw ArgumentError.value(this.feedbackSurface, "feedbackSurface", "length exceeds 32");
    }
    if (this.flowId != null && this.flowId!.length > 96) {
      throw ArgumentError.value(this.flowId, "flowId", "length exceeds 96");
    }
    if (this.fromStep != null && this.fromStep!.length > 64) {
      throw ArgumentError.value(this.fromStep, "fromStep", "length exceeds 64");
    }
    if (this.httpStatus != null && this.httpStatus! < 100) {
      throw ArgumentError.value(this.httpStatus, "httpStatus", "must be at least 100");
    }
    if (this.httpStatus != null && this.httpStatus! > 599) {
      throw ArgumentError.value(this.httpStatus, "httpStatus", "must not exceed 599");
    }
    if (this.inflightValue != null && this.inflightValue! < 0) {
      throw ArgumentError.value(this.inflightValue, "inflightValue", "must be at least 0");
    }
    if (this.jankThresholdMs != null && this.jankThresholdMs! < 1) {
      throw ArgumentError.value(this.jankThresholdMs, "jankThresholdMs", "must be at least 1");
    }
    if (this.jankyFrames != null && this.jankyFrames! < 0) {
      throw ArgumentError.value(this.jankyFrames, "jankyFrames", "must be at least 0");
    }
    if (this.journey != null && this.journey!.length > 128) {
      throw ArgumentError.value(this.journey, "journey", "length exceeds 128");
    }
    if (this.limitValue != null && this.limitValue! < 0) {
      throw ArgumentError.value(this.limitValue, "limitValue", "must be at least 0");
    }
    if (this.objectId != null && this.objectId!.length > 256) {
      throw ArgumentError.value(this.objectId, "objectId", "length exceeds 256");
    }
    if (this.objectType != null && this.objectType!.length > 64) {
      throw ArgumentError.value(this.objectType, "objectType", "length exceeds 64");
    }
    if (this.observedDurationMs != null && this.observedDurationMs! < 0) {
      throw ArgumentError.value(this.observedDurationMs, "observedDurationMs", "must be at least 0");
    }
    if (this.operationId != null && this.operationId!.length > 128) {
      throw ArgumentError.value(this.operationId, "operationId", "length exceeds 128");
    }
    if (this.otpPurpose != null && this.otpPurpose!.length > 32) {
      throw ArgumentError.value(this.otpPurpose, "otpPurpose", "length exceeds 32");
    }
    if (this.participantCount != null && this.participantCount! < 0) {
      throw ArgumentError.value(this.participantCount, "participantCount", "must be at least 0");
    }
    if (this.playbackMode != null && this.playbackMode!.length > 32) {
      throw ArgumentError.value(this.playbackMode, "playbackMode", "length exceeds 32");
    }
    if (this.processedVideoFrames != null && this.processedVideoFrames! < 0) {
      throw ArgumentError.value(this.processedVideoFrames, "processedVideoFrames", "must be at least 0");
    }
    if (this.provider != null && this.provider!.length > 32) {
      throw ArgumentError.value(this.provider, "provider", "length exceeds 32");
    }
    if (this.queuedValue != null && this.queuedValue! < 0) {
      throw ArgumentError.value(this.queuedValue, "queuedValue", "must be at least 0");
    }
    if (this.rankPosition != null && this.rankPosition! < 0) {
      throw ArgumentError.value(this.rankPosition, "rankPosition", "must be at least 0");
    }
    if (this.readyMs != null && this.readyMs! < 0) {
      throw ArgumentError.value(this.readyMs, "readyMs", "must be at least 0");
    }
    if (this.reasonId != null && this.reasonId!.length > 256) {
      throw ArgumentError.value(this.reasonId, "reasonId", "length exceeds 256");
    }
    if (this.rebufferCount != null && this.rebufferCount! < 0) {
      throw ArgumentError.value(this.rebufferCount, "rebufferCount", "must be at least 0");
    }
    if (this.rebufferMs != null && this.rebufferMs! < 0) {
      throw ArgumentError.value(this.rebufferMs, "rebufferMs", "must be at least 0");
    }
    if (this.reconnectCount != null && this.reconnectCount! < 0) {
      throw ArgumentError.value(this.reconnectCount, "reconnectCount", "must be at least 0");
    }
    if (this.recoveryAction != null && this.recoveryAction!.length > 64) {
      throw ArgumentError.value(this.recoveryAction, "recoveryAction", "length exceeds 64");
    }
    if (this.releaseIdHash != null && this.releaseIdHash!.length > 64) {
      throw ArgumentError.value(this.releaseIdHash, "releaseIdHash", "length exceeds 64");
    }
    if (this.requestId != null && this.requestId!.length > 256) {
      throw ArgumentError.value(this.requestId, "requestId", "length exceeds 256");
    }
    if (this.result != null && this.result!.length > 128) {
      throw ArgumentError.value(this.result, "result", "length exceeds 128");
    }
    if (this.resultCount != null && this.resultCount! < 0) {
      throw ArgumentError.value(this.resultCount, "resultCount", "must be at least 0");
    }
    if (this.sampledFrames != null && this.sampledFrames! < 1) {
      throw ArgumentError.value(this.sampledFrames, "sampledFrames", "must be at least 1");
    }
    if (this.seekCommandMaxMs != null && this.seekCommandMaxMs! < 0) {
      throw ArgumentError.value(this.seekCommandMaxMs, "seekCommandMaxMs", "must be at least 0");
    }
    if (this.seekCount != null && this.seekCount! < 0) {
      throw ArgumentError.value(this.seekCount, "seekCount", "must be at least 0");
    }
    if (this.seekFailureCount != null && this.seekFailureCount! < 0) {
      throw ArgumentError.value(this.seekFailureCount, "seekFailureCount", "must be at least 0");
    }
    if (this.seekSettleMaxMs != null && this.seekSettleMaxMs! < 0) {
      throw ArgumentError.value(this.seekSettleMaxMs, "seekSettleMaxMs", "must be at least 0");
    }
    if (this.step != null && this.step!.length > 64) {
      throw ArgumentError.value(this.step, "step", "length exceeds 64");
    }
    if (this.surfaceId != null && this.surfaceId!.length > 128) {
      throw ArgumentError.value(this.surfaceId, "surfaceId", "length exceeds 128");
    }
    if (this.tClickToContentMs != null && this.tClickToContentMs! < 0) {
      throw ArgumentError.value(this.tClickToContentMs, "tClickToContentMs", "must be at least 0");
    }
    if (this.tClickToFirstFrameMs != null && this.tClickToFirstFrameMs! < 0) {
      throw ArgumentError.value(this.tClickToFirstFrameMs, "tClickToFirstFrameMs", "must be at least 0");
    }
    if (this.tFirstFrameToShellMs != null && this.tFirstFrameToShellMs! < 0) {
      throw ArgumentError.value(this.tFirstFrameToShellMs, "tFirstFrameToShellMs", "must be at least 0");
    }
    if (this.tShellToContentMs != null && this.tShellToContentMs! < 0) {
      throw ArgumentError.value(this.tShellToContentMs, "tShellToContentMs", "must be at least 0");
    }
    if (this.targetId != null && this.targetId!.length > 256) {
      throw ArgumentError.value(this.targetId, "targetId", "length exceeds 256");
    }
    if (this.targetType != null && this.targetType!.length > 64) {
      throw ArgumentError.value(this.targetType, "targetType", "length exceeds 64");
    }
    if (this.toStep != null && this.toStep!.length > 64) {
      throw ArgumentError.value(this.toStep, "toStep", "length exceeds 64");
    }
    if (this.traceId != null && this.traceId!.length > 256) {
      throw ArgumentError.value(this.traceId, "traceId", "length exceeds 256");
    }
    if (this.ttffMs != null && this.ttffMs! < 0) {
      throw ArgumentError.value(this.ttffMs, "ttffMs", "must be at least 0");
    }
    if (this.worstBuildFrameMs != null && this.worstBuildFrameMs! < 0) {
      throw ArgumentError.value(this.worstBuildFrameMs, "worstBuildFrameMs", "must be at least 0");
    }
    if (this.worstFrameMs != null && this.worstFrameMs! < 0) {
      throw ArgumentError.value(this.worstFrameMs, "worstFrameMs", "must be at least 0");
    }
    if (this.worstRasterFrameMs != null && this.worstRasterFrameMs! < 0) {
      throw ArgumentError.value(this.worstRasterFrameMs, "worstRasterFrameMs", "must be at least 0");
    }
    final definition = switch (this.eventType) {
      "page_open" => (logType: "event", required: const <String>{}, allowed: const <String>{"devicePlatform", "readyMs"}),
      "page_return" => (logType: "event", required: const <String>{"durationMs"}, allowed: const <String>{"devicePlatform", "durationMs"}),
      "page_first_usable" => (logType: "event", required: const <String>{"durationMs", "terminalState"}, allowed: const <String>{"devicePlatform", "durationMs", "failReasonCode", "surfaceId", "terminalState"}),
      "page_error_outcome" => (logType: "event", required: const <String>{"errorCode", "recoveryAction", "result", "surfaceId"}, allowed: const <String>{"action", "devicePlatform", "durationMs", "errorCode", "recoveryAction", "result", "surfaceId"}),
      "app_anr_outcome" => (logType: "event", required: const <String>{"detectionSource", "result"}, allowed: const <String>{"detectionSource", "devicePlatform", "durationMs", "result"}),
      "app_frame_jank_outcome" => (logType: "event", required: const <String>{"jankThresholdMs", "jankyFrames", "result", "sampledFrames", "worstBuildFrameMs", "worstFrameMs", "worstRasterFrameMs"}, allowed: const <String>{"channelId", "devicePlatform", "jankThresholdMs", "jankyFrames", "result", "sampledFrames", "surfaceId", "worstBuildFrameMs", "worstFrameMs", "worstRasterFrameMs"}),
      "home_feed_resource_snapshot" => (logType: "event", required: const <String>{"currentValue", "resourceKind", "result"}, allowed: const <String>{"cacheSizeBytes", "channelId", "currentValue", "devicePlatform", "inflightValue", "limitValue", "queuedValue", "resourceKind", "resourceProfile", "result", "surfaceId"}),
      "home_feed_cache_read_outcome" => (logType: "event", required: const <String>{"cacheClass", "cacheSource", "result"}, allowed: const <String>{"cacheClass", "cacheSource", "channelId", "devicePlatform", "result", "surfaceId"}),
      "app_startup" => (logType: "event", required: const <String>{"hasError", "tClickToContentMs", "tClickToFirstFrameMs", "tFirstFrameToShellMs", "tShellToContentMs"}, allowed: const <String>{"devicePlatform", "hasError", "tClickToContentMs", "tClickToFirstFrameMs", "tFirstFrameToShellMs", "tShellToContentMs"}),
      "runtime_exception" => (logType: "error", required: const <String>{"errorCode"}, allowed: const <String>{"callStack", "devicePlatform", "errorCode", "httpStatus", "operationId"}),
      "product_action" => (logType: "event", required: const <String>{"action", "journey"}, allowed: const <String>{"action", "devicePlatform", "durationMs", "environment", "failReasonCode", "journey", "objectId", "objectType", "reasonId", "recoveryAction", "requestId", "result", "surfaceId", "targetId", "targetType", "traceId"}),
      "login_funnel" => (logType: "event", required: const <String>{"action", "flowId", "result", "step"}, allowed: const <String>{"action", "attemptIndex", "consentState", "countdownBucket", "devicePlatform", "dismissPolicy", "durationMs", "entryMode", "flowId", "fromStep", "motionReduced", "otpPurpose", "provider", "result", "step", "toStep"}),
      "login_operation" => (logType: "event", required: const <String>{"operationId", "result", "surfaceId"}, allowed: const <String>{"attemptIndex", "copyKey", "devicePlatform", "durationMs", "failReasonCode", "failureKind", "feedbackSurface", "flowId", "operationId", "otpPurpose", "provider", "recoveryAction", "requestId", "result", "step", "surfaceId", "traceId"}),
      "chat_interaction_outcome" => (logType: "event", required: const <String>{"chatAction", "chatOutcome"}, allowed: const <String>{"chatAction", "chatOutcome", "chatSource", "devicePlatform", "durationMs", "failReasonCode", "governanceAction", "memberCountBucket", "mentionScope", "recoveryAction", "surfaceId", "unreadCountBucket", "watermarkResult"}),
      "performance_sample" => (logType: "event", required: const <String>{"durationMs", "operationId"}, allowed: const <String>{"devicePlatform", "durationMs", "failReasonCode", "operationId", "recoveryAction", "requestId", "result", "traceId"}),
      "operation_result" => (logType: "event", required: const <String>{"operationId", "result"}, allowed: const <String>{"devicePlatform", "durationMs", "failReasonCode", "hasCache", "operationId", "recoveryAction", "requestId", "result", "surfaceId", "traceId"}),
      "filter_catalog_load" => (logType: "event", required: const <String>{"cacheAgeBucket", "catalogSource", "digestMatch", "releaseIdHash", "result"}, allowed: const <String>{"cacheAgeBucket", "catalogSource", "devicePlatform", "digestMatch", "durationMs", "failReasonCode", "releaseIdHash", "result"}),
      "content_publication" => (logType: "event", required: const <String>{"contentType", "objectState", "publicationStage", "result", "surfaceId"}, allowed: const <String>{"backgroundRetryTerminal", "contentType", "correlationHash", "devicePlatform", "durationMs", "failReasonCode", "objectState", "publicationStage", "recoveryAction", "requestId", "result", "surfaceId", "traceId"}),
      "article_reader_enter" => (logType: "event", required: const <String>{"durationMs", "objectId", "objectType", "result", "surfaceId"}, allowed: const <String>{"devicePlatform", "durationMs", "objectId", "objectType", "result", "surfaceId"}),
      "article_reader_dwell" => (logType: "event", required: const <String>{"durationMs", "objectId", "objectType", "result", "surfaceId"}, allowed: const <String>{"devicePlatform", "durationMs", "objectId", "objectType", "result", "surfaceId"}),
      "article_reader_exit" => (logType: "event", required: const <String>{"durationMs", "objectId", "objectType", "result", "surfaceId"}, allowed: const <String>{"devicePlatform", "durationMs", "objectId", "objectType", "result", "surfaceId"}),
      "article_reader_error" => (logType: "event", required: const <String>{"errorCode", "objectId", "objectType", "recoveryAction", "result", "surfaceId"}, allowed: const <String>{"devicePlatform", "durationMs", "errorCode", "objectId", "objectType", "recoveryAction", "result", "surfaceId"}),
      "article_reader_recovery" => (logType: "event", required: const <String>{"objectId", "objectType", "recoveryAction", "result", "surfaceId"}, allowed: const <String>{"devicePlatform", "durationMs", "errorCode", "objectId", "objectType", "recoveryAction", "result", "surfaceId"}),
      "video_preview_track_load" => (logType: "event", required: const <String>{"result"}, allowed: const <String>{"devicePlatform", "durationMs", "failReasonCode", "result"}),
      "rtc_call_outcome" => (logType: "event", required: const <String>{"callType", "result"}, allowed: const <String>{"callType", "devicePlatform", "durationMs", "failReasonCode", "participantCount", "result"}),
      "rtc_media_qoe" => (logType: "event", required: const <String>{"callType", "connectTimeMs", "mediaConnected", "reconnectCount", "result"}, allowed: const <String>{"callType", "connectTimeMs", "devicePlatform", "disconnectReason", "failReasonCode", "mediaConnected", "networkQuality", "participantCount", "reconnectCount", "result"}),
      "realtime_connect_result" => (logType: "event", required: const <String>{"result", "transport"}, allowed: const <String>{"devicePlatform", "durationMs", "failReasonCode", "result", "transport"}),
      "video_playback_qoe" => (logType: "event", required: const <String>{"devicePlatform", "effectivePlaybackMs", "playbackMode", "readyMs", "rebufferCount", "rebufferMs", "seekCommandMaxMs", "seekCount", "seekEvidenceSource", "seekFailureCount", "seekSettleMaxMs"}, allowed: const <String>{"audioUnderrunCount", "declaredDurationMs", "decoderFallbackEnabled", "decoderQueueMode", "devicePlatform", "droppedFrames", "durationMismatch", "effectivePlaybackMs", "failReasonCode", "observedDurationMs", "playbackMode", "processedVideoFrames", "readyMs", "rebufferCount", "rebufferMs", "rendererMode", "result", "seekCommandMaxMs", "seekCount", "seekEvidenceSource", "seekFailureCount", "seekSettleMaxMs", "ttffMs"}),
      "assistant_turn_quality" => (logType: "event", required: const <String>{"result", "turnAction"}, allowed: const <String>{"devicePlatform", "durationMs", "failReasonCode", "operationId", "result", "turnAction"}),
      "search_query_submit" => (logType: "event", required: const <String>{"requestId", "surfaceId"}, allowed: const <String>{"action", "devicePlatform", "requestId", "surfaceId"}),
      "search_result_impression" => (logType: "event", required: const <String>{"durationMs", "requestId", "resultCount"}, allowed: const <String>{"action", "devicePlatform", "durationMs", "requestId", "resultCount"}),
      "search_result_click" => (logType: "event", required: const <String>{"objectType", "rankPosition", "requestId"}, allowed: const <String>{"action", "devicePlatform", "objectType", "rankPosition", "requestId"}),
      "search_refine" => (logType: "event", required: const <String>{"action", "requestId"}, allowed: const <String>{"action", "devicePlatform", "requestId"}),
      "search_zero_result" => (logType: "event", required: const <String>{"durationMs", "requestId"}, allowed: const <String>{"action", "devicePlatform", "durationMs", "requestId"}),
      "search_result_dwell" => (logType: "event", required: const <String>{"durationMs", "requestId", "resultCount"}, allowed: const <String>{"action", "devicePlatform", "durationMs", "requestId", "resultCount"}),
      _ => throw ArgumentError.value(this.eventType, 'eventType', 'unknown canonical event'),
    };
    if (this.logType != definition.logType) {
      throw ArgumentError.value(this.logType, 'logType', 'does not match eventType');
    }
    final presentExtensions = <String>{
      if (this.action != null) "action",
      if (this.attemptIndex != null) "attemptIndex",
      if (this.audioUnderrunCount != null) "audioUnderrunCount",
      if (this.backgroundRetryTerminal != null) "backgroundRetryTerminal",
      if (this.cacheAgeBucket != null) "cacheAgeBucket",
      if (this.cacheClass != null) "cacheClass",
      if (this.cacheSizeBytes != null) "cacheSizeBytes",
      if (this.cacheSource != null) "cacheSource",
      if (this.callStack != null) "callStack",
      if (this.callType != null) "callType",
      if (this.catalogSource != null) "catalogSource",
      if (this.channelId != null) "channelId",
      if (this.chatAction != null) "chatAction",
      if (this.chatOutcome != null) "chatOutcome",
      if (this.chatSource != null) "chatSource",
      if (this.connectTimeMs != null) "connectTimeMs",
      if (this.consentState != null) "consentState",
      if (this.contentType != null) "contentType",
      if (this.copyKey != null) "copyKey",
      if (this.correlationHash != null) "correlationHash",
      if (this.countdownBucket != null) "countdownBucket",
      if (this.currentValue != null) "currentValue",
      if (this.declaredDurationMs != null) "declaredDurationMs",
      if (this.decoderFallbackEnabled != null) "decoderFallbackEnabled",
      if (this.decoderQueueMode != null) "decoderQueueMode",
      if (this.detectionSource != null) "detectionSource",
      if (this.devicePlatform != null) "devicePlatform",
      if (this.digestMatch != null) "digestMatch",
      if (this.disconnectReason != null) "disconnectReason",
      if (this.dismissPolicy != null) "dismissPolicy",
      if (this.droppedFrames != null) "droppedFrames",
      if (this.durationMismatch != null) "durationMismatch",
      if (this.durationMs != null) "durationMs",
      if (this.effectivePlaybackMs != null) "effectivePlaybackMs",
      if (this.entryMode != null) "entryMode",
      if (this.environment != null) "environment",
      if (this.errorCode != null) "errorCode",
      if (this.failReasonCode != null) "failReasonCode",
      if (this.failureKind != null) "failureKind",
      if (this.feedbackSurface != null) "feedbackSurface",
      if (this.flowId != null) "flowId",
      if (this.fromStep != null) "fromStep",
      if (this.governanceAction != null) "governanceAction",
      if (this.hasCache != null) "hasCache",
      if (this.hasError != null) "hasError",
      if (this.httpStatus != null) "httpStatus",
      if (this.inflightValue != null) "inflightValue",
      if (this.jankThresholdMs != null) "jankThresholdMs",
      if (this.jankyFrames != null) "jankyFrames",
      if (this.journey != null) "journey",
      if (this.limitValue != null) "limitValue",
      if (this.mediaConnected != null) "mediaConnected",
      if (this.memberCountBucket != null) "memberCountBucket",
      if (this.mentionScope != null) "mentionScope",
      if (this.motionReduced != null) "motionReduced",
      if (this.networkQuality != null) "networkQuality",
      if (this.objectId != null) "objectId",
      if (this.objectState != null) "objectState",
      if (this.objectType != null) "objectType",
      if (this.observedDurationMs != null) "observedDurationMs",
      if (this.operationId != null) "operationId",
      if (this.otpPurpose != null) "otpPurpose",
      if (this.participantCount != null) "participantCount",
      if (this.playbackMode != null) "playbackMode",
      if (this.processedVideoFrames != null) "processedVideoFrames",
      if (this.provider != null) "provider",
      if (this.publicationStage != null) "publicationStage",
      if (this.queuedValue != null) "queuedValue",
      if (this.rankPosition != null) "rankPosition",
      if (this.readyMs != null) "readyMs",
      if (this.reasonId != null) "reasonId",
      if (this.rebufferCount != null) "rebufferCount",
      if (this.rebufferMs != null) "rebufferMs",
      if (this.reconnectCount != null) "reconnectCount",
      if (this.recoveryAction != null) "recoveryAction",
      if (this.releaseIdHash != null) "releaseIdHash",
      if (this.rendererMode != null) "rendererMode",
      if (this.requestId != null) "requestId",
      if (this.resourceKind != null) "resourceKind",
      if (this.resourceProfile != null) "resourceProfile",
      if (this.result != null) "result",
      if (this.resultCount != null) "resultCount",
      if (this.sampledFrames != null) "sampledFrames",
      if (this.seekCommandMaxMs != null) "seekCommandMaxMs",
      if (this.seekCount != null) "seekCount",
      if (this.seekEvidenceSource != null) "seekEvidenceSource",
      if (this.seekFailureCount != null) "seekFailureCount",
      if (this.seekSettleMaxMs != null) "seekSettleMaxMs",
      if (this.step != null) "step",
      if (this.surfaceId != null) "surfaceId",
      if (this.tClickToContentMs != null) "tClickToContentMs",
      if (this.tClickToFirstFrameMs != null) "tClickToFirstFrameMs",
      if (this.tFirstFrameToShellMs != null) "tFirstFrameToShellMs",
      if (this.tShellToContentMs != null) "tShellToContentMs",
      if (this.targetId != null) "targetId",
      if (this.targetType != null) "targetType",
      if (this.terminalState != null) "terminalState",
      if (this.toStep != null) "toStep",
      if (this.traceId != null) "traceId",
      if (this.transport != null) "transport",
      if (this.ttffMs != null) "ttffMs",
      if (this.turnAction != null) "turnAction",
      if (this.unreadCountBucket != null) "unreadCountBucket",
      if (this.watermarkResult != null) "watermarkResult",
      if (this.worstBuildFrameMs != null) "worstBuildFrameMs",
      if (this.worstFrameMs != null) "worstFrameMs",
      if (this.worstRasterFrameMs != null) "worstRasterFrameMs",
    };
    if (!definition.required.every(presentExtensions.contains)) {
      throw ArgumentError.value(presentExtensions, 'extensions', 'missing required event extension');
    }
    if (!presentExtensions.every(definition.allowed.contains)) {
      throw ArgumentError.value(presentExtensions, 'extensions', 'event contains forbidden extension');
    }
    if (this.backgroundRetryTerminal != null && !const <String>{"not_applicable", "retry_scheduled", "retry_exhausted", "published", "pending_review", "rejected", "cancelled"}.contains(this.backgroundRetryTerminal)) {
      throw ArgumentError.value(this.backgroundRetryTerminal, "backgroundRetryTerminal", 'unsupported event extension value');
    }
    if (this.cacheAgeBucket != null && !const <String>{"not_applicable", "under_1h", "one_to_24h", "over_24h"}.contains(this.cacheAgeBucket)) {
      throw ArgumentError.value(this.cacheAgeBucket, "cacheAgeBucket", 'unsupported event extension value');
    }
    if (this.cacheSource != null && !const <String>{"memory", "disk", "remote", "seed", "optimistic_overlay", "unknown"}.contains(this.cacheSource)) {
      throw ArgumentError.value(this.cacheSource, "cacheSource", 'unsupported event extension value');
    }
    if (this.callStack?.any((value) => value.length > 256) == true) {
      throw ArgumentError.value(this.callStack, "callStack", 'event extension item is too long');
    }
    if (this.callType != null && !const <String>{"audio", "video"}.contains(this.callType)) {
      throw ArgumentError.value(this.callType, "callType", 'unsupported event extension value');
    }
    if (this.catalogSource != null && !const <String>{"remote", "verified_cache", "bootstrap_replica"}.contains(this.catalogSource)) {
      throw ArgumentError.value(this.catalogSource, "catalogSource", 'unsupported event extension value');
    }
    if (this.chatAction != null && !const <String>{"candidate_source_open", "candidate_source_select", "group_create", "member_add", "mention_select", "mention_send", "read_watermark", "group_governance"}.contains(this.chatAction)) {
      throw ArgumentError.value(this.chatAction, "chatAction", 'unsupported event extension value');
    }
    if (this.chatOutcome != null && !const <String>{"succeeded", "failed", "rejected", "cancelled", "unchanged"}.contains(this.chatOutcome)) {
      throw ArgumentError.value(this.chatOutcome, "chatOutcome", 'unsupported event extension value');
    }
    if (this.chatSource != null && !const <String>{"contacts", "group", "circle", "roster", "composer", "conversation", "settings"}.contains(this.chatSource)) {
      throw ArgumentError.value(this.chatSource, "chatSource", 'unsupported event extension value');
    }
    if (this.contentType != null && !const <String>{"micro", "article", "image", "video", "unknown"}.contains(this.contentType)) {
      throw ArgumentError.value(this.contentType, "contentType", 'unsupported event extension value');
    }
    if (this.decoderQueueMode != null && !const <String>{"synchronous"}.contains(this.decoderQueueMode)) {
      throw ArgumentError.value(this.decoderQueueMode, "decoderQueueMode", 'unsupported event extension value');
    }
    if (this.detectionSource != null && !const <String>{"dart_event_loop_watchdog", "android_application_exit_info", "ios_metric_kit"}.contains(this.detectionSource)) {
      throw ArgumentError.value(this.detectionSource, "detectionSource", 'unsupported event extension value');
    }
    if (this.devicePlatform != null && !const <String>{"android", "ios", "ohos", "web", "desktop"}.contains(this.devicePlatform)) {
      throw ArgumentError.value(this.devicePlatform, "devicePlatform", 'unsupported event extension value');
    }
    if (this.environment != null && !const <String>{"alpha", "beta", "gamma", "prod"}.contains(this.environment)) {
      throw ArgumentError.value(this.environment, "environment", 'unsupported event extension value');
    }
    if (this.governanceAction != null && !const <String>{"none", "announcement_update", "admin_assign", "admin_revoke", "ownership_transfer", "member_remove", "member_leave"}.contains(this.governanceAction)) {
      throw ArgumentError.value(this.governanceAction, "governanceAction", 'unsupported event extension value');
    }
    if (this.memberCountBucket != null && !const <String>{"zero", "one", "two_to_five", "six_to_fifty", "fifty_one_to_five_hundred", "five_hundred_one_to_one_thousand"}.contains(this.memberCountBucket)) {
      throw ArgumentError.value(this.memberCountBucket, "memberCountBucket", 'unsupported event extension value');
    }
    if (this.mentionScope != null && !const <String>{"none", "member", "all", "assistant"}.contains(this.mentionScope)) {
      throw ArgumentError.value(this.mentionScope, "mentionScope", 'unsupported event extension value');
    }
    if (this.networkQuality != null && !const <String>{"excellent", "good", "poor", "unknown"}.contains(this.networkQuality)) {
      throw ArgumentError.value(this.networkQuality, "networkQuality", 'unsupported event extension value');
    }
    if (this.objectState != null && !const <String>{"draft", "submitting", "retry_wait", "pending_review", "blocked", "published", "cancelled"}.contains(this.objectState)) {
      throw ArgumentError.value(this.objectState, "objectState", 'unsupported event extension value');
    }
    if (this.publicationStage != null && !const <String>{"editor_ready", "draft_saved", "draft_restored", "submit_started", "queued", "retry_scheduled", "retry_exhausted", "pending_review", "cancelled", "blocked", "published"}.contains(this.publicationStage)) {
      throw ArgumentError.value(this.publicationStage, "publicationStage", 'unsupported event extension value');
    }
    if (this.rendererMode != null && !const <String>{"platform_view", "texture_view"}.contains(this.rendererMode)) {
      throw ArgumentError.value(this.rendererMode, "rendererMode", 'unsupported event extension value');
    }
    if (this.resourceKind != null && !const <String>{"image_cache_bytes", "active_video_controllers", "media_downloads"}.contains(this.resourceKind)) {
      throw ArgumentError.value(this.resourceKind, "resourceKind", 'unsupported event extension value');
    }
    if (this.resourceProfile != null && !const <String>{"compact", "regular", "expanded"}.contains(this.resourceProfile)) {
      throw ArgumentError.value(this.resourceProfile, "resourceProfile", 'unsupported event extension value');
    }
    if (this.seekEvidenceSource != null && !const <String>{"controller_command_completion", "native_settled", "source_switch_native_settled", "source_switch_position_readback_native_unsupported", "source_switch_native_settle_timeout", "source_switch_settle_unsupported", "source_switch_command_failed", "source_switch_superseded"}.contains(this.seekEvidenceSource)) {
      throw ArgumentError.value(this.seekEvidenceSource, "seekEvidenceSource", 'unsupported event extension value');
    }
    if (this.terminalState != null && !const <String>{"content", "empty", "error"}.contains(this.terminalState)) {
      throw ArgumentError.value(this.terminalState, "terminalState", 'unsupported event extension value');
    }
    if (this.transport != null && !const <String>{"websocket", "long_poll"}.contains(this.transport)) {
      throw ArgumentError.value(this.transport, "transport", 'unsupported event extension value');
    }
    if (this.turnAction != null && !const <String>{"submit", "first_answer", "completed", "failed", "cancelled", "stream_failure"}.contains(this.turnAction)) {
      throw ArgumentError.value(this.turnAction, "turnAction", 'unsupported event extension value');
    }
    if (this.unreadCountBucket != null && !const <String>{"zero", "one", "two_to_five", "six_to_fifty", "fifty_one_to_five_hundred", "five_hundred_one_to_one_thousand"}.contains(this.unreadCountBucket)) {
      throw ArgumentError.value(this.unreadCountBucket, "unreadCountBucket", 'unsupported event extension value');
    }
    if (this.watermarkResult != null && !const <String>{"none", "advanced", "already_current", "rejected", "failed"}.contains(this.watermarkResult)) {
      throw ArgumentError.value(this.watermarkResult, "watermarkResult", 'unsupported event extension value');
    }
  }

  final String logType;
  final String eventType;
  final String sessionId;
  final String pageName;
  final DateTime occurredAt;
  final String deviceManufacturer;
  final String deviceModel;
  final String appVersion;
  final String networkClass;
  final String? action;
  final int? attemptIndex;
  final int? audioUnderrunCount;
  final String? backgroundRetryTerminal;
  final String? cacheAgeBucket;
  final String? cacheClass;
  final int? cacheSizeBytes;
  final String? cacheSource;
  final List<String>? callStack;
  final String? callType;
  final String? catalogSource;
  final String? channelId;
  final String? chatAction;
  final String? chatOutcome;
  final String? chatSource;
  final int? connectTimeMs;
  final String? consentState;
  final String? contentType;
  final String? copyKey;
  final String? correlationHash;
  final String? countdownBucket;
  final int? currentValue;
  final int? declaredDurationMs;
  final bool? decoderFallbackEnabled;
  final String? decoderQueueMode;
  final String? detectionSource;
  final String? devicePlatform;
  final bool? digestMatch;
  final String? disconnectReason;
  final String? dismissPolicy;
  final int? droppedFrames;
  final bool? durationMismatch;
  final int? durationMs;
  final int? effectivePlaybackMs;
  final String? entryMode;
  final String? environment;
  final String? errorCode;
  final String? failReasonCode;
  final String? failureKind;
  final String? feedbackSurface;
  final String? flowId;
  final String? fromStep;
  final String? governanceAction;
  final bool? hasCache;
  final bool? hasError;
  final int? httpStatus;
  final int? inflightValue;
  final int? jankThresholdMs;
  final int? jankyFrames;
  final String? journey;
  final int? limitValue;
  final bool? mediaConnected;
  final String? memberCountBucket;
  final String? mentionScope;
  final bool? motionReduced;
  final String? networkQuality;
  final String? objectId;
  final String? objectState;
  final String? objectType;
  final int? observedDurationMs;
  final String? operationId;
  final String? otpPurpose;
  final int? participantCount;
  final String? playbackMode;
  final int? processedVideoFrames;
  final String? provider;
  final String? publicationStage;
  final int? queuedValue;
  final int? rankPosition;
  final int? readyMs;
  final String? reasonId;
  final int? rebufferCount;
  final int? rebufferMs;
  final int? reconnectCount;
  final String? recoveryAction;
  final String? releaseIdHash;
  final String? rendererMode;
  final String? requestId;
  final String? resourceKind;
  final String? resourceProfile;
  final String? result;
  final int? resultCount;
  final int? sampledFrames;
  final int? seekCommandMaxMs;
  final int? seekCount;
  final String? seekEvidenceSource;
  final int? seekFailureCount;
  final int? seekSettleMaxMs;
  final String? step;
  final String? surfaceId;
  final int? tClickToContentMs;
  final int? tClickToFirstFrameMs;
  final int? tFirstFrameToShellMs;
  final int? tShellToContentMs;
  final String? targetId;
  final String? targetType;
  final String? terminalState;
  final String? toStep;
  final String? traceId;
  final String? transport;
  final int? ttffMs;
  final String? turnAction;
  final String? unreadCountBucket;
  final String? watermarkResult;
  final int? worstBuildFrameMs;
  final int? worstFrameMs;
  final int? worstRasterFrameMs;

  factory EventRecord.fromWire(Map<String, Object?> map, [String path = "EventRecord"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"logType", "eventType", "sessionId", "pageName", "occurredAt", "deviceManufacturer", "deviceModel", "appVersion", "networkClass", "action", "attemptIndex", "audioUnderrunCount", "backgroundRetryTerminal", "cacheAgeBucket", "cacheClass", "cacheSizeBytes", "cacheSource", "callStack", "callType", "catalogSource", "channelId", "chatAction", "chatOutcome", "chatSource", "connectTimeMs", "consentState", "contentType", "copyKey", "correlationHash", "countdownBucket", "currentValue", "declaredDurationMs", "decoderFallbackEnabled", "decoderQueueMode", "detectionSource", "devicePlatform", "digestMatch", "disconnectReason", "dismissPolicy", "droppedFrames", "durationMismatch", "durationMs", "effectivePlaybackMs", "entryMode", "environment", "errorCode", "failReasonCode", "failureKind", "feedbackSurface", "flowId", "fromStep", "governanceAction", "hasCache", "hasError", "httpStatus", "inflightValue", "jankThresholdMs", "jankyFrames", "journey", "limitValue", "mediaConnected", "memberCountBucket", "mentionScope", "motionReduced", "networkQuality", "objectId", "objectState", "objectType", "observedDurationMs", "operationId", "otpPurpose", "participantCount", "playbackMode", "processedVideoFrames", "provider", "publicationStage", "queuedValue", "rankPosition", "readyMs", "reasonId", "rebufferCount", "rebufferMs", "reconnectCount", "recoveryAction", "releaseIdHash", "rendererMode", "requestId", "resourceKind", "resourceProfile", "result", "resultCount", "sampledFrames", "seekCommandMaxMs", "seekCount", "seekEvidenceSource", "seekFailureCount", "seekSettleMaxMs", "step", "surfaceId", "tClickToContentMs", "tClickToFirstFrameMs", "tFirstFrameToShellMs", "tShellToContentMs", "targetId", "targetType", "terminalState", "toStep", "traceId", "transport", "ttffMs", "turnAction", "unreadCountBucket", "watermarkResult", "worstBuildFrameMs", "worstFrameMs", "worstRasterFrameMs"}, path);
    return EventRecord(
      logType: _generatedRequestString(map["logType"], '$path.logType'),
      eventType: _generatedRequestString(map["eventType"], '$path.eventType'),
      sessionId: _generatedRequestString(map["sessionId"], '$path.sessionId'),
      pageName: _generatedRequestString(map["pageName"], '$path.pageName'),
      occurredAt: _generatedRequestTimestamp(map["occurredAt"], '$path.occurredAt'),
      deviceManufacturer: _generatedRequestString(map["deviceManufacturer"], '$path.deviceManufacturer'),
      deviceModel: _generatedRequestString(map["deviceModel"], '$path.deviceModel'),
      appVersion: _generatedRequestString(map["appVersion"], '$path.appVersion'),
      networkClass: _generatedRequestString(map["networkClass"], '$path.networkClass'),
      action: map["action"] == null ? null : _generatedRequestString(map["action"], '$path.action'),
      attemptIndex: map["attemptIndex"] == null ? null : _generatedRequestInt(map["attemptIndex"], '$path.attemptIndex'),
      audioUnderrunCount: map["audioUnderrunCount"] == null ? null : _generatedRequestInt(map["audioUnderrunCount"], '$path.audioUnderrunCount'),
      backgroundRetryTerminal: map["backgroundRetryTerminal"] == null ? null : _generatedRequestString(map["backgroundRetryTerminal"], '$path.backgroundRetryTerminal'),
      cacheAgeBucket: map["cacheAgeBucket"] == null ? null : _generatedRequestString(map["cacheAgeBucket"], '$path.cacheAgeBucket'),
      cacheClass: map["cacheClass"] == null ? null : _generatedRequestString(map["cacheClass"], '$path.cacheClass'),
      cacheSizeBytes: map["cacheSizeBytes"] == null ? null : _generatedRequestInt(map["cacheSizeBytes"], '$path.cacheSizeBytes'),
      cacheSource: map["cacheSource"] == null ? null : _generatedRequestString(map["cacheSource"], '$path.cacheSource'),
      callStack: map["callStack"] == null ? null : List<String>.unmodifiable(_generatedRequestList(map["callStack"], '$path.callStack').asMap().entries.map((entry) => _generatedRequestString(entry.value, '$path.callStack' + '[${entry.key}]'))),
      callType: map["callType"] == null ? null : _generatedRequestString(map["callType"], '$path.callType'),
      catalogSource: map["catalogSource"] == null ? null : _generatedRequestString(map["catalogSource"], '$path.catalogSource'),
      channelId: map["channelId"] == null ? null : _generatedRequestString(map["channelId"], '$path.channelId'),
      chatAction: map["chatAction"] == null ? null : _generatedRequestString(map["chatAction"], '$path.chatAction'),
      chatOutcome: map["chatOutcome"] == null ? null : _generatedRequestString(map["chatOutcome"], '$path.chatOutcome'),
      chatSource: map["chatSource"] == null ? null : _generatedRequestString(map["chatSource"], '$path.chatSource'),
      connectTimeMs: map["connectTimeMs"] == null ? null : _generatedRequestInt(map["connectTimeMs"], '$path.connectTimeMs'),
      consentState: map["consentState"] == null ? null : _generatedRequestString(map["consentState"], '$path.consentState'),
      contentType: map["contentType"] == null ? null : _generatedRequestString(map["contentType"], '$path.contentType'),
      copyKey: map["copyKey"] == null ? null : _generatedRequestString(map["copyKey"], '$path.copyKey'),
      correlationHash: map["correlationHash"] == null ? null : _generatedRequestString(map["correlationHash"], '$path.correlationHash'),
      countdownBucket: map["countdownBucket"] == null ? null : _generatedRequestString(map["countdownBucket"], '$path.countdownBucket'),
      currentValue: map["currentValue"] == null ? null : _generatedRequestInt(map["currentValue"], '$path.currentValue'),
      declaredDurationMs: map["declaredDurationMs"] == null ? null : _generatedRequestInt(map["declaredDurationMs"], '$path.declaredDurationMs'),
      decoderFallbackEnabled: map["decoderFallbackEnabled"] == null ? null : _generatedRequestBool(map["decoderFallbackEnabled"], '$path.decoderFallbackEnabled'),
      decoderQueueMode: map["decoderQueueMode"] == null ? null : _generatedRequestString(map["decoderQueueMode"], '$path.decoderQueueMode'),
      detectionSource: map["detectionSource"] == null ? null : _generatedRequestString(map["detectionSource"], '$path.detectionSource'),
      devicePlatform: map["devicePlatform"] == null ? null : _generatedRequestString(map["devicePlatform"], '$path.devicePlatform'),
      digestMatch: map["digestMatch"] == null ? null : _generatedRequestBool(map["digestMatch"], '$path.digestMatch'),
      disconnectReason: map["disconnectReason"] == null ? null : _generatedRequestString(map["disconnectReason"], '$path.disconnectReason'),
      dismissPolicy: map["dismissPolicy"] == null ? null : _generatedRequestString(map["dismissPolicy"], '$path.dismissPolicy'),
      droppedFrames: map["droppedFrames"] == null ? null : _generatedRequestInt(map["droppedFrames"], '$path.droppedFrames'),
      durationMismatch: map["durationMismatch"] == null ? null : _generatedRequestBool(map["durationMismatch"], '$path.durationMismatch'),
      durationMs: map["durationMs"] == null ? null : _generatedRequestInt(map["durationMs"], '$path.durationMs'),
      effectivePlaybackMs: map["effectivePlaybackMs"] == null ? null : _generatedRequestInt(map["effectivePlaybackMs"], '$path.effectivePlaybackMs'),
      entryMode: map["entryMode"] == null ? null : _generatedRequestString(map["entryMode"], '$path.entryMode'),
      environment: map["environment"] == null ? null : _generatedRequestString(map["environment"], '$path.environment'),
      errorCode: map["errorCode"] == null ? null : _generatedRequestString(map["errorCode"], '$path.errorCode'),
      failReasonCode: map["failReasonCode"] == null ? null : _generatedRequestString(map["failReasonCode"], '$path.failReasonCode'),
      failureKind: map["failureKind"] == null ? null : _generatedRequestString(map["failureKind"], '$path.failureKind'),
      feedbackSurface: map["feedbackSurface"] == null ? null : _generatedRequestString(map["feedbackSurface"], '$path.feedbackSurface'),
      flowId: map["flowId"] == null ? null : _generatedRequestString(map["flowId"], '$path.flowId'),
      fromStep: map["fromStep"] == null ? null : _generatedRequestString(map["fromStep"], '$path.fromStep'),
      governanceAction: map["governanceAction"] == null ? null : _generatedRequestString(map["governanceAction"], '$path.governanceAction'),
      hasCache: map["hasCache"] == null ? null : _generatedRequestBool(map["hasCache"], '$path.hasCache'),
      hasError: map["hasError"] == null ? null : _generatedRequestBool(map["hasError"], '$path.hasError'),
      httpStatus: map["httpStatus"] == null ? null : _generatedRequestInt(map["httpStatus"], '$path.httpStatus'),
      inflightValue: map["inflightValue"] == null ? null : _generatedRequestInt(map["inflightValue"], '$path.inflightValue'),
      jankThresholdMs: map["jankThresholdMs"] == null ? null : _generatedRequestInt(map["jankThresholdMs"], '$path.jankThresholdMs'),
      jankyFrames: map["jankyFrames"] == null ? null : _generatedRequestInt(map["jankyFrames"], '$path.jankyFrames'),
      journey: map["journey"] == null ? null : _generatedRequestString(map["journey"], '$path.journey'),
      limitValue: map["limitValue"] == null ? null : _generatedRequestInt(map["limitValue"], '$path.limitValue'),
      mediaConnected: map["mediaConnected"] == null ? null : _generatedRequestBool(map["mediaConnected"], '$path.mediaConnected'),
      memberCountBucket: map["memberCountBucket"] == null ? null : _generatedRequestString(map["memberCountBucket"], '$path.memberCountBucket'),
      mentionScope: map["mentionScope"] == null ? null : _generatedRequestString(map["mentionScope"], '$path.mentionScope'),
      motionReduced: map["motionReduced"] == null ? null : _generatedRequestBool(map["motionReduced"], '$path.motionReduced'),
      networkQuality: map["networkQuality"] == null ? null : _generatedRequestString(map["networkQuality"], '$path.networkQuality'),
      objectId: map["objectId"] == null ? null : _generatedRequestString(map["objectId"], '$path.objectId'),
      objectState: map["objectState"] == null ? null : _generatedRequestString(map["objectState"], '$path.objectState'),
      objectType: map["objectType"] == null ? null : _generatedRequestString(map["objectType"], '$path.objectType'),
      observedDurationMs: map["observedDurationMs"] == null ? null : _generatedRequestInt(map["observedDurationMs"], '$path.observedDurationMs'),
      operationId: map["operationId"] == null ? null : _generatedRequestString(map["operationId"], '$path.operationId'),
      otpPurpose: map["otpPurpose"] == null ? null : _generatedRequestString(map["otpPurpose"], '$path.otpPurpose'),
      participantCount: map["participantCount"] == null ? null : _generatedRequestInt(map["participantCount"], '$path.participantCount'),
      playbackMode: map["playbackMode"] == null ? null : _generatedRequestString(map["playbackMode"], '$path.playbackMode'),
      processedVideoFrames: map["processedVideoFrames"] == null ? null : _generatedRequestInt(map["processedVideoFrames"], '$path.processedVideoFrames'),
      provider: map["provider"] == null ? null : _generatedRequestString(map["provider"], '$path.provider'),
      publicationStage: map["publicationStage"] == null ? null : _generatedRequestString(map["publicationStage"], '$path.publicationStage'),
      queuedValue: map["queuedValue"] == null ? null : _generatedRequestInt(map["queuedValue"], '$path.queuedValue'),
      rankPosition: map["rankPosition"] == null ? null : _generatedRequestInt(map["rankPosition"], '$path.rankPosition'),
      readyMs: map["readyMs"] == null ? null : _generatedRequestInt(map["readyMs"], '$path.readyMs'),
      reasonId: map["reasonId"] == null ? null : _generatedRequestString(map["reasonId"], '$path.reasonId'),
      rebufferCount: map["rebufferCount"] == null ? null : _generatedRequestInt(map["rebufferCount"], '$path.rebufferCount'),
      rebufferMs: map["rebufferMs"] == null ? null : _generatedRequestInt(map["rebufferMs"], '$path.rebufferMs'),
      reconnectCount: map["reconnectCount"] == null ? null : _generatedRequestInt(map["reconnectCount"], '$path.reconnectCount'),
      recoveryAction: map["recoveryAction"] == null ? null : _generatedRequestString(map["recoveryAction"], '$path.recoveryAction'),
      releaseIdHash: map["releaseIdHash"] == null ? null : _generatedRequestString(map["releaseIdHash"], '$path.releaseIdHash'),
      rendererMode: map["rendererMode"] == null ? null : _generatedRequestString(map["rendererMode"], '$path.rendererMode'),
      requestId: map["requestId"] == null ? null : _generatedRequestString(map["requestId"], '$path.requestId'),
      resourceKind: map["resourceKind"] == null ? null : _generatedRequestString(map["resourceKind"], '$path.resourceKind'),
      resourceProfile: map["resourceProfile"] == null ? null : _generatedRequestString(map["resourceProfile"], '$path.resourceProfile'),
      result: map["result"] == null ? null : _generatedRequestString(map["result"], '$path.result'),
      resultCount: map["resultCount"] == null ? null : _generatedRequestInt(map["resultCount"], '$path.resultCount'),
      sampledFrames: map["sampledFrames"] == null ? null : _generatedRequestInt(map["sampledFrames"], '$path.sampledFrames'),
      seekCommandMaxMs: map["seekCommandMaxMs"] == null ? null : _generatedRequestInt(map["seekCommandMaxMs"], '$path.seekCommandMaxMs'),
      seekCount: map["seekCount"] == null ? null : _generatedRequestInt(map["seekCount"], '$path.seekCount'),
      seekEvidenceSource: map["seekEvidenceSource"] == null ? null : _generatedRequestString(map["seekEvidenceSource"], '$path.seekEvidenceSource'),
      seekFailureCount: map["seekFailureCount"] == null ? null : _generatedRequestInt(map["seekFailureCount"], '$path.seekFailureCount'),
      seekSettleMaxMs: map["seekSettleMaxMs"] == null ? null : _generatedRequestInt(map["seekSettleMaxMs"], '$path.seekSettleMaxMs'),
      step: map["step"] == null ? null : _generatedRequestString(map["step"], '$path.step'),
      surfaceId: map["surfaceId"] == null ? null : _generatedRequestString(map["surfaceId"], '$path.surfaceId'),
      tClickToContentMs: map["tClickToContentMs"] == null ? null : _generatedRequestInt(map["tClickToContentMs"], '$path.tClickToContentMs'),
      tClickToFirstFrameMs: map["tClickToFirstFrameMs"] == null ? null : _generatedRequestInt(map["tClickToFirstFrameMs"], '$path.tClickToFirstFrameMs'),
      tFirstFrameToShellMs: map["tFirstFrameToShellMs"] == null ? null : _generatedRequestInt(map["tFirstFrameToShellMs"], '$path.tFirstFrameToShellMs'),
      tShellToContentMs: map["tShellToContentMs"] == null ? null : _generatedRequestInt(map["tShellToContentMs"], '$path.tShellToContentMs'),
      targetId: map["targetId"] == null ? null : _generatedRequestString(map["targetId"], '$path.targetId'),
      targetType: map["targetType"] == null ? null : _generatedRequestString(map["targetType"], '$path.targetType'),
      terminalState: map["terminalState"] == null ? null : _generatedRequestString(map["terminalState"], '$path.terminalState'),
      toStep: map["toStep"] == null ? null : _generatedRequestString(map["toStep"], '$path.toStep'),
      traceId: map["traceId"] == null ? null : _generatedRequestString(map["traceId"], '$path.traceId'),
      transport: map["transport"] == null ? null : _generatedRequestString(map["transport"], '$path.transport'),
      ttffMs: map["ttffMs"] == null ? null : _generatedRequestInt(map["ttffMs"], '$path.ttffMs'),
      turnAction: map["turnAction"] == null ? null : _generatedRequestString(map["turnAction"], '$path.turnAction'),
      unreadCountBucket: map["unreadCountBucket"] == null ? null : _generatedRequestString(map["unreadCountBucket"], '$path.unreadCountBucket'),
      watermarkResult: map["watermarkResult"] == null ? null : _generatedRequestString(map["watermarkResult"], '$path.watermarkResult'),
      worstBuildFrameMs: map["worstBuildFrameMs"] == null ? null : _generatedRequestInt(map["worstBuildFrameMs"], '$path.worstBuildFrameMs'),
      worstFrameMs: map["worstFrameMs"] == null ? null : _generatedRequestInt(map["worstFrameMs"], '$path.worstFrameMs'),
      worstRasterFrameMs: map["worstRasterFrameMs"] == null ? null : _generatedRequestInt(map["worstRasterFrameMs"], '$path.worstRasterFrameMs'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "logType": this.logType,
    "eventType": this.eventType,
    "sessionId": this.sessionId,
    "pageName": this.pageName,
    "occurredAt": this.occurredAt.toUtc().toIso8601String(),
    "deviceManufacturer": this.deviceManufacturer,
    "deviceModel": this.deviceModel,
    "appVersion": this.appVersion,
    "networkClass": this.networkClass,
    if (this.action != null) "action": this.action!,
    if (this.attemptIndex != null) "attemptIndex": this.attemptIndex!,
    if (this.audioUnderrunCount != null) "audioUnderrunCount": this.audioUnderrunCount!,
    if (this.backgroundRetryTerminal != null) "backgroundRetryTerminal": this.backgroundRetryTerminal!,
    if (this.cacheAgeBucket != null) "cacheAgeBucket": this.cacheAgeBucket!,
    if (this.cacheClass != null) "cacheClass": this.cacheClass!,
    if (this.cacheSizeBytes != null) "cacheSizeBytes": this.cacheSizeBytes!,
    if (this.cacheSource != null) "cacheSource": this.cacheSource!,
    if (this.callStack != null) "callStack": this.callStack!.map((value) => value).toList(growable: false),
    if (this.callType != null) "callType": this.callType!,
    if (this.catalogSource != null) "catalogSource": this.catalogSource!,
    if (this.channelId != null) "channelId": this.channelId!,
    if (this.chatAction != null) "chatAction": this.chatAction!,
    if (this.chatOutcome != null) "chatOutcome": this.chatOutcome!,
    if (this.chatSource != null) "chatSource": this.chatSource!,
    if (this.connectTimeMs != null) "connectTimeMs": this.connectTimeMs!,
    if (this.consentState != null) "consentState": this.consentState!,
    if (this.contentType != null) "contentType": this.contentType!,
    if (this.copyKey != null) "copyKey": this.copyKey!,
    if (this.correlationHash != null) "correlationHash": this.correlationHash!,
    if (this.countdownBucket != null) "countdownBucket": this.countdownBucket!,
    if (this.currentValue != null) "currentValue": this.currentValue!,
    if (this.declaredDurationMs != null) "declaredDurationMs": this.declaredDurationMs!,
    if (this.decoderFallbackEnabled != null) "decoderFallbackEnabled": this.decoderFallbackEnabled!,
    if (this.decoderQueueMode != null) "decoderQueueMode": this.decoderQueueMode!,
    if (this.detectionSource != null) "detectionSource": this.detectionSource!,
    if (this.devicePlatform != null) "devicePlatform": this.devicePlatform!,
    if (this.digestMatch != null) "digestMatch": this.digestMatch!,
    if (this.disconnectReason != null) "disconnectReason": this.disconnectReason!,
    if (this.dismissPolicy != null) "dismissPolicy": this.dismissPolicy!,
    if (this.droppedFrames != null) "droppedFrames": this.droppedFrames!,
    if (this.durationMismatch != null) "durationMismatch": this.durationMismatch!,
    if (this.durationMs != null) "durationMs": this.durationMs!,
    if (this.effectivePlaybackMs != null) "effectivePlaybackMs": this.effectivePlaybackMs!,
    if (this.entryMode != null) "entryMode": this.entryMode!,
    if (this.environment != null) "environment": this.environment!,
    if (this.errorCode != null) "errorCode": this.errorCode!,
    if (this.failReasonCode != null) "failReasonCode": this.failReasonCode!,
    if (this.failureKind != null) "failureKind": this.failureKind!,
    if (this.feedbackSurface != null) "feedbackSurface": this.feedbackSurface!,
    if (this.flowId != null) "flowId": this.flowId!,
    if (this.fromStep != null) "fromStep": this.fromStep!,
    if (this.governanceAction != null) "governanceAction": this.governanceAction!,
    if (this.hasCache != null) "hasCache": this.hasCache!,
    if (this.hasError != null) "hasError": this.hasError!,
    if (this.httpStatus != null) "httpStatus": this.httpStatus!,
    if (this.inflightValue != null) "inflightValue": this.inflightValue!,
    if (this.jankThresholdMs != null) "jankThresholdMs": this.jankThresholdMs!,
    if (this.jankyFrames != null) "jankyFrames": this.jankyFrames!,
    if (this.journey != null) "journey": this.journey!,
    if (this.limitValue != null) "limitValue": this.limitValue!,
    if (this.mediaConnected != null) "mediaConnected": this.mediaConnected!,
    if (this.memberCountBucket != null) "memberCountBucket": this.memberCountBucket!,
    if (this.mentionScope != null) "mentionScope": this.mentionScope!,
    if (this.motionReduced != null) "motionReduced": this.motionReduced!,
    if (this.networkQuality != null) "networkQuality": this.networkQuality!,
    if (this.objectId != null) "objectId": this.objectId!,
    if (this.objectState != null) "objectState": this.objectState!,
    if (this.objectType != null) "objectType": this.objectType!,
    if (this.observedDurationMs != null) "observedDurationMs": this.observedDurationMs!,
    if (this.operationId != null) "operationId": this.operationId!,
    if (this.otpPurpose != null) "otpPurpose": this.otpPurpose!,
    if (this.participantCount != null) "participantCount": this.participantCount!,
    if (this.playbackMode != null) "playbackMode": this.playbackMode!,
    if (this.processedVideoFrames != null) "processedVideoFrames": this.processedVideoFrames!,
    if (this.provider != null) "provider": this.provider!,
    if (this.publicationStage != null) "publicationStage": this.publicationStage!,
    if (this.queuedValue != null) "queuedValue": this.queuedValue!,
    if (this.rankPosition != null) "rankPosition": this.rankPosition!,
    if (this.readyMs != null) "readyMs": this.readyMs!,
    if (this.reasonId != null) "reasonId": this.reasonId!,
    if (this.rebufferCount != null) "rebufferCount": this.rebufferCount!,
    if (this.rebufferMs != null) "rebufferMs": this.rebufferMs!,
    if (this.reconnectCount != null) "reconnectCount": this.reconnectCount!,
    if (this.recoveryAction != null) "recoveryAction": this.recoveryAction!,
    if (this.releaseIdHash != null) "releaseIdHash": this.releaseIdHash!,
    if (this.rendererMode != null) "rendererMode": this.rendererMode!,
    if (this.requestId != null) "requestId": this.requestId!,
    if (this.resourceKind != null) "resourceKind": this.resourceKind!,
    if (this.resourceProfile != null) "resourceProfile": this.resourceProfile!,
    if (this.result != null) "result": this.result!,
    if (this.resultCount != null) "resultCount": this.resultCount!,
    if (this.sampledFrames != null) "sampledFrames": this.sampledFrames!,
    if (this.seekCommandMaxMs != null) "seekCommandMaxMs": this.seekCommandMaxMs!,
    if (this.seekCount != null) "seekCount": this.seekCount!,
    if (this.seekEvidenceSource != null) "seekEvidenceSource": this.seekEvidenceSource!,
    if (this.seekFailureCount != null) "seekFailureCount": this.seekFailureCount!,
    if (this.seekSettleMaxMs != null) "seekSettleMaxMs": this.seekSettleMaxMs!,
    if (this.step != null) "step": this.step!,
    if (this.surfaceId != null) "surfaceId": this.surfaceId!,
    if (this.tClickToContentMs != null) "tClickToContentMs": this.tClickToContentMs!,
    if (this.tClickToFirstFrameMs != null) "tClickToFirstFrameMs": this.tClickToFirstFrameMs!,
    if (this.tFirstFrameToShellMs != null) "tFirstFrameToShellMs": this.tFirstFrameToShellMs!,
    if (this.tShellToContentMs != null) "tShellToContentMs": this.tShellToContentMs!,
    if (this.targetId != null) "targetId": this.targetId!,
    if (this.targetType != null) "targetType": this.targetType!,
    if (this.terminalState != null) "terminalState": this.terminalState!,
    if (this.toStep != null) "toStep": this.toStep!,
    if (this.traceId != null) "traceId": this.traceId!,
    if (this.transport != null) "transport": this.transport!,
    if (this.ttffMs != null) "ttffMs": this.ttffMs!,
    if (this.turnAction != null) "turnAction": this.turnAction!,
    if (this.unreadCountBucket != null) "unreadCountBucket": this.unreadCountBucket!,
    if (this.watermarkResult != null) "watermarkResult": this.watermarkResult!,
    if (this.worstBuildFrameMs != null) "worstBuildFrameMs": this.worstBuildFrameMs!,
    if (this.worstFrameMs != null) "worstFrameMs": this.worstFrameMs!,
    if (this.worstRasterFrameMs != null) "worstRasterFrameMs": this.worstRasterFrameMs!,
  };
}

final class EventRecordBatchRequest {
  EventRecordBatchRequest({
    required List<EventRecord> events,
  }) : events = List.unmodifiable(events) {
    if (this.events.length < 1) {
      throw ArgumentError.value(this.events, "events", "item count is below 1");
    }
  }

  final List<EventRecord> events;

  factory EventRecordBatchRequest.fromWire(Map<String, Object?> map, [String path = "EventRecordBatchRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"events"}, path);
    return EventRecordBatchRequest(
      events: List<EventRecord>.unmodifiable(_generatedRequestList(map["events"], '$path.events').asMap().entries.map((entry) => EventRecord.fromWire(_generatedRequestObject(entry.value, '$path.events' + '[${entry.key}]'), '$path.events' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "events": this.events.map((value) => value.toWire()).toList(growable: false),
  };
}

final class GetAppRecoveryVersionQuery {
  GetAppRecoveryVersionQuery({
    required String platform,
    required String appVersion,
    required int buildNumber,
  }) : platform = platform,
       appVersion = appVersion,
       buildNumber = buildNumber {
    if (this.appVersion.isEmpty) {
      throw ArgumentError.value(this.appVersion, "appVersion", 'must not be blank');
    }
    if (this.buildNumber <= 0) {
      throw ArgumentError.value(this.buildNumber, "buildNumber", "must be positive");
    }
  }

  final String platform;
  final String appVersion;
  final int buildNumber;

  factory GetAppRecoveryVersionQuery.fromWire(Map<String, Object?> map, [String path = "GetAppRecoveryVersionQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"platform", "appVersion", "buildNumber"}, path);
    return GetAppRecoveryVersionQuery(
      platform: _generatedRequestString(map["platform"], '$path.platform'),
      appVersion: _generatedRequestString(map["appVersion"], '$path.appVersion'),
      buildNumber: _generatedRequestInt(map["buildNumber"], '$path.buildNumber'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "platform": this.platform,
    "appVersion": this.appVersion,
    "buildNumber": this.buildNumber,
  };
}

final class RecordVisitRequest {
  RecordVisitRequest({
    required VisitTargetType targetType,
    required String targetKey,
  }) : targetType = targetType,
       targetKey = targetKey {
    if (this.targetKey.isEmpty) {
      throw ArgumentError.value(this.targetKey, "targetKey", 'must not be blank');
    }
    if (this.targetKey.length > 256) {
      throw ArgumentError.value(this.targetKey, "targetKey", "length exceeds 256");
    }
  }

  final VisitTargetType targetType;
  final String targetKey;

  factory RecordVisitRequest.fromWire(Map<String, Object?> map, [String path = "RecordVisitRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"targetType", "targetKey"}, path);
    return RecordVisitRequest(
      targetType: switch (map["targetType"]) { "page" => VisitTargetType.page, "post" => VisitTargetType.post, "circle" => VisitTargetType.circle, "user" => VisitTargetType.user, _ => throw FormatException('$path.targetType' + ' has an invalid enum value'), },
      targetKey: _generatedRequestString(map["targetKey"], '$path.targetKey'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "targetType": this.targetType.wireName,
    "targetKey": this.targetKey,
  };
}

final class ReportRecoveryFailureRequest {
  ReportRecoveryFailureRequest({
    required DateTime occurredAt,
    required String appVersion,
    required String buildNumber,
    required String platform,
    required String osVersion,
    required String deviceModel,
    required String errorSource,
    required String errorType,
    required String errorMessage,
    required String stackTrace,
  }) : occurredAt = occurredAt,
       appVersion = appVersion,
       buildNumber = buildNumber,
       platform = platform,
       osVersion = osVersion,
       deviceModel = deviceModel,
       errorSource = errorSource,
       errorType = errorType,
       errorMessage = errorMessage,
       stackTrace = stackTrace {
    if (this.appVersion.isEmpty) {
      throw ArgumentError.value(this.appVersion, "appVersion", 'must not be blank');
    }
    if (this.buildNumber.isEmpty) {
      throw ArgumentError.value(this.buildNumber, "buildNumber", 'must not be blank');
    }
    if (this.osVersion.isEmpty) {
      throw ArgumentError.value(this.osVersion, "osVersion", 'must not be blank');
    }
    if (this.deviceModel.isEmpty) {
      throw ArgumentError.value(this.deviceModel, "deviceModel", 'must not be blank');
    }
    if (this.errorSource.isEmpty) {
      throw ArgumentError.value(this.errorSource, "errorSource", 'must not be blank');
    }
    if (this.errorType.isEmpty) {
      throw ArgumentError.value(this.errorType, "errorType", 'must not be blank');
    }
    if (this.errorMessage.isEmpty) {
      throw ArgumentError.value(this.errorMessage, "errorMessage", 'must not be blank');
    }
    if (this.stackTrace.isEmpty) {
      throw ArgumentError.value(this.stackTrace, "stackTrace", 'must not be blank');
    }
  }

  final DateTime occurredAt;
  final String appVersion;
  final String buildNumber;
  final String platform;
  final String osVersion;
  final String deviceModel;
  final String errorSource;
  final String errorType;
  final String errorMessage;
  final String stackTrace;

  factory ReportRecoveryFailureRequest.fromWire(Map<String, Object?> map, [String path = "ReportRecoveryFailureRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"occurredAt", "appVersion", "buildNumber", "platform", "osVersion", "deviceModel", "errorSource", "errorType", "errorMessage", "stackTrace"}, path);
    return ReportRecoveryFailureRequest(
      occurredAt: _generatedRequestTimestamp(map["occurredAt"], '$path.occurredAt'),
      appVersion: _generatedRequestString(map["appVersion"], '$path.appVersion'),
      buildNumber: _generatedRequestString(map["buildNumber"], '$path.buildNumber'),
      platform: _generatedRequestString(map["platform"], '$path.platform'),
      osVersion: _generatedRequestString(map["osVersion"], '$path.osVersion'),
      deviceModel: _generatedRequestString(map["deviceModel"], '$path.deviceModel'),
      errorSource: _generatedRequestString(map["errorSource"], '$path.errorSource'),
      errorType: _generatedRequestString(map["errorType"], '$path.errorType'),
      errorMessage: _generatedRequestString(map["errorMessage"], '$path.errorMessage'),
      stackTrace: _generatedRequestString(map["stackTrace"], '$path.stackTrace'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "occurredAt": this.occurredAt.toUtc().toIso8601String(),
    "appVersion": this.appVersion,
    "buildNumber": this.buildNumber,
    "platform": this.platform,
    "osVersion": this.osVersion,
    "deviceModel": this.deviceModel,
    "errorSource": this.errorSource,
    "errorType": this.errorType,
    "errorMessage": this.errorMessage,
    "stackTrace": this.stackTrace,
  };
}

final class ReportStartupEventBatchCommand {
  ReportStartupEventBatchCommand({
    required String proof,
    required List<StartupTelemetryEventWire> events,
  }) : proof = proof,
       events = List.unmodifiable(events) {
    if (this.proof.isEmpty) {
      throw ArgumentError.value(this.proof, "proof", 'must not be blank');
    }
    if (this.events.length < 1) {
      throw ArgumentError.value(this.events, "events", "item count is below 1");
    }
  }

  final String proof;
  final List<StartupTelemetryEventWire> events;

  factory ReportStartupEventBatchCommand.fromWire(Map<String, Object?> map, [String path = "ReportStartupEventBatchCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"proof", "events"}, path);
    return ReportStartupEventBatchCommand(
      proof: _generatedRequestString(map["proof"], '$path.proof'),
      events: List<StartupTelemetryEventWire>.unmodifiable(_generatedRequestList(map["events"], '$path.events').asMap().entries.map((entry) => StartupTelemetryEventWire.fromWire(_generatedRequestObject(entry.value, '$path.events' + '[${entry.key}]'), '$path.events' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "proof": this.proof,
    "events": this.events.map((value) => value.toWire()).toList(growable: false),
  };
}

final class RuntimeLogAttributesWire {
  RuntimeLogAttributesWire({
    String? anrThresholdMs,
    String? artifactCount,
    String? decoderFallbackEnabled,
    String? decoderQueueMode,
    String? droppedFrames,
    String? exceptionType,
    String? failurePoint,
    String? gate,
    String? inputKv,
    String? jankThresholdMs,
    String? jankyFrames,
    String? kind,
    String? module,
    String? outcome,
    String? outputKv,
    String? processedFrames,
    String? reason,
    String? rendererMode,
    String? sampledFrames,
    String? settleMs,
    String? settledPositionMs,
    String? source,
    String? stackFrameCount,
    String? stage,
    String? stallMs,
    String? targetPositionMs,
    String? ttffMs,
    String? worstBuildFrameMs,
    String? worstFrameMs,
    String? worstRasterFrameMs,
  }) : anrThresholdMs = anrThresholdMs,
       artifactCount = artifactCount,
       decoderFallbackEnabled = decoderFallbackEnabled,
       decoderQueueMode = decoderQueueMode,
       droppedFrames = droppedFrames,
       exceptionType = exceptionType,
       failurePoint = failurePoint,
       gate = gate,
       inputKv = inputKv,
       jankThresholdMs = jankThresholdMs,
       jankyFrames = jankyFrames,
       kind = kind,
       module = module,
       outcome = outcome,
       outputKv = outputKv,
       processedFrames = processedFrames,
       reason = reason,
       rendererMode = rendererMode,
       sampledFrames = sampledFrames,
       settleMs = settleMs,
       settledPositionMs = settledPositionMs,
       source = source,
       stackFrameCount = stackFrameCount,
       stage = stage,
       stallMs = stallMs,
       targetPositionMs = targetPositionMs,
       ttffMs = ttffMs,
       worstBuildFrameMs = worstBuildFrameMs,
       worstFrameMs = worstFrameMs,
       worstRasterFrameMs = worstRasterFrameMs {
    if (this.anrThresholdMs != null && this.anrThresholdMs!.length > 512) {
      throw ArgumentError.value(this.anrThresholdMs, "anrThresholdMs", "length exceeds 512");
    }
    if (this.artifactCount != null && this.artifactCount!.length > 512) {
      throw ArgumentError.value(this.artifactCount, "artifactCount", "length exceeds 512");
    }
    if (this.decoderFallbackEnabled != null && this.decoderFallbackEnabled!.length > 512) {
      throw ArgumentError.value(this.decoderFallbackEnabled, "decoderFallbackEnabled", "length exceeds 512");
    }
    if (this.decoderQueueMode != null && this.decoderQueueMode!.length > 512) {
      throw ArgumentError.value(this.decoderQueueMode, "decoderQueueMode", "length exceeds 512");
    }
    if (this.droppedFrames != null && this.droppedFrames!.length > 512) {
      throw ArgumentError.value(this.droppedFrames, "droppedFrames", "length exceeds 512");
    }
    if (this.exceptionType != null && this.exceptionType!.length > 512) {
      throw ArgumentError.value(this.exceptionType, "exceptionType", "length exceeds 512");
    }
    if (this.failurePoint != null && this.failurePoint!.length > 512) {
      throw ArgumentError.value(this.failurePoint, "failurePoint", "length exceeds 512");
    }
    if (this.gate != null && this.gate!.length > 512) {
      throw ArgumentError.value(this.gate, "gate", "length exceeds 512");
    }
    if (this.inputKv != null && this.inputKv!.length > 512) {
      throw ArgumentError.value(this.inputKv, "inputKv", "length exceeds 512");
    }
    if (this.jankThresholdMs != null && this.jankThresholdMs!.length > 512) {
      throw ArgumentError.value(this.jankThresholdMs, "jankThresholdMs", "length exceeds 512");
    }
    if (this.jankyFrames != null && this.jankyFrames!.length > 512) {
      throw ArgumentError.value(this.jankyFrames, "jankyFrames", "length exceeds 512");
    }
    if (this.kind != null && this.kind!.length > 512) {
      throw ArgumentError.value(this.kind, "kind", "length exceeds 512");
    }
    if (this.module != null && this.module!.length > 512) {
      throw ArgumentError.value(this.module, "module", "length exceeds 512");
    }
    if (this.outcome != null && this.outcome!.length > 512) {
      throw ArgumentError.value(this.outcome, "outcome", "length exceeds 512");
    }
    if (this.outputKv != null && this.outputKv!.length > 512) {
      throw ArgumentError.value(this.outputKv, "outputKv", "length exceeds 512");
    }
    if (this.processedFrames != null && this.processedFrames!.length > 512) {
      throw ArgumentError.value(this.processedFrames, "processedFrames", "length exceeds 512");
    }
    if (this.reason != null && this.reason!.length > 512) {
      throw ArgumentError.value(this.reason, "reason", "length exceeds 512");
    }
    if (this.rendererMode != null && this.rendererMode!.length > 512) {
      throw ArgumentError.value(this.rendererMode, "rendererMode", "length exceeds 512");
    }
    if (this.sampledFrames != null && this.sampledFrames!.length > 512) {
      throw ArgumentError.value(this.sampledFrames, "sampledFrames", "length exceeds 512");
    }
    if (this.settleMs != null && this.settleMs!.length > 512) {
      throw ArgumentError.value(this.settleMs, "settleMs", "length exceeds 512");
    }
    if (this.settledPositionMs != null && this.settledPositionMs!.length > 512) {
      throw ArgumentError.value(this.settledPositionMs, "settledPositionMs", "length exceeds 512");
    }
    if (this.source != null && this.source!.length > 512) {
      throw ArgumentError.value(this.source, "source", "length exceeds 512");
    }
    if (this.stackFrameCount != null && this.stackFrameCount!.length > 512) {
      throw ArgumentError.value(this.stackFrameCount, "stackFrameCount", "length exceeds 512");
    }
    if (this.stage != null && this.stage!.length > 512) {
      throw ArgumentError.value(this.stage, "stage", "length exceeds 512");
    }
    if (this.stallMs != null && this.stallMs!.length > 512) {
      throw ArgumentError.value(this.stallMs, "stallMs", "length exceeds 512");
    }
    if (this.targetPositionMs != null && this.targetPositionMs!.length > 512) {
      throw ArgumentError.value(this.targetPositionMs, "targetPositionMs", "length exceeds 512");
    }
    if (this.ttffMs != null && this.ttffMs!.length > 512) {
      throw ArgumentError.value(this.ttffMs, "ttffMs", "length exceeds 512");
    }
    if (this.worstBuildFrameMs != null && this.worstBuildFrameMs!.length > 512) {
      throw ArgumentError.value(this.worstBuildFrameMs, "worstBuildFrameMs", "length exceeds 512");
    }
    if (this.worstFrameMs != null && this.worstFrameMs!.length > 512) {
      throw ArgumentError.value(this.worstFrameMs, "worstFrameMs", "length exceeds 512");
    }
    if (this.worstRasterFrameMs != null && this.worstRasterFrameMs!.length > 512) {
      throw ArgumentError.value(this.worstRasterFrameMs, "worstRasterFrameMs", "length exceeds 512");
    }
  }

  final String? anrThresholdMs;
  final String? artifactCount;
  final String? decoderFallbackEnabled;
  final String? decoderQueueMode;
  final String? droppedFrames;
  final String? exceptionType;
  final String? failurePoint;
  final String? gate;
  final String? inputKv;
  final String? jankThresholdMs;
  final String? jankyFrames;
  final String? kind;
  final String? module;
  final String? outcome;
  final String? outputKv;
  final String? processedFrames;
  final String? reason;
  final String? rendererMode;
  final String? sampledFrames;
  final String? settleMs;
  final String? settledPositionMs;
  final String? source;
  final String? stackFrameCount;
  final String? stage;
  final String? stallMs;
  final String? targetPositionMs;
  final String? ttffMs;
  final String? worstBuildFrameMs;
  final String? worstFrameMs;
  final String? worstRasterFrameMs;

  factory RuntimeLogAttributesWire.fromWire(Map<String, Object?> map, [String path = "RuntimeLogAttributesWire"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"anrThresholdMs", "artifactCount", "decoderFallbackEnabled", "decoderQueueMode", "droppedFrames", "exceptionType", "failurePoint", "gate", "inputKv", "jankThresholdMs", "jankyFrames", "kind", "module", "outcome", "outputKv", "processedFrames", "reason", "rendererMode", "sampledFrames", "settleMs", "settledPositionMs", "source", "stackFrameCount", "stage", "stallMs", "targetPositionMs", "ttffMs", "worstBuildFrameMs", "worstFrameMs", "worstRasterFrameMs"}, path);
    return RuntimeLogAttributesWire(
      anrThresholdMs: map["anrThresholdMs"] == null ? null : _generatedRequestString(map["anrThresholdMs"], '$path.anrThresholdMs'),
      artifactCount: map["artifactCount"] == null ? null : _generatedRequestString(map["artifactCount"], '$path.artifactCount'),
      decoderFallbackEnabled: map["decoderFallbackEnabled"] == null ? null : _generatedRequestString(map["decoderFallbackEnabled"], '$path.decoderFallbackEnabled'),
      decoderQueueMode: map["decoderQueueMode"] == null ? null : _generatedRequestString(map["decoderQueueMode"], '$path.decoderQueueMode'),
      droppedFrames: map["droppedFrames"] == null ? null : _generatedRequestString(map["droppedFrames"], '$path.droppedFrames'),
      exceptionType: map["exceptionType"] == null ? null : _generatedRequestString(map["exceptionType"], '$path.exceptionType'),
      failurePoint: map["failurePoint"] == null ? null : _generatedRequestString(map["failurePoint"], '$path.failurePoint'),
      gate: map["gate"] == null ? null : _generatedRequestString(map["gate"], '$path.gate'),
      inputKv: map["inputKv"] == null ? null : _generatedRequestString(map["inputKv"], '$path.inputKv'),
      jankThresholdMs: map["jankThresholdMs"] == null ? null : _generatedRequestString(map["jankThresholdMs"], '$path.jankThresholdMs'),
      jankyFrames: map["jankyFrames"] == null ? null : _generatedRequestString(map["jankyFrames"], '$path.jankyFrames'),
      kind: map["kind"] == null ? null : _generatedRequestString(map["kind"], '$path.kind'),
      module: map["module"] == null ? null : _generatedRequestString(map["module"], '$path.module'),
      outcome: map["outcome"] == null ? null : _generatedRequestString(map["outcome"], '$path.outcome'),
      outputKv: map["outputKv"] == null ? null : _generatedRequestString(map["outputKv"], '$path.outputKv'),
      processedFrames: map["processedFrames"] == null ? null : _generatedRequestString(map["processedFrames"], '$path.processedFrames'),
      reason: map["reason"] == null ? null : _generatedRequestString(map["reason"], '$path.reason'),
      rendererMode: map["rendererMode"] == null ? null : _generatedRequestString(map["rendererMode"], '$path.rendererMode'),
      sampledFrames: map["sampledFrames"] == null ? null : _generatedRequestString(map["sampledFrames"], '$path.sampledFrames'),
      settleMs: map["settleMs"] == null ? null : _generatedRequestString(map["settleMs"], '$path.settleMs'),
      settledPositionMs: map["settledPositionMs"] == null ? null : _generatedRequestString(map["settledPositionMs"], '$path.settledPositionMs'),
      source: map["source"] == null ? null : _generatedRequestString(map["source"], '$path.source'),
      stackFrameCount: map["stackFrameCount"] == null ? null : _generatedRequestString(map["stackFrameCount"], '$path.stackFrameCount'),
      stage: map["stage"] == null ? null : _generatedRequestString(map["stage"], '$path.stage'),
      stallMs: map["stallMs"] == null ? null : _generatedRequestString(map["stallMs"], '$path.stallMs'),
      targetPositionMs: map["targetPositionMs"] == null ? null : _generatedRequestString(map["targetPositionMs"], '$path.targetPositionMs'),
      ttffMs: map["ttffMs"] == null ? null : _generatedRequestString(map["ttffMs"], '$path.ttffMs'),
      worstBuildFrameMs: map["worstBuildFrameMs"] == null ? null : _generatedRequestString(map["worstBuildFrameMs"], '$path.worstBuildFrameMs'),
      worstFrameMs: map["worstFrameMs"] == null ? null : _generatedRequestString(map["worstFrameMs"], '$path.worstFrameMs'),
      worstRasterFrameMs: map["worstRasterFrameMs"] == null ? null : _generatedRequestString(map["worstRasterFrameMs"], '$path.worstRasterFrameMs'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.anrThresholdMs != null) "anrThresholdMs": this.anrThresholdMs!,
    if (this.artifactCount != null) "artifactCount": this.artifactCount!,
    if (this.decoderFallbackEnabled != null) "decoderFallbackEnabled": this.decoderFallbackEnabled!,
    if (this.decoderQueueMode != null) "decoderQueueMode": this.decoderQueueMode!,
    if (this.droppedFrames != null) "droppedFrames": this.droppedFrames!,
    if (this.exceptionType != null) "exceptionType": this.exceptionType!,
    if (this.failurePoint != null) "failurePoint": this.failurePoint!,
    if (this.gate != null) "gate": this.gate!,
    if (this.inputKv != null) "inputKv": this.inputKv!,
    if (this.jankThresholdMs != null) "jankThresholdMs": this.jankThresholdMs!,
    if (this.jankyFrames != null) "jankyFrames": this.jankyFrames!,
    if (this.kind != null) "kind": this.kind!,
    if (this.module != null) "module": this.module!,
    if (this.outcome != null) "outcome": this.outcome!,
    if (this.outputKv != null) "outputKv": this.outputKv!,
    if (this.processedFrames != null) "processedFrames": this.processedFrames!,
    if (this.reason != null) "reason": this.reason!,
    if (this.rendererMode != null) "rendererMode": this.rendererMode!,
    if (this.sampledFrames != null) "sampledFrames": this.sampledFrames!,
    if (this.settleMs != null) "settleMs": this.settleMs!,
    if (this.settledPositionMs != null) "settledPositionMs": this.settledPositionMs!,
    if (this.source != null) "source": this.source!,
    if (this.stackFrameCount != null) "stackFrameCount": this.stackFrameCount!,
    if (this.stage != null) "stage": this.stage!,
    if (this.stallMs != null) "stallMs": this.stallMs!,
    if (this.targetPositionMs != null) "targetPositionMs": this.targetPositionMs!,
    if (this.ttffMs != null) "ttffMs": this.ttffMs!,
    if (this.worstBuildFrameMs != null) "worstBuildFrameMs": this.worstBuildFrameMs!,
    if (this.worstFrameMs != null) "worstFrameMs": this.worstFrameMs!,
    if (this.worstRasterFrameMs != null) "worstRasterFrameMs": this.worstRasterFrameMs!,
  };
}

final class RuntimeLogBatchRequest {
  RuntimeLogBatchRequest({
    required List<RuntimeLogRecordWire> records,
  }) : records = List.unmodifiable(records) {
    if (this.records.length < 1) {
      throw ArgumentError.value(this.records, "records", "item count is below 1");
    }
  }

  final List<RuntimeLogRecordWire> records;

  factory RuntimeLogBatchRequest.fromWire(Map<String, Object?> map, [String path = "RuntimeLogBatchRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"records"}, path);
    return RuntimeLogBatchRequest(
      records: List<RuntimeLogRecordWire>.unmodifiable(_generatedRequestList(map["records"], '$path.records').asMap().entries.map((entry) => RuntimeLogRecordWire.fromWire(_generatedRequestObject(entry.value, '$path.records' + '[${entry.key}]'), '$path.records' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "records": this.records.map((value) => value.toWire()).toList(growable: false),
  };
}

final class RuntimeLogCorrelationWire {
  const RuntimeLogCorrelationWire({
    String? requestId,
    String? traceId,
    String? spanId,
    String? operationId,
    String? pageName,
    String? surfaceId,
    String? executionId,
    String? workPackageId,
    String? environmentRunId,
    String? actorHash,
  }) : requestId = requestId,
       traceId = traceId,
       spanId = spanId,
       operationId = operationId,
       pageName = pageName,
       surfaceId = surfaceId,
       executionId = executionId,
       workPackageId = workPackageId,
       environmentRunId = environmentRunId,
       actorHash = actorHash;

  final String? requestId;
  final String? traceId;
  final String? spanId;
  final String? operationId;
  final String? pageName;
  final String? surfaceId;
  final String? executionId;
  final String? workPackageId;
  final String? environmentRunId;
  final String? actorHash;

  factory RuntimeLogCorrelationWire.fromWire(Map<String, Object?> map, [String path = "RuntimeLogCorrelationWire"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId", "actorHash"}, path);
    return RuntimeLogCorrelationWire(
      requestId: map["requestId"] == null ? null : _generatedRequestString(map["requestId"], '$path.requestId'),
      traceId: map["traceId"] == null ? null : _generatedRequestString(map["traceId"], '$path.traceId'),
      spanId: map["spanId"] == null ? null : _generatedRequestString(map["spanId"], '$path.spanId'),
      operationId: map["operationId"] == null ? null : _generatedRequestString(map["operationId"], '$path.operationId'),
      pageName: map["pageName"] == null ? null : _generatedRequestString(map["pageName"], '$path.pageName'),
      surfaceId: map["surfaceId"] == null ? null : _generatedRequestString(map["surfaceId"], '$path.surfaceId'),
      executionId: map["executionId"] == null ? null : _generatedRequestString(map["executionId"], '$path.executionId'),
      workPackageId: map["workPackageId"] == null ? null : _generatedRequestString(map["workPackageId"], '$path.workPackageId'),
      environmentRunId: map["environmentRunId"] == null ? null : _generatedRequestString(map["environmentRunId"], '$path.environmentRunId'),
      actorHash: map["actorHash"] == null ? null : _generatedRequestString(map["actorHash"], '$path.actorHash'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.requestId != null) "requestId": this.requestId!,
    if (this.traceId != null) "traceId": this.traceId!,
    if (this.spanId != null) "spanId": this.spanId!,
    if (this.operationId != null) "operationId": this.operationId!,
    if (this.pageName != null) "pageName": this.pageName!,
    if (this.surfaceId != null) "surfaceId": this.surfaceId!,
    if (this.executionId != null) "executionId": this.executionId!,
    if (this.workPackageId != null) "workPackageId": this.workPackageId!,
    if (this.environmentRunId != null) "environmentRunId": this.environmentRunId!,
    if (this.actorHash != null) "actorHash": this.actorHash!,
  };
}

// Derived from _shared/runtime_observability.yaml#envelope; source SHA256: 8ee972ad69e67a5b96580799f293ed57f1367f300d1bc393425bfc7bca42f3cd.
final class RuntimeLogRecordWire {
  RuntimeLogRecordWire({
    required String schema,
    String? recordId,
    required DateTime occurredAt,
    required DateTime observedAt,
    required String logKind,
    required String severity,
    required String signal,
    required String message,
    required RuntimeLogResourceWire resource,
    RuntimeLogCorrelationWire? correlation,
    String? step,
    String? event,
    String? result,
    String? method,
    String? route,
    String? status,
    int? durationMs,
    String? action,
    String? target,
    String? errorCode,
    String? fingerprint,
    RuntimeLogAttributesWire? attributes,
  }) : schema = schema,
       recordId = recordId,
       occurredAt = occurredAt.toUtc(),
       observedAt = observedAt.toUtc(),
       logKind = logKind,
       severity = severity,
       signal = signal,
       message = message,
       resource = resource,
       correlation = correlation,
       step = step,
       event = event,
       result = result,
       method = method,
       route = route,
       status = status,
       durationMs = durationMs,
       action = action,
       target = target,
       errorCode = errorCode,
       fingerprint = fingerprint,
       attributes = attributes {
    if (this.schema.isEmpty) {
      throw ArgumentError.value(this.schema, "schema", 'must not be blank');
    }
    if (this.logKind.isEmpty) {
      throw ArgumentError.value(this.logKind, "logKind", 'must not be blank');
    }
    if (this.severity.isEmpty) {
      throw ArgumentError.value(this.severity, "severity", 'must not be blank');
    }
    if (this.signal.isEmpty) {
      throw ArgumentError.value(this.signal, "signal", 'must not be blank');
    }
    if (this.schema != "observability.slim") {
      throw ArgumentError.value(this.schema, 'schema', 'unsupported runtime log schema');
    }
    if (!const <String>{"deploy", "runtime", "access", "event", "exception", "audit"}.contains(this.logKind)) {
      throw ArgumentError.value(this.logKind, 'logKind', 'unsupported runtime log kind');
    }
    if (!const <String>{"DEBUG", "INFO", "WARN", "ERROR"}.contains(this.severity)) {
      throw ArgumentError.value(this.severity, 'severity', 'unsupported runtime log severity');
    }
    final signalPolicy = switch (this.signal) {
      "app.runtime.lifecycle" => (logKind: "runtime", attributes: const <String>{"artifactCount", "decoderFallbackEnabled", "decoderQueueMode", "droppedFrames", "exceptionType", "failurePoint", "gate", "inputKv", "jankThresholdMs", "jankyFrames", "kind", "module", "outcome", "outputKv", "processedFrames", "reason", "rendererMode", "sampledFrames", "settleMs", "settledPositionMs", "source", "stackFrameCount", "stage", "targetPositionMs", "ttffMs", "worstFrameMs"}, correlation: const <String>{"actorHash", "environmentRunId", "executionId", "operationId", "pageName", "requestId", "spanId", "surfaceId", "traceId", "workPackageId"}),
      "app.access.http" => (logKind: "access", attributes: const <String>{"artifactCount", "decoderFallbackEnabled", "decoderQueueMode", "droppedFrames", "exceptionType", "failurePoint", "gate", "inputKv", "jankThresholdMs", "jankyFrames", "kind", "module", "outcome", "outputKv", "processedFrames", "reason", "rendererMode", "sampledFrames", "settleMs", "settledPositionMs", "source", "stackFrameCount", "stage", "targetPositionMs", "ttffMs", "worstFrameMs"}, correlation: const <String>{"actorHash", "environmentRunId", "executionId", "operationId", "pageName", "requestId", "spanId", "surfaceId", "traceId", "workPackageId"}),
      "app.exception.flutter" => (logKind: "exception", attributes: const <String>{"artifactCount", "decoderFallbackEnabled", "decoderQueueMode", "droppedFrames", "exceptionType", "failurePoint", "gate", "inputKv", "jankThresholdMs", "jankyFrames", "kind", "module", "outcome", "outputKv", "processedFrames", "reason", "rendererMode", "sampledFrames", "settleMs", "settledPositionMs", "source", "stackFrameCount", "stage", "targetPositionMs", "ttffMs", "worstFrameMs"}, correlation: const <String>{"actorHash", "environmentRunId", "executionId", "operationId", "pageName", "requestId", "spanId", "surfaceId", "traceId", "workPackageId"}),
      "app.exception.platform" => (logKind: "exception", attributes: const <String>{"artifactCount", "decoderFallbackEnabled", "decoderQueueMode", "droppedFrames", "exceptionType", "failurePoint", "gate", "inputKv", "jankThresholdMs", "jankyFrames", "kind", "module", "outcome", "outputKv", "processedFrames", "reason", "rendererMode", "sampledFrames", "settleMs", "settledPositionMs", "source", "stackFrameCount", "stage", "targetPositionMs", "ttffMs", "worstFrameMs"}, correlation: const <String>{"actorHash", "environmentRunId", "executionId", "operationId", "pageName", "requestId", "spanId", "surfaceId", "traceId", "workPackageId"}),
      "app.performance.frame" => (logKind: "event", attributes: const <String>{"artifactCount", "decoderFallbackEnabled", "decoderQueueMode", "droppedFrames", "exceptionType", "failurePoint", "gate", "inputKv", "jankThresholdMs", "jankyFrames", "kind", "module", "outcome", "outputKv", "processedFrames", "reason", "rendererMode", "sampledFrames", "settleMs", "settledPositionMs", "source", "stackFrameCount", "stage", "targetPositionMs", "ttffMs", "worstBuildFrameMs", "worstFrameMs", "worstRasterFrameMs"}, correlation: const <String>{"actorHash", "environmentRunId", "executionId", "operationId", "pageName", "requestId", "spanId", "surfaceId", "traceId", "workPackageId"}),
      "app.performance.anr" => (logKind: "event", attributes: const <String>{"anrThresholdMs", "jankThresholdMs", "jankyFrames", "sampledFrames", "source", "stallMs", "worstFrameMs"}, correlation: const <String>{"actorHash", "environmentRunId", "executionId", "operationId", "pageName", "requestId", "spanId", "surfaceId", "traceId", "workPackageId"}),
      "app.performance.media" => (logKind: "event", attributes: const <String>{"artifactCount", "decoderFallbackEnabled", "decoderQueueMode", "droppedFrames", "exceptionType", "failurePoint", "gate", "inputKv", "jankThresholdMs", "jankyFrames", "kind", "module", "outcome", "outputKv", "processedFrames", "reason", "rendererMode", "sampledFrames", "settleMs", "settledPositionMs", "source", "stackFrameCount", "stage", "targetPositionMs", "ttffMs", "worstFrameMs"}, correlation: const <String>{"actorHash", "environmentRunId", "executionId", "operationId", "pageName", "requestId", "spanId", "surfaceId", "traceId", "workPackageId"}),
      "service.access.http" => (logKind: "access", attributes: const <String>{"artifactCount", "decoderFallbackEnabled", "decoderQueueMode", "droppedFrames", "exceptionType", "failurePoint", "gate", "inputKv", "jankThresholdMs", "jankyFrames", "kind", "module", "outcome", "outputKv", "processedFrames", "reason", "rendererMode", "sampledFrames", "settleMs", "settledPositionMs", "source", "stackFrameCount", "stage", "targetPositionMs", "ttffMs", "worstFrameMs"}, correlation: const <String>{"actorHash", "environmentRunId", "executionId", "operationId", "pageName", "requestId", "spanId", "surfaceId", "traceId", "workPackageId"}),
      "service.runtime.process" => (logKind: "runtime", attributes: const <String>{"artifactCount", "decoderFallbackEnabled", "decoderQueueMode", "droppedFrames", "exceptionType", "failurePoint", "gate", "inputKv", "jankThresholdMs", "jankyFrames", "kind", "module", "outcome", "outputKv", "processedFrames", "reason", "rendererMode", "sampledFrames", "settleMs", "settledPositionMs", "source", "stackFrameCount", "stage", "targetPositionMs", "ttffMs", "worstFrameMs"}, correlation: const <String>{"actorHash", "environmentRunId", "executionId", "operationId", "pageName", "requestId", "spanId", "surfaceId", "traceId", "workPackageId"}),
      "service.exception.runtime" => (logKind: "exception", attributes: const <String>{"artifactCount", "decoderFallbackEnabled", "decoderQueueMode", "droppedFrames", "exceptionType", "failurePoint", "gate", "inputKv", "jankThresholdMs", "jankyFrames", "kind", "module", "outcome", "outputKv", "processedFrames", "reason", "rendererMode", "sampledFrames", "settleMs", "settledPositionMs", "source", "stackFrameCount", "stage", "targetPositionMs", "ttffMs", "worstFrameMs"}, correlation: const <String>{"actorHash", "environmentRunId", "executionId", "operationId", "pageName", "requestId", "spanId", "surfaceId", "traceId", "workPackageId"}),
      "service.audit.control" => (logKind: "audit", attributes: const <String>{"artifactCount", "decoderFallbackEnabled", "decoderQueueMode", "droppedFrames", "exceptionType", "failurePoint", "gate", "inputKv", "jankThresholdMs", "jankyFrames", "kind", "module", "outcome", "outputKv", "processedFrames", "reason", "rendererMode", "sampledFrames", "settleMs", "settledPositionMs", "source", "stackFrameCount", "stage", "targetPositionMs", "ttffMs", "worstFrameMs"}, correlation: const <String>{"actorHash", "environmentRunId", "executionId", "operationId", "pageName", "requestId", "spanId", "surfaceId", "traceId", "workPackageId"}),
      "data.runtime.stage" => (logKind: "runtime", attributes: const <String>{"artifactCount", "decoderFallbackEnabled", "decoderQueueMode", "droppedFrames", "exceptionType", "failurePoint", "gate", "inputKv", "jankThresholdMs", "jankyFrames", "kind", "module", "outcome", "outputKv", "processedFrames", "reason", "rendererMode", "sampledFrames", "settleMs", "settledPositionMs", "source", "stackFrameCount", "stage", "targetPositionMs", "ttffMs", "worstFrameMs"}, correlation: const <String>{"actorHash", "environmentRunId", "executionId", "operationId", "pageName", "requestId", "spanId", "surfaceId", "traceId", "workPackageId"}),
      "data.exception.stage" => (logKind: "exception", attributes: const <String>{"artifactCount", "decoderFallbackEnabled", "decoderQueueMode", "droppedFrames", "exceptionType", "failurePoint", "gate", "inputKv", "jankThresholdMs", "jankyFrames", "kind", "module", "outcome", "outputKv", "processedFrames", "reason", "rendererMode", "sampledFrames", "settleMs", "settledPositionMs", "source", "stackFrameCount", "stage", "targetPositionMs", "ttffMs", "worstFrameMs"}, correlation: const <String>{"actorHash", "environmentRunId", "executionId", "operationId", "pageName", "requestId", "spanId", "surfaceId", "traceId", "workPackageId"}),
      "ops.audit.control" => (logKind: "audit", attributes: const <String>{"artifactCount", "decoderFallbackEnabled", "decoderQueueMode", "droppedFrames", "exceptionType", "failurePoint", "gate", "inputKv", "jankThresholdMs", "jankyFrames", "kind", "module", "outcome", "outputKv", "processedFrames", "reason", "rendererMode", "sampledFrames", "settleMs", "settledPositionMs", "source", "stackFrameCount", "stage", "targetPositionMs", "ttffMs", "worstFrameMs"}, correlation: const <String>{"actorHash", "environmentRunId", "executionId", "operationId", "pageName", "requestId", "spanId", "surfaceId", "traceId", "workPackageId"}),
      "ops.deploy.stackctl" => (logKind: "deploy", attributes: const <String>{"artifactCount", "decoderFallbackEnabled", "decoderQueueMode", "droppedFrames", "exceptionType", "failurePoint", "gate", "inputKv", "jankThresholdMs", "jankyFrames", "kind", "module", "outcome", "outputKv", "processedFrames", "reason", "rendererMode", "sampledFrames", "settleMs", "settledPositionMs", "source", "stackFrameCount", "stage", "targetPositionMs", "ttffMs", "worstFrameMs"}, correlation: const <String>{"actorHash", "environmentRunId", "executionId", "operationId", "pageName", "requestId", "spanId", "surfaceId", "traceId", "workPackageId"}),
      "ops.exception.runtime" => (logKind: "exception", attributes: const <String>{"artifactCount", "decoderFallbackEnabled", "decoderQueueMode", "droppedFrames", "exceptionType", "failurePoint", "gate", "inputKv", "jankThresholdMs", "jankyFrames", "kind", "module", "outcome", "outputKv", "processedFrames", "reason", "rendererMode", "sampledFrames", "settleMs", "settledPositionMs", "source", "stackFrameCount", "stage", "targetPositionMs", "ttffMs", "worstFrameMs"}, correlation: const <String>{"actorHash", "environmentRunId", "executionId", "operationId", "pageName", "requestId", "spanId", "surfaceId", "traceId", "workPackageId"}),
      "ops.runtime.process" => (logKind: "runtime", attributes: const <String>{"artifactCount", "decoderFallbackEnabled", "decoderQueueMode", "droppedFrames", "exceptionType", "failurePoint", "gate", "inputKv", "jankThresholdMs", "jankyFrames", "kind", "module", "outcome", "outputKv", "processedFrames", "reason", "rendererMode", "sampledFrames", "settleMs", "settledPositionMs", "source", "stackFrameCount", "stage", "targetPositionMs", "ttffMs", "worstFrameMs"}, correlation: const <String>{"actorHash", "environmentRunId", "executionId", "operationId", "pageName", "requestId", "spanId", "surfaceId", "traceId", "workPackageId"}),
      "portal.exception.browser" => (logKind: "exception", attributes: const <String>{"artifactCount", "decoderFallbackEnabled", "decoderQueueMode", "droppedFrames", "exceptionType", "failurePoint", "gate", "inputKv", "jankThresholdMs", "jankyFrames", "kind", "module", "outcome", "outputKv", "processedFrames", "reason", "rendererMode", "sampledFrames", "settleMs", "settledPositionMs", "source", "stackFrameCount", "stage", "targetPositionMs", "ttffMs", "worstFrameMs"}, correlation: const <String>{"actorHash", "environmentRunId", "executionId", "operationId", "pageName", "requestId", "spanId", "surfaceId", "traceId", "workPackageId"}),
      _ => throw ArgumentError.value(this.signal, 'signal', 'unknown runtime log signal'),
    };
    if (signalPolicy.logKind != this.logKind) {
      throw ArgumentError.value(this.signal, 'signal', 'does not match logKind');
    }
    final attributeKeys = this.attributes?.toWire().keys ?? const <String>[];
    if (!attributeKeys.every(signalPolicy.attributes.contains)) {
      throw ArgumentError.value(attributeKeys, 'attributes', 'contains fields outside signal policy');
    }
    final correlationKeys = this.correlation?.toWire().keys ?? const <String>[];
    if (!correlationKeys.every(signalPolicy.correlation.contains)) {
      throw ArgumentError.value(correlationKeys, 'correlation', 'contains fields outside signal policy');
    }
    final presentKindFields = <String>{
      if (this.step != null) "step",
      if (this.event != null) "event",
      if (this.result != null) "result",
      if (this.method != null) "method",
      if (this.route != null) "route",
      if (this.status != null) "status",
      if (this.durationMs != null) "durationMs",
      if (this.action != null) "action",
      if (this.target != null) "target",
      if (this.errorCode != null) "errorCode",
    };
    final requiredKindFields = switch (this.logKind) {
      "deploy" => const <String>{"result", "step"},
      "runtime" => const <String>{"event", "result"},
      "access" => const <String>{"durationMs", "method", "route", "status"},
      "event" => const <String>{"event", "result"},
      "exception" => const <String>{"errorCode"},
      "audit" => const <String>{"action", "result", "target"},
      _ => const <String>{},
    };
    if (!requiredKindFields.every(presentKindFields.contains)) {
      throw ArgumentError.value(presentKindFields, 'logKind', 'missing required runtime log fields');
    }
    if (attributeKeys.length > 24) {
      throw ArgumentError.value(attributeKeys.length, 'attributes', 'too many runtime log attributes');
    }
  }

  final String schema;
  final String? recordId;
  final DateTime occurredAt;
  final DateTime observedAt;
  final String logKind;
  final String severity;
  final String signal;
  final String message;
  final RuntimeLogResourceWire resource;
  final RuntimeLogCorrelationWire? correlation;
  final String? step;
  final String? event;
  final String? result;
  final String? method;
  final String? route;
  final String? status;
  final int? durationMs;
  final String? action;
  final String? target;
  final String? errorCode;
  final String? fingerprint;
  final RuntimeLogAttributesWire? attributes;

  factory RuntimeLogRecordWire.fromWire(Map<String, Object?> map, [String path = "RuntimeLogRecordWire"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"schema", "recordId", "occurredAt", "observedAt", "logKind", "severity", "signal", "message", "resource", "correlation", "step", "event", "result", "method", "route", "status", "durationMs", "action", "target", "errorCode", "fingerprint", "attributes"}, path);
    return RuntimeLogRecordWire(
      schema: _generatedRequestString(map["schema"], '$path.schema'),
      recordId: map["recordId"] == null ? null : _generatedRequestString(map["recordId"], '$path.recordId'),
      occurredAt: _generatedRequestTimestamp(map["occurredAt"], '$path.occurredAt'),
      observedAt: _generatedRequestTimestamp(map["observedAt"], '$path.observedAt'),
      logKind: _generatedRequestString(map["logKind"], '$path.logKind'),
      severity: _generatedRequestString(map["severity"], '$path.severity'),
      signal: _generatedRequestString(map["signal"], '$path.signal'),
      message: _generatedRequestString(map["message"], '$path.message'),
      resource: RuntimeLogResourceWire.fromWire(_generatedRequestObject(map["resource"], '$path.resource'), '$path.resource'),
      correlation: map["correlation"] == null ? null : RuntimeLogCorrelationWire.fromWire(_generatedRequestObject(map["correlation"], '$path.correlation'), '$path.correlation'),
      step: map["step"] == null ? null : _generatedRequestString(map["step"], '$path.step'),
      event: map["event"] == null ? null : _generatedRequestString(map["event"], '$path.event'),
      result: map["result"] == null ? null : _generatedRequestString(map["result"], '$path.result'),
      method: map["method"] == null ? null : _generatedRequestString(map["method"], '$path.method'),
      route: map["route"] == null ? null : _generatedRequestString(map["route"], '$path.route'),
      status: map["status"] == null ? null : _generatedRequestString(map["status"], '$path.status'),
      durationMs: map["durationMs"] == null ? null : _generatedRequestInt(map["durationMs"], '$path.durationMs'),
      action: map["action"] == null ? null : _generatedRequestString(map["action"], '$path.action'),
      target: map["target"] == null ? null : _generatedRequestString(map["target"], '$path.target'),
      errorCode: map["errorCode"] == null ? null : _generatedRequestString(map["errorCode"], '$path.errorCode'),
      fingerprint: map["fingerprint"] == null ? null : _generatedRequestString(map["fingerprint"], '$path.fingerprint'),
      attributes: map["attributes"] == null ? null : RuntimeLogAttributesWire.fromWire(_generatedRequestObject(map["attributes"], '$path.attributes'), '$path.attributes'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "schema": this.schema,
    if (this.recordId != null) "recordId": this.recordId!,
    "occurredAt": this.occurredAt.toUtc().toIso8601String(),
    "observedAt": this.observedAt.toUtc().toIso8601String(),
    "logKind": this.logKind,
    "severity": this.severity,
    "signal": this.signal,
    "message": this.message,
    "resource": this.resource.toWire(),
    if (this.correlation != null) "correlation": this.correlation!.toWire(),
    if (this.step != null) "step": this.step!,
    if (this.event != null) "event": this.event!,
    if (this.result != null) "result": this.result!,
    if (this.method != null) "method": this.method!,
    if (this.route != null) "route": this.route!,
    if (this.status != null) "status": this.status!,
    if (this.durationMs != null) "durationMs": this.durationMs!,
    if (this.action != null) "action": this.action!,
    if (this.target != null) "target": this.target!,
    if (this.errorCode != null) "errorCode": this.errorCode!,
    if (this.fingerprint != null) "fingerprint": this.fingerprint!,
    if (this.attributes != null) "attributes": this.attributes!.toWire(),
  };
}

final class RuntimeLogResourceWire {
  RuntimeLogResourceWire({
    required String sourceType,
    required String service,
    String? environment,
    String? component,
    String? appVersion,
    String? serviceVersionversion,
  }) : sourceType = sourceType,
       service = service,
       environment = environment,
       component = component,
       appVersion = appVersion,
       serviceVersionversion = serviceVersionversion {
    if (this.sourceType.isEmpty) {
      throw ArgumentError.value(this.sourceType, "sourceType", 'must not be blank');
    }
    if (this.service.isEmpty) {
      throw ArgumentError.value(this.service, "service", 'must not be blank');
    }
  }

  final String sourceType;
  final String service;
  final String? environment;
  final String? component;
  final String? appVersion;
  final String? serviceVersionversion;

  factory RuntimeLogResourceWire.fromWire(Map<String, Object?> map, [String path = "RuntimeLogResourceWire"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"sourceType", "service", "environment", "component", "appVersion", "service.version"}, path);
    return RuntimeLogResourceWire(
      sourceType: _generatedRequestString(map["sourceType"], '$path.sourceType'),
      service: _generatedRequestString(map["service"], '$path.service'),
      environment: map["environment"] == null ? null : _generatedRequestString(map["environment"], '$path.environment'),
      component: map["component"] == null ? null : _generatedRequestString(map["component"], '$path.component'),
      appVersion: map["appVersion"] == null ? null : _generatedRequestString(map["appVersion"], '$path.appVersion'),
      serviceVersionversion: map["service.version"] == null ? null : _generatedRequestString(map["service.version"], '$path.service.version'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "sourceType": this.sourceType,
    "service": this.service,
    if (this.environment != null) "environment": this.environment!,
    if (this.component != null) "component": this.component!,
    if (this.appVersion != null) "appVersion": this.appVersion!,
    if (this.serviceVersionversion != null) "service.version": this.serviceVersionversion!,
  };
}

final class StartupTelemetryEventWire {
  StartupTelemetryEventWire({
    required String eventId,
    required String attemptId,
    required int sequence,
    required String phase,
    required int phaseDurationMs,
    required int elapsedMs,
    required String outcome,
    required DateTime occurredAt,
    required String platform,
    required String runtimeEnv,
    String? appVersion,
    String? networkClass,
    StartupRecoverySurface? recoverySurface,
    StartupRecoveryLifecycle? recoveryLifecycle,
    StartupRecoveryMount? recoveryMount,
    StartupRecoveryPhase? recoveryPhase,
    StartupRecoveryAction? recoveryAction,
    String? failureCode,
    String? failureSource,
    String? deadlineOrigin,
  }) : eventId = eventId,
       attemptId = attemptId,
       sequence = sequence,
       phase = phase,
       phaseDurationMs = phaseDurationMs,
       elapsedMs = elapsedMs,
       outcome = outcome,
       occurredAt = occurredAt,
       platform = platform,
       runtimeEnv = runtimeEnv,
       appVersion = appVersion,
       networkClass = networkClass,
       recoverySurface = recoverySurface,
       recoveryLifecycle = recoveryLifecycle,
       recoveryMount = recoveryMount,
       recoveryPhase = recoveryPhase,
       recoveryAction = recoveryAction,
       failureCode = failureCode,
       failureSource = failureSource,
       deadlineOrigin = deadlineOrigin {
    if (this.eventId.isEmpty) {
      throw ArgumentError.value(this.eventId, "eventId", 'must not be blank');
    }
    if (this.attemptId.isEmpty) {
      throw ArgumentError.value(this.attemptId, "attemptId", 'must not be blank');
    }
    if (this.phase.isEmpty) {
      throw ArgumentError.value(this.phase, "phase", 'must not be blank');
    }
    if (this.outcome.isEmpty) {
      throw ArgumentError.value(this.outcome, "outcome", 'must not be blank');
    }
    if (this.platform.isEmpty) {
      throw ArgumentError.value(this.platform, "platform", 'must not be blank');
    }
    if (this.runtimeEnv.isEmpty) {
      throw ArgumentError.value(this.runtimeEnv, "runtimeEnv", 'must not be blank');
    }
  }

  final String eventId;
  final String attemptId;
  final int sequence;
  final String phase;
  final int phaseDurationMs;
  final int elapsedMs;
  final String outcome;
  final DateTime occurredAt;
  final String platform;
  final String runtimeEnv;
  final String? appVersion;
  final String? networkClass;
  final StartupRecoverySurface? recoverySurface;
  final StartupRecoveryLifecycle? recoveryLifecycle;
  final StartupRecoveryMount? recoveryMount;
  final StartupRecoveryPhase? recoveryPhase;
  final StartupRecoveryAction? recoveryAction;
  final String? failureCode;
  final String? failureSource;
  final String? deadlineOrigin;

  factory StartupTelemetryEventWire.fromWire(Map<String, Object?> map, [String path = "StartupTelemetryEventWire"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"eventId", "attemptId", "sequence", "phase", "phaseDurationMs", "elapsedMs", "outcome", "occurredAt", "platform", "runtimeEnv", "appVersion", "networkClass", "recoverySurface", "recoveryLifecycle", "recoveryMount", "recoveryPhase", "recoveryAction", "failureCode", "failureSource", "deadlineOrigin"}, path);
    return StartupTelemetryEventWire(
      eventId: _generatedRequestString(map["eventId"], '$path.eventId'),
      attemptId: _generatedRequestString(map["attemptId"], '$path.attemptId'),
      sequence: _generatedRequestInt(map["sequence"], '$path.sequence'),
      phase: _generatedRequestString(map["phase"], '$path.phase'),
      phaseDurationMs: _generatedRequestInt(map["phaseDurationMs"], '$path.phaseDurationMs'),
      elapsedMs: _generatedRequestInt(map["elapsedMs"], '$path.elapsedMs'),
      outcome: _generatedRequestString(map["outcome"], '$path.outcome'),
      occurredAt: _generatedRequestTimestamp(map["occurredAt"], '$path.occurredAt'),
      platform: _generatedRequestString(map["platform"], '$path.platform'),
      runtimeEnv: _generatedRequestString(map["runtimeEnv"], '$path.runtimeEnv'),
      appVersion: map["appVersion"] == null ? null : _generatedRequestString(map["appVersion"], '$path.appVersion'),
      networkClass: map["networkClass"] == null ? null : _generatedRequestString(map["networkClass"], '$path.networkClass'),
      recoverySurface: map["recoverySurface"] == null ? null : switch (map["recoverySurface"]) { "page.app.startup_recovery" => StartupRecoverySurface.pageAppStartupRecovery, _ => throw FormatException('$path.recoverySurface' + ' has an invalid enum value'), },
      recoveryLifecycle: map["recoveryLifecycle"] == null ? null : switch (map["recoveryLifecycle"]) { "enter" => StartupRecoveryLifecycle.enter, "phase_change" => StartupRecoveryLifecycle.phaseChange, "external_action" => StartupRecoveryLifecycle.externalAction, "runtime_reentry" => StartupRecoveryLifecycle.runtimeReentry, "exit" => StartupRecoveryLifecycle.exit, "failure" => StartupRecoveryLifecycle.failure, _ => throw FormatException('$path.recoveryLifecycle' + ' has an invalid enum value'), },
      recoveryMount: map["recoveryMount"] == null ? null : switch (map["recoveryMount"]) { "bootstrap" => StartupRecoveryMount.bootstrap, "runtime_boundary" => StartupRecoveryMount.runtimeBoundary, "safe_shell" => StartupRecoveryMount.safeShell, "router_error" => StartupRecoveryMount.routerError, _ => throw FormatException('$path.recoveryMount' + ' has an invalid enum value'), },
      recoveryPhase: map["recoveryPhase"] == null ? null : switch (map["recoveryPhase"]) { "startup_checking" => StartupRecoveryPhase.startupChecking, "startup_update_required" => StartupRecoveryPhase.startupUpdateRequired, "startup_latest" => StartupRecoveryPhase.startupLatest, "startup_version_unavailable" => StartupRecoveryPhase.startupVersionUnavailable, "runtime_unavailable" => StartupRecoveryPhase.runtimeUnavailable, "runtime_reentering" => StartupRecoveryPhase.runtimeReentering, "runtime_version_checking" => StartupRecoveryPhase.runtimeVersionChecking, "runtime_update_required" => StartupRecoveryPhase.runtimeUpdateRequired, "runtime_latest" => StartupRecoveryPhase.runtimeLatest, "runtime_version_unavailable" => StartupRecoveryPhase.runtimeVersionUnavailable, _ => throw FormatException('$path.recoveryPhase' + ' has an invalid enum value'), },
      recoveryAction: map["recoveryAction"] == null ? null : switch (map["recoveryAction"]) { "none" => StartupRecoveryAction.none, "open_update" => StartupRecoveryAction.openUpdate, "open_web" => StartupRecoveryAction.openWeb, "external_return" => StartupRecoveryAction.externalReturn, "runtime_reentry" => StartupRecoveryAction.runtimeReentry, _ => throw FormatException('$path.recoveryAction' + ' has an invalid enum value'), },
      failureCode: map["failureCode"] == null ? null : _generatedRequestString(map["failureCode"], '$path.failureCode'),
      failureSource: map["failureSource"] == null ? null : _generatedRequestString(map["failureSource"], '$path.failureSource'),
      deadlineOrigin: map["deadlineOrigin"] == null ? null : _generatedRequestString(map["deadlineOrigin"], '$path.deadlineOrigin'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "eventId": this.eventId,
    "attemptId": this.attemptId,
    "sequence": this.sequence,
    "phase": this.phase,
    "phaseDurationMs": this.phaseDurationMs,
    "elapsedMs": this.elapsedMs,
    "outcome": this.outcome,
    "occurredAt": this.occurredAt.toUtc().toIso8601String(),
    "platform": this.platform,
    "runtimeEnv": this.runtimeEnv,
    if (this.appVersion != null) "appVersion": this.appVersion!,
    if (this.networkClass != null) "networkClass": this.networkClass!,
    if (this.recoverySurface != null) "recoverySurface": this.recoverySurface!.wireName,
    if (this.recoveryLifecycle != null) "recoveryLifecycle": this.recoveryLifecycle!.wireName,
    if (this.recoveryMount != null) "recoveryMount": this.recoveryMount!.wireName,
    if (this.recoveryPhase != null) "recoveryPhase": this.recoveryPhase!.wireName,
    if (this.recoveryAction != null) "recoveryAction": this.recoveryAction!.wireName,
    if (this.failureCode != null) "failureCode": this.failureCode!,
    if (this.failureSource != null) "failureSource": this.failureSource!,
    if (this.deadlineOrigin != null) "deadlineOrigin": this.deadlineOrigin!,
  };
}

CloudOperationRequestPayload encodeOpsAppReleaseGetAppRecoveryVersionGeneratedRequest(GetAppRecoveryVersionQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "platform": request.platform,
      "appVersion": request.appVersion,
      "buildNumber": (request.buildNumber).toString(),
    },
  );
}

CloudOperationRequestPayload encodeOpsEventRecordReportEventBatchGeneratedRequest(EventRecordBatchRequest request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "events": request.events.map((value) => value.toWire()).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeOpsEventRecordReportRuntimeLogBatchGeneratedRequest(RuntimeLogBatchRequest request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "records": request.records.map((value) => value.toWire()).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeOpsEventRecordReportStartupEventBatchGeneratedRequest(ReportStartupEventBatchCommand request) {
  return CloudOperationRequestPayload(
    headers: <String, String>{
      "X-Qwq-Startup-Proof": request.proof,
    },
    body: <String, Object?>{
      "events": request.events.map((value) => value.toWire()).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeOpsRecoveryFailureReportRecoveryFailureGeneratedRequest(ReportRecoveryFailureRequest request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "occurredAt": request.occurredAt.toUtc().toIso8601String(),
      "appVersion": request.appVersion,
      "buildNumber": request.buildNumber,
      "platform": request.platform,
      "osVersion": request.osVersion,
      "deviceModel": request.deviceModel,
      "errorSource": request.errorSource,
      "errorType": request.errorType,
      "errorMessage": request.errorMessage,
      "stackTrace": request.stackTrace,
    },
  );
}

CloudOperationRequestPayload encodeOpsVisitRecordRecordVisitGeneratedRequest(RecordVisitRequest request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "targetType": request.targetType.wireName,
      "targetKey": request.targetKey,
    },
  );
}

