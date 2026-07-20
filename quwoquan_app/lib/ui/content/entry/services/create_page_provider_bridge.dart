import 'dart:convert';
import 'dart:developer' as developer;

import 'package:crypto/crypto.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// 发布写动作依赖已解析的当前分身上下文。
///
/// 这是端侧在发起云命令前发现的临时依赖不可用，不是 Dart [StateError] 或可供
/// UI 解析的字符串。稳定错误码复用 content metadata 中的
/// `CONTENT.SYSTEM.required_dependency_unavailable`，具体语义放入
/// [RuntimeFailure.semanticReason]，供页面做类型安全的恢复展示。
final class ActivePersonaContextUnavailableFailure extends RuntimeFailure {
  ActivePersonaContextUnavailableFailure()
    : super(
        code: ContentErrorCode.requiredDependencyUnavailable.code,
        semanticReason: 'active_persona_context_unavailable',
        origin: RuntimeFailureOrigin.localClient,
        kind: RuntimeFailureKind.unavailable,
        nature: RuntimeFailureNature.transient,
        location: const RuntimeFailureLocation(
          businessObject: 'content_post',
          functionModule: 'attach_active_persona',
        ),
        context: const RuntimeFailureContext(),
        recovery: const RuntimeRecoveryDirective(
          action: 'retry',
          disruptionLevel: 'surface',
        ),
      );
}

/// UI composition bridge. Pure payload/media preparation deliberately lives
/// outside this file so its contract tests do not load the application root.
Future<void> reportCreateEditorSurfaceEvent(
  WidgetRef ref,
  String event, [
  Map<String, Object?> extras = const {},
  String surfaceId = 'create_editor',
]) async {
  try {
    final reporter = ref.read(appTelemetryReporterProvider);
    final contentType = _publicationContentType(extras['contentType']);
    final publication = _publicationTelemetryFor(
      event,
      contentType: contentType,
      surfaceId: surfaceId,
      failReasonCode: extras['failReasonCode']?.toString(),
      durationMs: extras['durationMs'] is num
          ? (extras['durationMs'] as num).toInt()
          : null,
      correlationHash: extras['correlationHash']?.toString(),
    );
    final payload =
        publication ??
        AppTelemetryPayload.productAction(
          journey: 'content_creation_to_publication',
          action: event,
          result: extras['result']?.toString(),
          durationMs: extras['durationMs'] is num
              ? (extras['durationMs'] as num).toInt()
              : null,
          failReasonCode: extras['failReasonCode']?.toString(),
        );
    await reporter.record(
      payload,
      pageName: surfaceId == 'localDrafts' || surfaceId == 'local_drafts'
          ? 'local_drafts'
          : 'create',
    );
  } catch (error, stackTrace) {
    developer.log(
      'reportCreateEditorSurfaceEvent failed: event=$event',
      name: 'CreateEditor',
      error: error,
      stackTrace: stackTrace,
    );
  }
}

AppTelemetryPayload? _publicationTelemetryFor(
  String event, {
  required String contentType,
  required String surfaceId,
  String? failReasonCode,
  int? durationMs,
  String? correlationHash,
}) {
  final (stage, state, result) = switch (event) {
    'create_editor_ready' => ('editor_ready', 'draft', 'ready'),
    'create_draft_saved' => ('draft_saved', 'draft', 'success'),
    'create_draft_restored' => ('draft_restored', 'draft', 'success'),
    'create_publish_started' => ('submit_started', 'submitting', 'started'),
    'create_publish_queued' => ('queued', 'retry_wait', 'queued'),
    'create_publish_failure' => ('blocked', 'blocked', 'failure'),
    'create_publish_pending_review' => (
      'pending_review',
      'pending_review',
      'accepted',
    ),
    'create_publish_success' => ('published', 'published', 'success'),
    _ => (null, null, null),
  };
  if (stage == null || state == null || result == null) {
    return null;
  }
  return AppTelemetryPayload.contentPublication(
    publicationStage: stage,
    contentType: contentType,
    objectState: state,
    surfaceId: surfaceId,
    result: result,
    durationMs: durationMs,
    failReasonCode: failReasonCode,
    correlationHash: correlationHash,
  );
}

String _publicationContentType(Object? raw) {
  final normalized = raw?.toString().trim() ?? '';
  return switch (normalized) {
    'micro' || 'article' || 'image' || 'video' => normalized,
    _ => 'unknown',
  };
}

String publicationCorrelationHash(String publishIntentId) {
  final normalized = publishIntentId.trim();
  if (normalized.isEmpty) return '';
  return sha256.convert(utf8.encode(normalized)).toString().substring(0, 32);
}

Future<SubmitContentPostPublicationCommand>
attachActivePersonaToPostPublicationCommand(
  WidgetRef ref,
  PreparedPostPublicationPayload prepared, {
  required String localDraftId,
}) async {
  final activeContext = await ref.read(activePersonaContextProvider.future);
  if (ref
          .read(contentConfigRepositoryProvider)
          .requiresResolvedPersonaForMutations &&
      activeContext.isFallback) {
    throw ActivePersonaContextUnavailableFailure();
  }
  final personaVersion = int.tryParse(activeContext.personaContextVersion);
  return submitContentPostPublicationCommandFromPreparedPayload(
    prepared.payload,
    localDraftId: localDraftId,
    mediaAssetIds: prepared.mediaAssetIds,
    authorDisplayNameSnapshot: activeContext.displayName,
    authorAvatarUrlSnapshot: activeContext.avatarUrl,
    personaContextVersion: personaVersion,
  );
}
